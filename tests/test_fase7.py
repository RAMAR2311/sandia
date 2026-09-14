"""Pruebas automatizadas para la Fase 7: Reportes, Métricas y Tableros."""

from decimal import Decimal
import pytest

from models import Producto, TurnoCaja, Venta, db
from tests.conftest import PASSWORD_PRUEBA, crear_producto, crear_usuario
from utils import hoy_bogota


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


def test_dashboard_reportes_acceso(client, admin, app):
    iniciar_sesion(client)
    res = client.get("/reportes/")
    assert res.status_code == 200
    assert "Reportes &amp; Métricas Ejecutivas" in res.get_data(as_text=True) or "Reportes" in res.get_data(as_text=True)


def test_reporte_ventas_y_filtro_periodo(client, admin, app):
    iniciar_sesion(client)
    res = client.get("/reportes/ventas?periodo=mes")
    assert res.status_code == 200
    assert "Resumen Financiero" in res.get_data(as_text=True)


def test_reporte_inventario(client, admin, app):
    crear_producto(app, sku="REP-INV-01", nombre="Alimento Perro Adulto", precio_costo=Decimal("80000.00"), precio_sugerido=Decimal("110000.00"), cantidad_stock=Decimal("5.00"))
    iniciar_sesion(client)

    res = client.get("/reportes/inventario")
    assert res.status_code == 200
    assert "Alimento Perro Adulto" in res.get_data(as_text=True)


def test_api_dashboard_kpis(client, admin, app):
    iniciar_sesion(client)
    res = client.get("/api/reportes/dashboard-kpis")
    assert res.status_code == 200
    data = res.get_json()
    assert "ventas_hoy" in data
    assert "citas_hoy" in data
    assert "consultas_hoy" in data
