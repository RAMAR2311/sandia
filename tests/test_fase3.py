"""Pruebas de la Fase 3: inventario, productos, variantes, lotes, kardex, alertas e importación Excel."""

import io
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import func, select

from models import (
    Lote,
    MovimientoStock,
    Producto,
    Proveedor,
    VarianteProducto,
    db,
)
from tests.conftest import crear_usuario, iniciar_sesion, token_csrf
from utils import hoy_bogota


# ---------------------------------------------------------------------------
# Helpers de prueba
# ---------------------------------------------------------------------------


def crear_proveedor(app, nombre="Distribuidora VetCol", nit="900123456-1"):
    with app.app_context():
        prov = Proveedor(nombre=nombre, nit=nit)
        db.session.add(prov)
        db.session.commit()
        return prov.id


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


def datos_producto(**cambios):
    datos = {
        "sku": "ALI-100",
        "codigo_barras": "7701234567890",
        "nombre": "Alimento Canino 10kg",
        "descripcion": "Nutrición completa",
        "categoria": "alimento",
        "tipo": "producto",
        "unidad_medida": "bulto",
        "precio_costo": "80000",
        "precio_minimo": "100000",
        "precio_sugerido": "120000",
        "stock_minimo": "5",
        "proveedor_id": "0",
        "controla_lote": "y",
        "activo": "y",
    }
    datos.update(cambios)
    return datos


# ---------------------------------------------------------------------------
# Productos y Variantes
# ---------------------------------------------------------------------------


def test_admin_crea_producto_y_normaliza_sku(client, admin, app):
    iniciar_sesion(client)
    token = token_csrf(client, "/inventario/nuevo")
    respuesta = client.post(
        "/inventario/nuevo",
        data=datos_producto(csrf_token=token, sku="  med-005  "),
    )
    assert respuesta.status_code == 302
    with app.app_context():
        prod = db.session.execute(select(Producto)).scalar_one()
        assert prod.sku == "MED-005"
        assert prod.nombre_busqueda == "alimento canino 10kg"
        assert prod.precio_sugerido == Decimal("120000.00")
        assert prod.controla_lote is True
        assert prod.creado_por_id == admin


def test_sku_duplicado_rechazado(client, admin, app):
    crear_producto(app, sku="DUPL-01")
    iniciar_sesion(client)
    token = token_csrf(client, "/inventario/nuevo")
    respuesta = client.post(
        "/inventario/nuevo",
        data=datos_producto(csrf_token=token, sku="dupl-01"),
    )
    assert respuesta.status_code == 200
    assert "Ya existe un producto o variante con este SKU" in respuesta.get_data(as_text=True)


def test_crear_variante_producto(client, admin, app):
    prod_id = crear_producto(app, sku="ROPA-01", nombre="Chaqueta Perro")
    iniciar_sesion(client)
    token = token_csrf(client, f"/inventario/{prod_id}")
    respuesta = client.post(
        f"/inventario/{prod_id}/variantes/nueva",
        data={
            "csrf_token": token,
            "nombre_variante": "Talla M",
            "sku": "ROPA-01-M",
            "precio_costo": "20000",
            "precio_sugerido": "40000",
            "activo": "y",
        },
    )
    assert respuesta.status_code == 302
    with app.app_context():
        prod = db.session.get(Producto, prod_id)
        assert len(prod.variantes) == 1
        assert prod.variantes[0].nombre_variante == "Talla M"
        assert prod.variantes[0].sku == "ROPA-01-M"


# ---------------------------------------------------------------------------
# Lotes y Kardex
# ---------------------------------------------------------------------------


def test_ingresar_lote_actualiza_stock_y_kardex(client, admin, app):
    prod_id = crear_producto(app, sku="VAC-01", nombre="Vacuna Rabia", controla_lote=True)
    iniciar_sesion(client)
    token = token_csrf(client, f"/inventario/{prod_id}")
    vencimiento = (hoy_bogota() + timedelta(days=180)).isoformat()
    respuesta = client.post(
        f"/inventario/{prod_id}/lotes/nuevo",
        data={
            "csrf_token": token,
            "numero_lote": "LOT-2026-X",
            "fecha_vencimiento": vencimiento,
            "cantidad": "50",
            "variante_id": "0",
            "proveedor_id": "0",
        },
    )
    assert respuesta.status_code == 302
    with app.app_context():
        prod = db.session.get(Producto, prod_id)
        assert prod.cantidad_stock == Decimal("50.00")
        assert len(prod.lotes) == 1
        assert prod.lotes[0].numero_lote == "LOT-2026-X"
        assert len(prod.movimientos) == 1
        mov = prod.movimientos[0]
        assert mov.tipo_movimiento == "entrada"
        assert mov.cantidad == Decimal("50.00")
        assert mov.stock_nuevo == Decimal("50.00")


def test_lote_vencido_rechazado_al_crear(client, admin, app):
    prod_id = crear_producto(app, sku="VAC-02", nombre="Vacuna Triple", controla_lote=True)
    iniciar_sesion(client)
    token = token_csrf(client, f"/inventario/{prod_id}")
    ayer = (hoy_bogota() - timedelta(days=1)).isoformat()
    client.post(
        f"/inventario/{prod_id}/lotes/nuevo",
        data={
            "csrf_token": token,
            "numero_lote": "LOT-VIEJO",
            "fecha_vencimiento": ayer,
            "cantidad": "10",
        },
    )
    with app.app_context():
        prod = db.session.get(Producto, prod_id)
        assert len(prod.lotes) == 0
        assert prod.cantidad_stock == Decimal("0.00")


def test_ajuste_stock_manual(client, admin, app):
    prod_id = crear_producto(app, sku="JUG-01", nombre="Pelota Goma", cantidad_stock=Decimal("10.00"))
    iniciar_sesion(client)
    token = token_csrf(client, f"/inventario/{prod_id}")
    respuesta = client.post(
        f"/inventario/{prod_id}/ajuste",
        data={
            "csrf_token": token,
            "tipo_movimiento": "ajuste_negativo",
            "cantidad": "2",
            "motivo": "Pelotas dañadas en exhibición",
            "variante_id": "0",
            "lote_id": "0",
        },
    )
    assert respuesta.status_code == 302
    with app.app_context():
        prod = db.session.get(Producto, prod_id)
        assert prod.cantidad_stock == Decimal("8.00")
        mov = prod.movimientos[0]
        assert mov.tipo_movimiento == "ajuste_negativo"
        assert mov.cantidad == Decimal("2.00")
        assert mov.stock_anterior == Decimal("10.00")
        assert mov.stock_nuevo == Decimal("8.00")


# ---------------------------------------------------------------------------
# Tablero de Alertas FEFO
# ---------------------------------------------------------------------------


def test_tablero_alertas_muestra_vencimientos_y_stock_bajo(client, admin, app):
    p_bajo = crear_producto(app, sku="BAJO-01", nombre="Champú Medicado", cantidad_stock=Decimal("1.00"), stock_minimo=Decimal("5.00"))
    p_lote = crear_producto(app, sku="LOTE-01", nombre="Biológico Test", controla_lote=True)
    with app.app_context():
        venc_30 = Lote(
            producto_id=p_lote,
            numero_lote="LOT-30D",
            fecha_vencimiento=hoy_bogota() + timedelta(days=15),
            cantidad_inicial=Decimal("10.00"),
            cantidad_disponible=Decimal("10.00"),
        )
        db.session.add(venc_30)
        db.session.commit()

    iniciar_sesion(client)
    html = client.get("/inventario/alertas").get_data(as_text=True)
    assert "Champú Medicado" in html
    assert "LOT-30D" in html


# ---------------------------------------------------------------------------
# Seguridad y Ocultamiento de Precios de Costo
# ---------------------------------------------------------------------------


def test_cajero_no_recibe_precio_costo_en_api(client, admin, app):
    crear_usuario(app, email="cajero@prueba.local", rol="cajero")
    prod_id = crear_producto(app, sku="COSTO-01", nombre="Jabón Anti-pulgas", precio_costo=Decimal("15000.00"), precio_sugerido=Decimal("25000.00"))

    # Como Admin: sí viene el precio_costo
    iniciar_sesion(client, email="admin@prueba.local")
    res_admin = client.get("/api/productos/buscar?q=COSTO-01").get_json()
    assert res_admin[0]["precio_costo"] == 15000.00

    # Como Cajero: precio_costo es None
    iniciar_sesion(client, email="cajero@prueba.local")
    res_cajero = client.get("/api/productos/buscar?q=COSTO-01").get_json()
    assert len(res_cajero) == 1
    assert res_cajero[0]["precio_costo"] is None
    assert res_cajero[0]["precio_sugerido"] == 25000.00


# ---------------------------------------------------------------------------
# Importación desde Excel
# ---------------------------------------------------------------------------


def test_descargar_plantilla_excel(client, admin):
    iniciar_sesion(client)
    respuesta = client.get("/inventario/plantilla-excel")
    assert respuesta.status_code == 200
    assert respuesta.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_importar_productos_desde_excel(client, admin, app):
    datos = [
        {
            "SKU": "EXCEL-01",
            "Nombre": "Desparasitante Canino",
            "Categoria": "medicamento",
            "UnidadMedida": "tableta",
            "PrecioCosto": 5000,
            "PrecioMinimo": 8000,
            "PrecioSugerido": 12000,
            "StockInicial": 30,
            "StockMinimo": 10,
            "ControlaLote": "si",
        }
    ]

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(datos).to_excel(writer, index=False)
    buffer.seek(0)

    iniciar_sesion(client)
    token = token_csrf(client, "/inventario/importar")
    respuesta = client.post(
        "/inventario/importar",
        data={"csrf_token": token, "archivo": (buffer, "inventario_test.xlsx")},
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 200
    assert "Importación finalizada" in respuesta.get_data(as_text=True)

    with app.app_context():
        prod = db.session.execute(select(Producto).filter_by(sku="EXCEL-01")).scalar_one()
        assert prod.nombre == "Desparasitante Canino"
        assert prod.cantidad_stock == Decimal("30.00")
        assert prod.controla_lote is True


# ---------------------------------------------------------------------------
# Proveedores
# ---------------------------------------------------------------------------


def test_crud_proveedor(client, admin, app):
    iniciar_sesion(client)
    token = token_csrf(client, "/inventario/proveedores/nuevo")
    respuesta = client.post(
        "/inventario/proveedores/nuevo",
        data={
            "csrf_token": token,
            "nit": "900.888.777-1",
            "nombre": "Laboratorios VetFarm",
            "telefono": "6015554433",
            "email": "contacto@vetfarm.local",
            "activo": "y",
        },
    )
    assert respuesta.status_code == 302
    with app.app_context():
        prov = db.session.execute(select(Proveedor)).scalar_one()
        assert prov.nombre == "Laboratorios VetFarm"
        assert prov.nit == "900.888.777-1"
        assert prov.email == "contacto@vetfarm.local"
