"""Pruebas de la Fase 1: cimientos, login, roles, configuración y utilidades."""

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from models import ConfiguracionSistema, IntentoLogin, Usuario, db
from tests.conftest import PASSWORD_PRUEBA, crear_usuario, iniciar_sesion, token_csrf
from utils import ZONA_BOGOTA, enlace_whatsapp, formato_cop, formato_fecha, obtener_hora_bogota

# ---------------------------------------------------------------------------
# Arranque estricto
# ---------------------------------------------------------------------------


def test_arranque_falla_sin_database_url(monkeypatch):
    from app import create_app

    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        create_app()


def test_arranque_falla_sin_secret_key(monkeypatch):
    from app import create_app

    monkeypatch.setenv("SECRET_KEY", "")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()


def test_rechaza_bases_que_no_sean_postgres(monkeypatch):
    from app import create_app

    monkeypatch.setenv("DATABASE_URL", "sqlite:///vetcare.db")
    with pytest.raises(RuntimeError, match="PostgreSQL"):
        create_app()


def test_config_no_tiene_valores_por_defecto_peligrosos(app):
    assert app.config["SECRET_KEY"] not in ("", "dev", "secret", "changeme")
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config.get("WTF_CSRF_ENABLED", True) is True


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def test_hora_bogota_tiene_zona():
    ahora = obtener_hora_bogota()
    assert ahora.tzinfo is not None
    assert ahora.utcoffset() == timedelta(hours=-5)


@pytest.mark.parametrize(
    "valor, esperado",
    [
        (Decimal("45000"), "$45.000"),
        (45000, "$45.000"),
        ("1234567.49", "$1.234.567"),
        (Decimal("999.50"), "$1.000"),
        (0, "$0"),
        (None, "$0"),
        (Decimal("-2500"), "-$2.500"),
    ],
)
def test_formato_cop(valor, esperado):
    assert formato_cop(valor) == esperado


def test_formato_fecha_convierte_a_bogota():
    # 03:30 UTC del 15 de septiembre = 10:30 p. m. del 14 en Bogotá.
    from zoneinfo import ZoneInfo

    valor = datetime(2026, 9, 15, 3, 30, tzinfo=ZoneInfo("UTC"))
    assert formato_fecha(valor) == "14/09/2026"
    assert formato_fecha(valor, con_hora=True) == "14/09/2026 10:30 p. m."


def test_enlace_whatsapp():
    assert enlace_whatsapp("310 555 1234", "Hola Firulais") == "https://wa.me/573105551234?text=Hola%20Firulais"
    assert enlace_whatsapp("+57 310 555 1234") == "https://wa.me/573105551234"
    assert enlace_whatsapp("") == ""


# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------


def test_pagina_login_carga(client):
    respuesta = client.get("/auth/login")
    assert respuesta.status_code == 200
    assert "Iniciar sesión" in respuesta.get_data(as_text=True)
    assert 'name="csrf_token"' in respuesta.get_data(as_text=True)


def test_rutas_protegidas_redirigen_al_login(client):
    respuesta = client.get("/")
    assert respuesta.status_code == 302
    assert "/auth/login" in respuesta.headers["Location"]


def test_login_correcto_lleva_al_tablero(client, admin, app):
    respuesta = iniciar_sesion(client)
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/")
    tablero = client.get("/")
    assert tablero.status_code == 200
    assert "Hola, Usuario" in tablero.get_data(as_text=True)
    with app.app_context():
        usuario = db.session.get(Usuario, admin)
        assert usuario.ultimo_acceso is not None
        assert usuario.ultimo_acceso.astimezone(ZONA_BOGOTA).date() == obtener_hora_bogota().date()


def test_login_no_distingue_mayusculas_en_correo(client, admin):
    respuesta = iniciar_sesion(client, email="ADMIN@Prueba.local")
    assert respuesta.status_code == 302


def test_login_incorrecto(client, admin):
    respuesta = iniciar_sesion(client, password="incorrecta")
    assert respuesta.status_code == 200
    assert "Correo o contraseña incorrectos" in respuesta.get_data(as_text=True)


def test_usuario_inactivo_no_puede_entrar(client, app):
    crear_usuario(app, email="inactivo@prueba.local", activo=False)
    respuesta = iniciar_sesion(client, email="inactivo@prueba.local")
    assert respuesta.status_code == 200
    assert "Correo o contraseña incorrectos" in respuesta.get_data(as_text=True)


def test_bloqueo_tras_cinco_intentos_fallidos(client, admin, app):
    for _ in range(IntentoLogin.LIMITE_INTENTOS):
        iniciar_sesion(client, password="incorrecta")
    respuesta = iniciar_sesion(client, password=PASSWORD_PRUEBA)  # incluso la clave correcta
    assert respuesta.status_code == 429
    assert "Demasiados intentos" in respuesta.get_data(as_text=True)
    with app.app_context():
        assert IntentoLogin.fallidos_recientes("127.0.0.1") == IntentoLogin.LIMITE_INTENTOS


def test_post_sin_token_csrf_es_rechazado(client, admin):
    respuesta = client.post("/auth/login", data={"email": "admin@prueba.local", "password": PASSWORD_PRUEBA})
    assert respuesta.status_code == 400


def test_redireccion_abierta_bloqueada(client, admin):
    token = token_csrf(client)
    respuesta = client.post(
        "/auth/login?next=https://malicioso.example.com",
        data={"csrf_token": token, "email": "admin@prueba.local", "password": PASSWORD_PRUEBA},
    )
    assert respuesta.status_code == 302
    assert "malicioso" not in respuesta.headers["Location"]


def test_logout_solo_por_post(client, admin):
    iniciar_sesion(client)
    assert client.get("/auth/logout").status_code == 405
    token = token_csrf(client, "/")
    respuesta = client.post("/auth/logout", data={"csrf_token": token})
    assert respuesta.status_code == 302
    assert client.get("/").status_code == 302  # ya no hay sesión


def test_cambiar_password(client, admin, app):
    iniciar_sesion(client)
    token = token_csrf(client, "/auth/cambiar-password")
    respuesta = client.post(
        "/auth/cambiar-password",
        data={
            "csrf_token": token,
            "password_actual": PASSWORD_PRUEBA,
            "password_nueva": "Nueva-Clave-456",
            "password_confirmacion": "Nueva-Clave-456",
        },
    )
    assert respuesta.status_code == 302
    with app.app_context():
        assert db.session.get(Usuario, admin).verificar_password("Nueva-Clave-456")


# ---------------------------------------------------------------------------
# Roles y permisos
# ---------------------------------------------------------------------------


def test_cajero_no_entra_a_administracion(client, cajero):
    iniciar_sesion(client, email="cajero@prueba.local")
    assert client.get("/").status_code == 200
    assert client.get("/admin/usuarios").status_code == 403
    assert client.get("/admin/configuracion").status_code == 403
    tablero = client.get("/").get_data(as_text=True)
    assert "/admin/usuarios" not in tablero  # el menú no ofrece lo que no puede usar


def test_admin_entra_a_administracion(client, admin):
    iniciar_sesion(client)
    assert client.get("/admin/usuarios").status_code == 200
    assert client.get("/admin/configuracion").status_code == 200


def test_rol_invalido_es_rechazado_por_el_modelo(app):
    with app.app_context():
        with pytest.raises(ValueError):
            Usuario(nombre="x", email="x@x.com", rol="superusuario")


# ---------------------------------------------------------------------------
# Administración de usuarios
# ---------------------------------------------------------------------------


def test_admin_crea_usuario(client, admin, app):
    iniciar_sesion(client)
    token = token_csrf(client, "/admin/usuarios/nuevo")
    respuesta = client.post(
        "/admin/usuarios/nuevo",
        data={
            "csrf_token": token,
            "nombre": "Laura Groomer",
            "email": "Laura@Sandia.local",
            "telefono": "3105551234",
            "rol": "groomer",
            "activo": "y",
            "password": "Clave-Groomer-1",
            "password_confirmacion": "Clave-Groomer-1",
        },
    )
    assert respuesta.status_code == 302
    with app.app_context():
        creado = db.session.execute(select(Usuario).filter_by(email="laura@sandia.local")).scalar_one()
        assert creado.rol == "groomer"
        assert creado.verificar_password("Clave-Groomer-1")
        assert creado.password_hash != "Clave-Groomer-1"


def test_no_permite_correo_duplicado(client, admin):
    iniciar_sesion(client)
    token = token_csrf(client, "/admin/usuarios/nuevo")
    respuesta = client.post(
        "/admin/usuarios/nuevo",
        data={
            "csrf_token": token,
            "nombre": "Duplicado",
            "email": "admin@prueba.local",
            "rol": "cajero",
            "password": "Clave-Dup-123",
            "password_confirmacion": "Clave-Dup-123",
        },
    )
    assert respuesta.status_code == 200
    assert "Ya existe un usuario con ese correo" in respuesta.get_data(as_text=True)


def test_no_se_puede_desactivar_el_ultimo_admin(client, admin, app):
    iniciar_sesion(client)
    token = token_csrf(client, "/admin/usuarios")
    # Se desactiva a sí mismo: prohibido.
    client.post(f"/admin/usuarios/{admin}/estado", data={"csrf_token": token})
    with app.app_context():
        assert db.session.get(Usuario, admin).activo is True
    # Segundo admin: sí se puede desactivar porque queda otro.
    otro = crear_usuario(app, email="otro@prueba.local")
    client.post(f"/admin/usuarios/{otro}/estado", data={"csrf_token": token})
    with app.app_context():
        assert db.session.get(Usuario, otro).activo is False


def test_desactivar_es_borrado_logico(client, admin, app):
    iniciar_sesion(client)
    cajero_id = crear_usuario(app, email="cajero@prueba.local", rol="cajero")
    token = token_csrf(client, "/admin/usuarios")
    client.post(f"/admin/usuarios/{cajero_id}/estado", data={"csrf_token": token})
    with app.app_context():
        usuario = db.session.get(Usuario, cajero_id)
        assert usuario is not None  # sigue existiendo
        assert usuario.activo is False


# ---------------------------------------------------------------------------
# Configuración del sistema
# ---------------------------------------------------------------------------


def test_configuracion_sembrada_por_la_migracion(app):
    with app.app_context():
        assert ConfiguracionSistema.obtener("descontar_stock_ventas") is True
        assert ConfiguracionSistema.obtener("clinica_nombre") == "Sandía"
        assert ConfiguracionSistema.obtener("clave_inexistente", "x") == "x"


def test_configuracion_se_guarda_desde_el_formulario(client, admin, app):
    iniciar_sesion(client)
    token = token_csrf(client, "/admin/configuracion")
    respuesta = client.post(
        "/admin/configuracion",
        data={
            "csrf_token": token,
            "clinica_nombre": "Sandía",
            "clinica_subtitulo": "Medicina y Spa Veterinario",
            "clinica_nit": "900.123.456-7",
            "clinica_direccion": "Calle 1 # 2-3",
            "clinica_ciudad": "Bogotá",
            "clinica_telefono": "6011234567",
            "clinica_whatsapp": "573105551234",
            "clinica_email": "hola@sandia.local",
            # descontar_stock_ventas sin marcar => False
        },
    )
    assert respuesta.status_code == 302
    with app.app_context():
        assert ConfiguracionSistema.obtener("descontar_stock_ventas") is False
        assert ConfiguracionSistema.obtener("clinica_nit") == "900.123.456-7"
        fila = db.session.execute(select(ConfiguracionSistema).filter_by(clave="clinica_nit")).scalar_one()
        assert fila.actualizado_por_id == admin
        assert fila.fecha_actualizacion is not None
        # Se restaura para no afectar otras pruebas.
        ConfiguracionSistema.establecer("descontar_stock_ventas", True)
        db.session.commit()


def test_whatsapp_de_clinica_debe_ser_numerico(client, admin):
    iniciar_sesion(client)
    token = token_csrf(client, "/admin/configuracion")
    respuesta = client.post(
        "/admin/configuracion",
        data={"csrf_token": token, "clinica_nombre": "Sandía", "clinica_whatsapp": "310-555"},
    )
    assert respuesta.status_code == 200
    assert "solo dígitos" in respuesta.get_data(as_text=True)


# ---------------------------------------------------------------------------
# Comando CLI y errores
# ---------------------------------------------------------------------------


def test_comando_crear_admin(app):
    runner = app.test_cli_runner()
    resultado = runner.invoke(args=["crear-admin", "--nombre", "Admin CLI", "--email", "CLI@Sandia.local", "--password", "Clave-CLI-123"])
    assert "creado correctamente" in resultado.output
    with app.app_context():
        usuario = db.session.execute(select(Usuario).filter_by(email="cli@sandia.local")).scalar_one()
        assert usuario.rol == "admin"
    repetido = runner.invoke(args=["crear-admin", "--nombre", "Admin CLI", "--email", "cli@sandia.local", "--password", "Clave-CLI-123"])
    assert "Ya existe" in repetido.output


def test_pagina_404_personalizada(client, admin):
    iniciar_sesion(client)
    respuesta = client.get("/esta-ruta-no-existe")
    assert respuesta.status_code == 404
    assert "Página no encontrada" in respuesta.get_data(as_text=True)


def test_endpoint_salud(client):
    respuesta = client.get("/salud")
    assert respuesta.status_code == 200
    assert respuesta.get_json() == {"estado": "ok", "base_datos": "ok"}


def test_manejador_global_hace_rollback_tras_error(app):
    """Regla de oro: tras un error, la transacción no queda envenenada.

    Sin el rollback del manejador global, cualquier consulta posterior en la
    misma petición fallaría (PendingRollbackError / InFailedSqlTransaction).
    """
    from sqlalchemy import func
    from sqlalchemy.exc import IntegrityError

    with app.test_request_context("/"):
        db.session.add(Usuario(nombre="Roto", email="roto@prueba.local", rol="cajero"))  # sin password_hash
        try:
            db.session.flush()
        except IntegrityError as exc:
            respuesta = app.make_response(app.handle_user_exception(exc))
        else:
            pytest.fail("El flush debió fallar por password_hash nulo")
        assert respuesta.status_code == 500
        assert "Algo salió mal" in respuesta.get_data(as_text=True)
        # La sesión sigue siendo usable en la misma petición:
        assert db.session.execute(select(func.count(Usuario.id))).scalar_one() == 0
