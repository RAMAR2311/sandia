"""Pruebas automatizadas de la Fase 5: Spa & Peluquería de Mascotas (Grooming)."""

from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from models import (
    CitaSpa,
    Mascota,
    ServicioSpa,
    Tutor,
    Usuario,
    db,
)
from utils import ZONA_BOGOTA, hoy_bogota
from tests.conftest import crear_usuario, iniciar_sesion, token_csrf


# ---------------------------------------------------------------------------
# Helpers de prueba de Spa
# ---------------------------------------------------------------------------


def crear_servicio_spa(app, nombre="Baño y Corte Canino", precio=Decimal("45000.00"), **extra):
    with app.app_context():
        datos = {
            "nombre": nombre,
            "descripcion": "Servicio completo de estética canina",
            "duracion_minutos": 60,
            "precio_sugerido": precio,
            "especie": "canino",
            "tamano_mascota": None,
            "activo": True,
        }
        datos.update(extra)
        srv = ServicioSpa(**datos)
        db.session.add(srv)
        db.session.commit()
        return srv.id


def crear_tutor_y_mascota(app):
    with app.app_context():
        tutor = Tutor(
            nombre_completo="Carlos Andrés López",
            numero_documento="1098765432",
            telefono="3009876543",
        )
        db.session.add(tutor)
        db.session.flush()

        mascota = Mascota(
            tutor_id=tutor.id,
            nombre="Firulais",
            especie="canino",
            sexo="macho",
        )
        db.session.add(mascota)
        db.session.commit()
        return tutor.id, mascota.id


# ---------------------------------------------------------------------------
# Pruebas de Servicios y Agendamiento
# ---------------------------------------------------------------------------


def test_crud_servicios_spa(client, admin, app):
    iniciar_sesion(client)

    # 1. Crear nuevo servicio de spa
    token = token_csrf(client, "/spa/servicio/nuevo")
    res_crear = client.post(
        "/spa/servicio/nuevo",
        data={
            "csrf_token": token,
            "nombre": "Corte de Uñas y Limpieza de Oídos",
            "descripcion": "Pedicure canino y desinfección auricular",
            "duracion_minutos": "30",
            "precio_sugerido": "25000.00",
            "especie": "",
            "tamano_mascota": "",
            "activo": "y",
        },
        follow_redirects=True,
    )
    assert res_crear.status_code == 200
    assert "creado correctamente" in res_crear.get_data(as_text=True)

    with app.app_context():
        srv = db.session.execute(select(ServicioSpa).filter_by(nombre="Corte de Uñas y Limpieza de Oídos")).scalar_one_or_none()
        assert srv is not None
        assert srv.duracion_minutos == 30
        assert srv.precio_sugerido == Decimal("25000.00")
        srv_id = srv.id

    # 2. Editar servicio
    token = token_csrf(client, f"/spa/servicio/{srv_id}/editar")
    res_edit = client.post(
        f"/spa/servicio/{srv_id}/editar",
        data={
            "csrf_token": token,
            "nombre": "Corte de Uñas Premium",
            "descripcion": "Pedicure con limado eléctrico",
            "duracion_minutos": "40",
            "precio_sugerido": "30000.00",
            "especie": "canino",
            "tamano_mascota": "",
            "activo": "y",
        },
        follow_redirects=True,
    )
    assert res_edit.status_code == 200
    assert "actualizado correctamente" in res_edit.get_data(as_text=True)


def test_agendar_cita_spa(client, admin, app):
    tutor_id, mascota_id = crear_tutor_y_mascota(app)
    srv_id = crear_servicio_spa(app)
    groomer_id = crear_usuario(app, email="groomer1@prueba.local", rol="groomer", nombre="Groomer Pedro")

    iniciar_sesion(client)

    token = token_csrf(client, "/spa/cita/nueva")
    res_agendar = client.post(
        "/spa/cita/nueva",
        data={
            "csrf_token": token,
            "tutor_id": str(tutor_id),
            "mascota_id": str(mascota_id),
            "servicio_spa_id": str(srv_id),
            "groomer_id": str(groomer_id),
            "fecha": hoy_bogota().strftime("%Y-%m-%d"),
            "hora": "10:30",
            "duracion_minutos": "60",
            "notas_ingreso": "Mascota nerviosa con secador",
        },
        follow_redirects=True,
    )
    assert res_agendar.status_code == 200
    assert "Cita de grooming agendada correctamente" in res_agendar.get_data(as_text=True)

    with app.app_context():
        cita = db.session.execute(select(CitaSpa).filter_by(mascota_id=mascota_id)).scalar_one_or_none()
        assert cita is not None
        assert cita.estado == "programada"
        assert cita.groomer_id == groomer_id
        assert cita.notas_ingreso == "Mascota nerviosa con secador"


# ---------------------------------------------------------------------------
# Flujo de Estados y WhatsApp
# ---------------------------------------------------------------------------


def test_flujo_estados_cita_spa(client, admin, app):
    tutor_id, mascota_id = crear_tutor_y_mascota(app)
    srv_id = crear_servicio_spa(app)

    with app.app_context():
        cita = CitaSpa(
            tutor_id=tutor_id,
            mascota_id=mascota_id,
            servicio_spa_id=srv_id,
            fecha_hora=datetime.now(ZONA_BOGOTA),
            estado="programada",
        )
        db.session.add(cita)
        db.session.commit()
        cita_id = cita.id

    iniciar_sesion(client)

    # 1. Pasar a 'en_proceso'
    token = token_csrf(client, f"/spa/cita/{cita_id}")
    res_proc = client.post(
        f"/spa/cita/{cita_id}/estado",
        data={"csrf_token": token, "estado": "en_proceso", "notas_salida": "Comenzando baño antipulgas"},
        follow_redirects=True,
    )
    assert res_proc.status_code == 200

    with app.app_context():
        c = db.session.get(CitaSpa, cita_id)
        assert c.estado == "en_proceso"

    # 2. Pasar a 'listo_recogida'
    token = token_csrf(client, f"/spa/cita/{cita_id}")
    res_listo = client.post(
        f"/spa/cita/{cita_id}/estado",
        data={"csrf_token": token, "estado": "listo_recogida", "notas_salida": "Grooming terminado impecable"},
        follow_redirects=True,
    )
    assert res_listo.status_code == 200
    assert "¡Firulais está listo/a!" in res_listo.get_data(as_text=True)

    with app.app_context():
        c = db.session.get(CitaSpa, cita_id)
        assert c.estado == "listo_recogida"
        assert c.enlace_whatsapp is not None
        assert "3009876543" in c.enlace_whatsapp
        assert "Firulais" in c.mensaje_whatsapp


def test_api_citas_hoy_spa(client, admin, app):
    tutor_id, mascota_id = crear_tutor_y_mascota(app)
    srv_id = crear_servicio_spa(app)

    with app.app_context():
        cita = CitaSpa(
            tutor_id=tutor_id,
            mascota_id=mascota_id,
            servicio_spa_id=srv_id,
            fecha_hora=datetime.now(ZONA_BOGOTA),
            estado="programada",
        )
        db.session.add(cita)
        db.session.commit()

    iniciar_sesion(client)

    res = client.get("/api/spa/citas-hoy")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data) == 1
    assert data[0]["mascota"] == "Firulais"
    assert data[0]["estado"] == "programada"


def test_notificado_whatsapp_flag(client, admin, app):
    tutor_id, mascota_id = crear_tutor_y_mascota(app)
    srv_id = crear_servicio_spa(app)

    with app.app_context():
        cita = CitaSpa(
            tutor_id=tutor_id,
            mascota_id=mascota_id,
            servicio_spa_id=srv_id,
            fecha_hora=datetime.now(ZONA_BOGOTA),
            estado="listo_recogida",
        )
        db.session.add(cita)
        db.session.commit()
        cita_id = cita.id

    iniciar_sesion(client)

    token = token_csrf(client, f"/spa/cita/{cita_id}")
    res = client.post(f"/spa/cita/{cita_id}/notificado-wa", headers={"X-CSRFToken": token})
    assert res.status_code == 200
    assert res.get_json()["ok"] is True

    with app.app_context():
        c = db.session.get(CitaSpa, cita_id)
        assert c.notificado_whatsapp is True
