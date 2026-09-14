"""Pruebas automatizadas para la Fase 8: Configuración del Sistema, Copias de Seguridad y Hardening."""

import os
import pytest

from models import ConfiguracionSistema, db
from tests.conftest import PASSWORD_PRUEBA
from utils import obtener_hora_bogota


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


def test_acceso_configuracion_admin(client, admin, app):
    iniciar_sesion(client)
    res = client.get("/admin/configuracion")
    assert res.status_code == 200
    assert "Configuración del Sistema" in res.get_data(as_text=True) or "Configuración" in res.get_data(as_text=True)


def test_guardar_configuracion_sistema(client, admin, app):
    iniciar_sesion(client)
    token = token_csrf(client, "/admin/configuracion")

    res = client.post(
        "/admin/configuracion",
        data={
            "csrf_token": token,
            "clinica_nombre": "VetCare San José",
            "clinica_subtitulo": "Centro Veterinario y Spa 24h",
            "clinica_nit": "901.888.777-1",
            "clinica_direccion": "Calle 45 # 12-34",
            "clinica_ciudad": "Bogotá",
            "clinica_telefono": "6015551234",
            "clinica_whatsapp": "573001234567",
            "clinica_email": "contacto@vetcaresanjose.com",
            "reserva_dias_maximo": "30",
            "dias_antelacion_recordatorio": "1",
            "alerta_stock_bajo": "true",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200

    with app.app_context():
        ConfiguracionSistema.invalidar_cache()
        datos = ConfiguracionSistema.datos_clinica()
        assert datos["nombre"] == "VetCare San José"
        assert datos["nit"] == "901.888.777-1"


def test_backup_cli_runner(app):
    runner = app.test_cli_runner()
    res = runner.invoke(args=["backup", "--help"])
    assert res.exit_code == 0
    assert "dump" in res.output
    assert "restore" in res.output
