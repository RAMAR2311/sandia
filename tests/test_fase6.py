"""Pruebas automatizadas para la Fase 6: Historias Clínicas, Consultas SOAP, Vacunas y Desparasitaciones."""

from datetime import datetime, timedelta
from decimal import Decimal
import pytest
from sqlalchemy import select

from models import ConsultaMedica, DesparasitacionMascota, Mascota, Raza, RegistroPeso, Tutor, Usuario, VacunaMascota, db
from tests.conftest import PASSWORD_PRUEBA, crear_usuario
from utils import ZONA_BOGOTA, hoy_bogota, obtener_hora_bogota


def iniciar_sesion(client, email="admin@prueba.local", password=PASSWORD_PRUEBA):
    return client.post(
        "/auth/login",
        data={"email": email, "password": password, "csrf_token": token_csrf(client, "/auth/login")},
        follow_redirects=True,
    )


def token_csrf(client, url="/auth/login"):
    respuesta = client.get(url)
    data = respuesta.get_data(as_text=True)
    import re

    match = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', data)
    if not match:
        match = re.search(r'value="([^"]+)" name="csrf_token"', data)
    if not match:
        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', data)
    return match.group(1) if match else ""


def crear_tutor_y_mascota(app):
    with app.app_context():
        tutor = Tutor(
            nombre_completo="Carlos Andrés López",
            tipo_documento="CC",
            numero_documento="1020304050",
            telefono="3009876543",
        )
        db.session.add(tutor)
        db.session.flush()

        mascota = Mascota(
            tutor_id=tutor.id,
            nombre="Max",
            especie="canino",
            sexo="macho",
        )
        db.session.add(mascota)
        db.session.flush()

        reg_peso = RegistroPeso(mascota_id=mascota.id, peso_kg=Decimal("12.50"))
        db.session.add(reg_peso)
        db.session.commit()
        return tutor.id, mascota.id


def test_registrar_consulta_medica_soap(client, admin, app):
    tutor_id, mascota_id = crear_tutor_y_mascota(app)
    iniciar_sesion(client)

    token = token_csrf(client, f"/historias/mascota/{mascota_id}/consulta/nueva")
    res = client.post(
        f"/historias/mascota/{mascota_id}/consulta/nueva",
        data={
            "csrf_token": token,
            "motivo_consulta": "Revisión general y tos canina",
            "anamnesis": "El tutor indica tos seca por las noches desde hace 3 días",
            "peso_kg": "13.20",
            "temperatura_c": "38.8",
            "frecuencia_cardiaca": "110",
            "frecuencia_respiratoria": "24",
            "tllc_segundos": "2",
            "mucosas": "rosadas",
            "condicion_corporal": "3/5",
            "examen_sistemas": "Auscultación pulmonar con leves estertores roncantes bilateralmente",
            "diagnostico": "Traqueobronquitis infecciosa canina (Tos de las perreras)",
            "plan_tratamiento": "Antitusivo + Antibiótico de amplio espectro por 7 días",
            "receta_medica": "Doxiciclina 100mg - 1 tab c/24h x 7 días\nJarabe Antitusivo - 5ml c/12h x 5 días",
            "observaciones": "Revisar control en 7 días",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert "Consulta médica (SOAP) guardada correctamente" in res.get_data(as_text=True)

    with app.app_context():
        consulta = db.session.execute(select(ConsultaMedica).filter_by(mascota_id=mascota_id)).scalar_one_or_none()
        assert consulta is not None
        assert consulta.motivo_consulta == "Revisión general y tos canina"
        assert consulta.diagnostico == "Traqueobronquitis infecciosa canina (Tos de las perreras)"
        assert consulta.peso_kg == Decimal("13.20")
        assert consulta.veterinario_id == admin

        # Verificar actualización de peso de mascota
        mascota = db.session.get(Mascota, mascota_id)
        assert mascota.peso_actual.peso_kg == Decimal("13.20")


def test_registrar_vacuna_mascota(client, admin, app):
    tutor_id, mascota_id = crear_tutor_y_mascota(app)
    iniciar_sesion(client)

    hoy = hoy_bogota()
    proxima = hoy + timedelta(days=365)

    token = token_csrf(client, f"/historias/mascota/{mascota_id}/vacuna/nueva")
    res = client.post(
        f"/historias/mascota/{mascota_id}/vacuna/nueva",
        data={
            "csrf_token": token,
            "nombre_vacuna": "Múltiple Canina (DHPP)",
            "lote": "LOTE-998822",
            "laboratorio": "Zoetis",
            "dosis": "1.0 mL",
            "fecha_aplicacion": hoy.strftime("%Y-%m-%d"),
            "fecha_proxima": proxima.strftime("%Y-%m-%d"),
            "observaciones": "Aplicada en miembro posterior derecho",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200

    with app.app_context():
        vacuna = db.session.execute(select(VacunaMascota).filter_by(mascota_id=mascota_id)).scalar_one_or_none()
        assert vacuna is not None
        assert vacuna.nombre_vacuna == "Múltiple Canina (DHPP)"
        assert vacuna.estado_vencimiento == "al_dia"


def test_registrar_desparasitacion_mascota(client, admin, app):
    tutor_id, mascota_id = crear_tutor_y_mascota(app)
    iniciar_sesion(client)

    hoy = hoy_bogota()
    proxima = hoy + timedelta(days=90)

    token = token_csrf(client, f"/historias/mascota/{mascota_id}/desparasitacion/nueva")
    res = client.post(
        f"/historias/mascota/{mascota_id}/desparasitacion/nueva",
        data={
            "csrf_token": token,
            "producto": "Simparica Trio 10-20kg",
            "tipo": "mixta",
            "dosis": "1 comprimido masticable",
            "peso_kg": "12.50",
            "fecha_aplicacion": hoy.strftime("%Y-%m-%d"),
            "fecha_proxima": proxima.strftime("%Y-%m-%d"),
            "observaciones": "Tolerado adecuadamente",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200

    with app.app_context():
        desp = db.session.execute(select(DesparasitacionMascota).filter_by(mascota_id=mascota_id)).scalar_one_or_none()
        assert desp is not None
        assert desp.producto == "Simparica Trio 10-20kg"
        assert desp.tipo == "mixta"
        assert desp.estado_vencimiento == "al_dia"


def test_ficha_medica_vista(client, admin, app):
    tutor_id, mascota_id = crear_tutor_y_mascota(app)
    iniciar_sesion(client)

    res = client.get(f"/historias/mascota/{mascota_id}")
    assert res.status_code == 200
    assert "Max" in res.get_data(as_text=True)
    assert "Carlos Andrés López" in res.get_data(as_text=True)


def test_api_vacunas_pendientes(client, admin, app):
    tutor_id, mascota_id = crear_tutor_y_mascota(app)

    hoy = hoy_bogota()
    proxima_vencer = hoy + timedelta(days=5)

    with app.app_context():
        vacuna = VacunaMascota(
            mascota_id=mascota_id,
            tutor_id=tutor_id,
            veterinario_id=admin,
            nombre_vacuna="Rabia",
            fecha_aplicacion=hoy - timedelta(days=360),
            fecha_proxima=proxima_vencer,
        )
        db.session.add(vacuna)
        db.session.commit()

    iniciar_sesion(client)

    res = client.get("/api/historias/vacunas-pendientes")
    assert res.status_code == 200
    data = res.get_json()
    assert "vacunas" in data
    assert len(data["vacunas"]) == 1
    assert data["vacunas"][0]["nombre_vacuna"] == "Rabia"
    assert data["vacunas"][0]["estado_vencimiento"] == "proxima_vencer"
