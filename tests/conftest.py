"""Configuración de pytest.

Usa la base ``TEST_DATABASE_URL`` (PostgreSQL) definida en ``.env``. Las tablas
se crean corriendo las migraciones reales de Alembic, así cada prueba verifica
también que ``flask db upgrade`` funciona desde cero.
"""

import os
import re

import pytest
from dotenv import load_dotenv
from flask_migrate import upgrade
from sqlalchemy import text

from decimal import Decimal

load_dotenv()

from app import create_app  # noqa: E402
from models import Producto, Usuario, db  # noqa: E402

PASSWORD_PRUEBA = "Clave-Segura-123"


@pytest.fixture(scope="session")
def app(tmp_path_factory):
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("Define TEST_DATABASE_URL en .env para correr las pruebas")
    if url == os.environ.get("DATABASE_URL", "").strip():
        pytest.fail("TEST_DATABASE_URL no puede ser la misma base que DATABASE_URL")

    carpeta_subidas = tmp_path_factory.mktemp("uploads")
    aplicacion = create_app(
        {"TESTING": True, "SQLALCHEMY_DATABASE_URI": url, "UPLOAD_FOLDER": str(carpeta_subidas)}
    )
    with aplicacion.app_context():
        db.drop_all()
        db.session.execute(text("DROP TABLE IF EXISTS alembic_version"))
        db.session.commit()
        upgrade()  # migraciones reales, no create_all()
    yield aplicacion
    with aplicacion.app_context():
        db.session.remove()
        db.drop_all()
        db.session.execute(text("DROP TABLE IF EXISTS alembic_version"))
        db.session.commit()


@pytest.fixture(autouse=True)
def limpiar_tablas(app):
    """Deja usuarios e intentos vacíos antes de cada prueba (la configuración se conserva)."""
    with app.app_context():
        res = db.session.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
            "AND table_name NOT IN ('configuracion_sistema', 'alembic_version', 'razas', 'plantillas_consentimientos')"
        )).scalars().all()
        if res:
            tablas = ", ".join(f'"{t}"' for t in res)
            db.session.execute(text(f"TRUNCATE TABLE {tablas} RESTART IDENTITY CASCADE"))
            db.session.execute(text("UPDATE configuracion_sistema SET actualizado_por_id = NULL"))
            db.session.commit()
    yield


@pytest.fixture
def client(app):
    return app.test_client()


def crear_usuario(app, email="admin@prueba.local", rol="admin", nombre="Usuario Prueba", activo=True, password=PASSWORD_PRUEBA):
    with app.app_context():
        usuario = Usuario(nombre=nombre, email=email, rol=rol, activo=activo)
        usuario.establecer_password(password)
        db.session.add(usuario)
        db.session.commit()
        return usuario.id


@pytest.fixture
def admin(app):
    return crear_usuario(app)


@pytest.fixture
def cajero(app):
    return crear_usuario(app, email="cajero@prueba.local", rol="cajero", nombre="Cajero Prueba")


@pytest.fixture
def recepcion(app):
    return crear_usuario(app, email="recepcion@prueba.local", rol="recepcion", nombre="Recepción Prueba")


@pytest.fixture
def groomer(app):
    return crear_usuario(app, email="groomer@prueba.local", rol="groomer", nombre="Groomer Prueba")


def token_csrf(client, ruta="/auth/login"):
    """Obtiene el token CSRF de un formulario renderizado o meta tag."""
    respuesta = client.get(ruta)
    coincidencia = re.search(rb'name="csrf_token"[^>]*value="([^"]+)"', respuesta.data)
    if not coincidencia:
        coincidencia = re.search(rb'name="csrf-token"[^>]*content="([^"]+)"', respuesta.data)
    assert coincidencia, f"No se encontró token CSRF en {ruta}"
    return coincidencia.group(1).decode()


def iniciar_sesion(client, email="admin@prueba.local", password=PASSWORD_PRUEBA):
    with client.session_transaction() as sess:
        sess.clear()
    token = token_csrf(client)
    return client.post(
        "/auth/login",
        data={"csrf_token": token, "email": email, "password": password},
        follow_redirects=False,
    )


def crear_producto(app, sku="MED-001", nombre="Amoxicilina 250mg", **extra):
    with app.app_context():
        datos = {
            "sku": sku,
            "nombre": nombre,
            "tipo": "producto",
            "categoria": "otro",
            "unidad_medida": "unidad",
            "precio_costo": Decimal("0.00"),
            "precio_minimo": Decimal("0.00"),
            "precio_sugerido": Decimal("0.00"),
            "cantidad_stock": Decimal("0.00"),
            "stock_minimo": Decimal("0.00"),
            "controla_lote": False,
            "requiere_receta": False,
            "activo": True,
        }
        datos.update(extra)
        prod = Producto(**datos)
        db.session.add(prod)
        db.session.commit()
        return prod.id
