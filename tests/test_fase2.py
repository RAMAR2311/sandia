"""Pruebas de la Fase 2: tutores, mascotas, fotos, curva de peso, línea de tiempo y razas."""

import io
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import func, select

from models import Mascota, Raza, RegistroPeso, Tutor, db
from tests.conftest import crear_usuario, iniciar_sesion, token_csrf
from utils import edad_en_meses, edad_texto, fecha_desde_edad, normalizar_texto

# ---------------------------------------------------------------------------
# Ayudas
# ---------------------------------------------------------------------------


def crear_tutor(app, nombre="María Muñoz", telefono="3105551234", documento=None, **extra):
    with app.app_context():
        tutor = Tutor(nombre_completo=nombre, telefono=telefono, numero_documento=documento, **extra)
        if documento:
            tutor.tipo_documento = "CC"
        db.session.add(tutor)
        db.session.commit()
        return tutor.id


def crear_mascota(app, tutor_id, nombre="Firulais", especie="canino", **extra):
    with app.app_context():
        mascota = Mascota(tutor_id=tutor_id, nombre=nombre, especie=especie, **extra)
        db.session.add(mascota)
        db.session.commit()
        return mascota.id


def raza_id(app, especie, nombre):
    with app.app_context():
        return db.session.execute(select(Raza.id).where(Raza.especie == especie, Raza.nombre == nombre)).scalar_one()


def imagen_prueba(formato="PNG", tamano=(1600, 1200), color=(229, 57, 53)):
    imagen = Image.new("RGB", tamano, color)
    buffer = io.BytesIO()
    imagen.save(buffer, format=formato)
    buffer.seek(0)
    return buffer


def datos_mascota(tutor_id, **cambios):
    datos = {
        "tutor_id": str(tutor_id),
        "nombre": "Firulais",
        "especie": "canino",
        "raza_id": "0",
        "sexo": "macho",
        "conoce_fecha": "y",
        "fecha_nacimiento": "2024-06-10",
        "tamano": "mediano",
        "color": "Café",
        "microchip": "",
        "alergias": "",
        "condiciones_preexistentes": "",
    }
    datos.update(cambios)
    return datos


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------


def test_normalizar_texto():
    assert normalizar_texto("  Muñoz   PÉREZ ") == "munoz perez"
    assert normalizar_texto("Ñoño") == "nono"
    assert normalizar_texto(None) == ""


def test_edad_texto():
    hoy = date(2026, 9, 14)
    assert edad_texto(date(2024, 6, 10), hoy) == "2 años 3 meses"
    assert edad_texto(date(2025, 9, 14), hoy) == "1 año"
    assert edad_texto(date(2026, 4, 1), hoy) == "5 meses"
    assert edad_texto(date(2026, 8, 25), hoy) == "2 semanas"
    assert edad_texto(date(2026, 9, 13), hoy) == "1 día"
    assert edad_texto(date(2027, 1, 1), hoy) == ""
    assert edad_texto(None) == ""


def test_fecha_desde_edad_y_meses():
    hoy = date(2026, 9, 14)
    assert fecha_desde_edad(2, 3, hoy) == date(2024, 6, 14)
    assert fecha_desde_edad(0, 0, date(2026, 3, 31)) == date(2026, 3, 31)
    assert edad_en_meses(fecha_desde_edad(2, 3, hoy), hoy) == 27


def test_migracion_siembra_razas(app):
    with app.app_context():
        for especie in ("canino", "felino", "ave", "roedor", "otro"):
            cantidad = db.session.execute(select(func.count(Raza.id)).where(Raza.especie == especie)).scalar_one()
            assert cantidad > 0, especie
        assert raza_id(app, "canino", "Criollo / Mestizo")


# ---------------------------------------------------------------------------
# Tutores
# ---------------------------------------------------------------------------


def test_recepcion_crea_tutor_y_normaliza_datos(client, recepcion, app):
    iniciar_sesion(client, email="recepcion@prueba.local")
    token = token_csrf(client, "/tutores/nuevo")
    respuesta = client.post(
        "/tutores/nuevo",
        data={
            "csrf_token": token,
            "tipo_documento": "CC",
            "numero_documento": " 1.234.567 ",
            "nombre_completo": "  Ana   María  Muñoz ",
            "telefono": "310 555 1234",
            "whatsapp": "",
            "email": "ANA@Correo.com",
            "acepta_recordatorios": "y",
        },
    )
    assert respuesta.status_code == 302
    with app.app_context():
        tutor = db.session.execute(select(Tutor)).scalar_one()
        assert tutor.nombre_completo == "Ana María Muñoz"
        assert tutor.nombre_busqueda == "ana maria munoz"
        assert tutor.numero_documento == "1.234.567"
        assert tutor.email == "ana@correo.com"
        assert tutor.whatsapp is None
        assert tutor.whatsapp_efectivo == "573105551234"  # cae al teléfono
        assert tutor.enlace_whatsapp("Hola").startswith("https://wa.me/573105551234?text=Hola")
        assert tutor.creado_por_id == recepcion


def test_documento_duplicado_rechazado(client, admin, app):
    crear_tutor(app, documento="1001")
    iniciar_sesion(client)
    token = token_csrf(client, "/tutores/nuevo")
    respuesta = client.post(
        "/tutores/nuevo",
        data={"csrf_token": token, "tipo_documento": "CC", "numero_documento": "1001", "nombre_completo": "Otro"},
    )
    assert respuesta.status_code == 200
    assert "Ya hay un tutor registrado con ese documento" in respuesta.get_data(as_text=True)


def test_busqueda_de_tutores_tolera_tildes_y_telefono(client, admin, app):
    crear_tutor(app, nombre="José Pérez Gómez", telefono="3201112233")
    crear_tutor(app, nombre="Laura Rincón", telefono="3009998877")
    iniciar_sesion(client)
    html = client.get("/tutores/?q=jose+perez").get_data(as_text=True)
    assert "José Pérez Gómez" in html and "Laura Rincón" not in html
    html = client.get("/tutores/?q=999").get_data(as_text=True)
    assert "Laura Rincón" in html and "José Pérez" not in html
    html = client.get("/tutores/?q=ZZZZ").get_data(as_text=True)
    assert "Ningún tutor coincide" in html


def test_cajero_ve_pero_no_edita_tutores(client, cajero, app):
    tutor = crear_tutor(app)
    iniciar_sesion(client, email="cajero@prueba.local")
    assert client.get("/tutores/").status_code == 200
    assert client.get(f"/tutores/{tutor}").status_code == 200
    assert client.get("/tutores/nuevo").status_code == 403
    assert client.get(f"/tutores/{tutor}/editar").status_code == 403
    html = client.get(f"/tutores/{tutor}").get_data(as_text=True)
    assert "Nuevo tutor" not in html and "Desactivar tutor" not in html


def test_desactivar_tutor_es_logico(client, admin, app):
    tutor = crear_tutor(app)
    iniciar_sesion(client)
    token = token_csrf(client, f"/tutores/{tutor}")
    respuesta = client.post(f"/tutores/{tutor}/estado", data={"csrf_token": token})
    assert respuesta.status_code == 302
    with app.app_context():
        assert db.session.get(Tutor, tutor).activo is False
    assert "María Muñoz" not in client.get("/tutores/").get_data(as_text=True)
    assert "María Muñoz" in client.get("/tutores/?estado=inactivos").get_data(as_text=True)


# ---------------------------------------------------------------------------
# Mascotas
# ---------------------------------------------------------------------------


def test_crear_mascota_con_fecha_exacta_y_raza(client, admin, app):
    tutor = crear_tutor(app)
    labrador = raza_id(app, "canino", "Labrador Retriever")
    iniciar_sesion(client)
    token = token_csrf(client, f"/mascotas/nueva?tutor_id={tutor}")
    respuesta = client.post("/mascotas/nueva", data=datos_mascota(tutor, csrf_token=token, raza_id=str(labrador)))
    assert respuesta.status_code == 302
    with app.app_context():
        mascota = db.session.execute(select(Mascota)).scalar_one()
        assert mascota.tutor_id == tutor
        assert mascota.raza.nombre == "Labrador Retriever"
        assert mascota.fecha_nacimiento == date(2024, 6, 10)
        assert mascota.fecha_nacimiento_estimada is False
        assert mascota.nombre_busqueda == "firulais"
        assert mascota.creado_por_id == admin
        assert mascota.tamano == "mediano"


def test_crear_mascota_con_edad_aproximada(client, admin, app):
    tutor = crear_tutor(app)
    iniciar_sesion(client)
    token = token_csrf(client, "/mascotas/nueva")
    datos = datos_mascota(tutor, csrf_token=token, nombre="Michi", especie="felino", fecha_nacimiento="", edad_anios="2", edad_meses="3")
    del datos["conoce_fecha"]  # interruptor apagado: edad aproximada
    respuesta = client.post("/mascotas/nueva", data=datos)
    assert respuesta.status_code == 302
    with app.app_context():
        mascota = db.session.execute(select(Mascota)).scalar_one()
        assert mascota.fecha_nacimiento_estimada is True
        assert edad_en_meses(mascota.fecha_nacimiento) == 27
        assert mascota.edad.startswith("≈ 2 años")


def test_raza_de_otra_especie_rechazada(client, admin, app):
    tutor = crear_tutor(app)
    persa = raza_id(app, "felino", "Persa")
    iniciar_sesion(client)
    token = token_csrf(client, "/mascotas/nueva")
    respuesta = client.post("/mascotas/nueva", data=datos_mascota(tutor, csrf_token=token, raza_id=str(persa)))
    assert respuesta.status_code == 200
    assert "no corresponde a la especie" in respuesta.get_data(as_text=True)


def test_mascota_requiere_tutor_activo(client, admin, app):
    tutor = crear_tutor(app, activo=False)
    iniciar_sesion(client)
    token = token_csrf(client, "/mascotas/nueva")
    respuesta = client.post("/mascotas/nueva", data=datos_mascota(tutor, csrf_token=token))
    assert respuesta.status_code == 200
    assert "Selecciona un tutor activo" in respuesta.get_data(as_text=True)


def test_fecha_de_nacimiento_futura_rechazada(client, admin, app):
    tutor = crear_tutor(app)
    iniciar_sesion(client)
    token = token_csrf(client, "/mascotas/nueva")
    futura = (date.today() + timedelta(days=30)).isoformat()
    respuesta = client.post("/mascotas/nueva", data=datos_mascota(tutor, csrf_token=token, fecha_nacimiento=futura))
    assert respuesta.status_code == 200
    assert "no puede ser futura" in respuesta.get_data(as_text=True)


def test_ficha_muestra_tutor_datos_y_linea_de_tiempo(client, admin, app):
    tutor = crear_tutor(app, nombre="Carlos Rojas", telefono="3115550000")
    mascota = crear_mascota(app, tutor, nombre="Rocky", tamano="grande", alergias="Pollo", fecha_nacimiento=date(2020, 1, 15))
    iniciar_sesion(client)
    html = client.get(f"/mascotas/{mascota}").get_data(as_text=True)
    assert "Rocky" in html and "Carlos Rojas" in html
    assert "wa.me/573115550000" in html
    assert "Registro en el sistema" in html
    assert "Alergias:</strong> Pollo" in html
    assert "Grande" in html
    listado = client.get("/mascotas/?q=rocky").get_data(as_text=True)
    assert "Rocky" in listado and "Carlos Rojas" in listado
    assert "Ninguna mascota coincide" in client.get("/mascotas/?q=zzz").get_data(as_text=True)
    assert "Rocky" in client.get("/mascotas/?especie=canino").get_data(as_text=True)
    assert "Rocky" not in client.get("/mascotas/?especie=felino").get_data(as_text=True)


def test_registrar_peso_alimenta_curva_y_linea_de_tiempo(client, admin, app):
    tutor = crear_tutor(app)
    mascota = crear_mascota(app, tutor)
    iniciar_sesion(client)
    token = token_csrf(client, f"/mascotas/{mascota}")
    ayer = (date.today() - timedelta(days=1)).isoformat()
    assert client.post(f"/mascotas/{mascota}/peso", data={"csrf_token": token, "peso_kg": "4.5", "fecha": ayer}).status_code == 302
    assert client.post(f"/mascotas/{mascota}/peso", data={"csrf_token": token, "peso_kg": "5.25"}).status_code == 302
    with app.app_context():
        actual = db.session.get(Mascota, mascota)
        assert len(actual.registros_peso) == 2
        assert actual.peso_actual.peso_kg == Decimal("5.25")
        assert actual.registros_peso[0].peso_kg == Decimal("4.50")
        assert actual.registros_peso[0].registrado_por_id == admin
    html = client.get(f"/mascotas/{mascota}").get_data(as_text=True)
    assert "5,25 kg" in html and "4,5 kg" in html
    assert "Peso registrado: 5,25 kg" in html
    assert '"peso": 5.25' in html  # datos para la gráfica


def test_peso_invalido_rechazado(client, admin, app):
    tutor = crear_tutor(app)
    mascota = crear_mascota(app, tutor)
    iniciar_sesion(client)
    token = token_csrf(client, f"/mascotas/{mascota}")
    client.post(f"/mascotas/{mascota}/peso", data={"csrf_token": token, "peso_kg": "0"})
    client.post(f"/mascotas/{mascota}/peso", data={"csrf_token": token, "peso_kg": "abc"})
    with app.app_context():
        assert db.session.execute(select(func.count(RegistroPeso.id))).scalar_one() == 0


def test_solo_admin_elimina_pesos(client, app):
    crear_usuario(app, email="vet@prueba.local", rol="veterinario")
    tutor = crear_tutor(app)
    mascota = crear_mascota(app, tutor)
    with app.app_context():
        db.session.add(RegistroPeso(mascota_id=mascota, peso_kg=Decimal("44")))
        db.session.commit()
        peso_id = db.session.execute(select(RegistroPeso.id)).scalar_one()
    iniciar_sesion(client, email="vet@prueba.local")
    token = token_csrf(client, f"/mascotas/{mascota}")
    assert client.post(f"/mascotas/{mascota}/peso/{peso_id}/eliminar", data={"csrf_token": token}).status_code == 403


def test_subir_foto_real_genera_miniatura(client, admin, app):
    tutor = crear_tutor(app)
    mascota = crear_mascota(app, tutor)
    iniciar_sesion(client)
    token = token_csrf(client, f"/mascotas/{mascota}")
    respuesta = client.post(
        f"/mascotas/{mascota}/foto",
        data={"csrf_token": token, "foto": (imagen_prueba(), "IMG_2024 (1).PNG")},
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 302
    with app.app_context():
        actual = db.session.get(Mascota, mascota)
        assert actual.foto and actual.foto.endswith(".jpg") and "IMG" not in actual.foto
        carpeta = Path(app.config["UPLOAD_FOLDER"]) / "mascotas"
        grande = Image.open(carpeta / actual.foto)
        mini = Image.open(carpeta / f"mini_{actual.foto}")
        assert max(grande.size) <= 1024
        assert max(mini.size) <= 300
    html = client.get(f"/mascotas/{mascota}").get_data(as_text=True)
    assert f"uploads/mascotas/mini_{actual.foto}" in html


def test_foto_con_extension_invalida_o_falsa_rechazada(client, admin, app):
    tutor = crear_tutor(app)
    mascota = crear_mascota(app, tutor)
    iniciar_sesion(client)
    token = token_csrf(client, f"/mascotas/{mascota}")
    client.post(
        f"/mascotas/{mascota}/foto",
        data={"csrf_token": token, "foto": (io.BytesIO(b"<script>alert(1)</script>"), "malo.html")},
        content_type="multipart/form-data",
    )
    client.post(
        f"/mascotas/{mascota}/foto",
        data={"csrf_token": token, "foto": (io.BytesIO(b"esto no es una imagen"), "falsa.jpg")},
        content_type="multipart/form-data",
    )
    with app.app_context():
        assert db.session.get(Mascota, mascota).foto is None
        carpeta = Path(app.config["UPLOAD_FOLDER"]) / "mascotas"
        assert not list(carpeta.glob("*.html"))


def test_fallecimiento_y_reactivacion(client, admin, app):
    tutor = crear_tutor(app)
    mascota = crear_mascota(app, tutor)
    iniciar_sesion(client)
    token = token_csrf(client, f"/mascotas/{mascota}")
    respuesta = client.post(f"/mascotas/{mascota}/fallecimiento", data={"csrf_token": token, "fecha_fallecimiento": date.today().isoformat()})
    assert respuesta.status_code == 302
    with app.app_context():
        actual = db.session.get(Mascota, mascota)
        assert actual.fallecido is True and actual.fecha_fallecimiento == date.today()
    html = client.get(f"/mascotas/{mascota}").get_data(as_text=True)
    assert "Fallecido/a el" in html and "Registrar peso" not in html
    assert "Firulais" not in client.get("/mascotas/").get_data(as_text=True)
    assert client.post(f"/mascotas/{mascota}/fallecimiento/deshacer", data={"csrf_token": token}).status_code == 302
    with app.app_context():
        assert db.session.get(Mascota, mascota).fallecido is False


def test_groomer_lee_pero_no_edita_mascotas(client, groomer, app):
    tutor = crear_tutor(app)
    mascota = crear_mascota(app, tutor)
    iniciar_sesion(client, email="groomer@prueba.local")
    assert client.get("/mascotas/").status_code == 200
    assert client.get(f"/mascotas/{mascota}").status_code == 200
    assert client.get(f"/mascotas/{mascota}/editar").status_code == 403
    token = token_csrf(client, f"/mascotas/{mascota}")
    assert client.post(f"/mascotas/{mascota}/peso", data={"csrf_token": token, "peso_kg": "3"}).status_code == 403


def test_editar_mascota_cambia_tutor_y_conserva_foto(client, admin, app):
    tutor_a = crear_tutor(app, nombre="Tutor A")
    tutor_b = crear_tutor(app, nombre="Tutor B", telefono="3000000000")
    mascota = crear_mascota(app, tutor_a, foto="existente.jpg")
    iniciar_sesion(client)
    token = token_csrf(client, f"/mascotas/{mascota}/editar")
    respuesta = client.post(
        f"/mascotas/{mascota}/editar",
        data=datos_mascota(tutor_b, csrf_token=token, nombre="Firu", especie="canino", tamano=""),
    )
    assert respuesta.status_code == 302
    with app.app_context():
        actual = db.session.get(Mascota, mascota)
        assert actual.tutor_id == tutor_b and actual.nombre == "Firu"
        assert actual.foto == "existente.jpg"
        assert actual.tamano is None


# ---------------------------------------------------------------------------
# API JSON
# ---------------------------------------------------------------------------


def test_api_buscar_tutores_y_mascotas(client, admin, app):
    tutor = crear_tutor(app, nombre="Pedro Núñez", telefono="3123456789", documento="55")
    crear_mascota(app, tutor, nombre="Nala", especie="felino")
    iniciar_sesion(client)
    datos = client.get("/api/tutores/buscar?q=nunez").get_json()
    assert len(datos) == 1 and datos[0]["nombre"] == "Pedro Núñez"
    assert datos[0]["mascotas"][0]["nombre"] == "Nala"
    assert client.get("/api/tutores/buscar?q=345").get_json()[0]["id"] == tutor
    assert client.get("/api/tutores/buscar?q=p").get_json() == []  # mínimo 2 caracteres
    mascotas = client.get("/api/mascotas/buscar?q=nala").get_json()
    assert mascotas[0]["tutor"]["nombre"] == "Pedro Núñez" and mascotas[0]["emoji"] == "🐱"
    assert client.get("/api/mascotas/buscar?q=pedro").get_json()[0]["nombre"] == "Nala"  # también por tutor
    razas = client.get("/api/razas?especie=ave").get_json()
    assert any(r["nombre"] == "Canario" for r in razas)
    assert client.get("/api/razas?especie=dragon").status_code == 400


def test_api_exige_sesion(client):
    respuesta = client.get("/api/tutores/buscar?q=ana", headers={"Accept": "application/json"})
    assert respuesta.status_code in (302, 401)


# ---------------------------------------------------------------------------
# Catálogo de razas
# ---------------------------------------------------------------------------


def test_admin_gestiona_razas(client, admin, app):
    iniciar_sesion(client)
    token = token_csrf(client, "/admin/razas/nueva")
    respuesta = client.post("/admin/razas/nueva", data={"csrf_token": token, "especie": "canino", "nombre": "  Xoloitzcuintle ", "activo": "y"})
    assert respuesta.status_code == 302
    repetida = client.post("/admin/razas/nueva", data={"csrf_token": token, "especie": "canino", "nombre": "xoloitzcuintle", "activo": "y"})
    assert "ya existe" in repetida.get_data(as_text=True)
    nueva = raza_id(app, "canino", "Xoloitzcuintle")
    respuesta = client.post(f"/admin/razas/{nueva}/editar", data={"csrf_token": token, "especie": "canino", "nombre": "Xoloitzcuintle"})
    assert respuesta.status_code == 302
    with app.app_context():
        raza = db.session.get(Raza, nueva)
        assert raza.activo is False  # el switch sin marcar la desactiva
        db.session.delete(raza)
        db.session.commit()
    assert not any(r["nombre"] == "Xoloitzcuintle" for r in client.get("/api/razas?especie=canino").get_json())


def test_razas_solo_admin(client, recepcion):
    iniciar_sesion(client, email="recepcion@prueba.local")
    assert client.get("/admin/razas").status_code == 403
