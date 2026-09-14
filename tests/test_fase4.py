"""Pruebas automatizadas de la Fase 4: Punto de Venta (POS) y Caja."""

from datetime import timedelta
from decimal import Decimal

import pytest

from models import (
    DetalleVenta,
    Lote,
    MovimientoStock,
    PagoVenta,
    Producto,
    TurnoCaja,
    Venta,
    db,
)
from utils import hoy_bogota
from tests.conftest import crear_producto, crear_usuario, iniciar_sesion, token_csrf


def post_pos_venta(client, payload):
    token = token_csrf(client, "/pos/caja")
    return client.post("/pos/venta/procesar", json=payload, headers={"X-CSRFToken": token})


# ---------------------------------------------------------------------------
# Gestión de Turnos de Caja
# ---------------------------------------------------------------------------


def test_apertura_y_cierre_caja_con_arqueo(client, admin, app):
    iniciar_sesion(client)

    # 1. Estado inicial: sin caja abierta
    res = client.get("/pos/caja")
    assert res.status_code == 200
    assert "Sin turno activo" in res.get_data(as_text=True)

    # 2. Abrir caja con 50,000 COP
    token = token_csrf(client, "/pos/caja")
    res_abrir = client.post(
        "/pos/caja/abrir",
        data={"csrf_token": token, "monto_apertura": "50000.00", "notas": "Apertura turno mañana"},
        follow_redirects=True,
    )
    assert res_abrir.status_code == 200
    assert "Turno de caja abierto correctamente" in res_abrir.get_data(as_text=True)

    with app.app_context():
        turno = db.session.execute(select_turnos_abiertos(admin)).scalar_one_or_none()
        assert turno is not None
        assert turno.monto_apertura == Decimal("50000.00")

    # 3. Intentar abrir otra caja simultánea (debe rechazar)
    token = token_csrf(client, "/pos/caja")
    res_doble = client.post(
        "/pos/caja/abrir",
        data={"csrf_token": token, "monto_apertura": "10000.00"},
        follow_redirects=True,
    )
    assert "Ya tienes una caja abierta" in res_doble.get_data(as_text=True)

    # 4. Cerrar caja con arqueo (esperado 50.000, contado 50.000 -> cuadre $0)
    token = token_csrf(client, "/pos/caja")
    res_cierre = client.post(
        "/pos/caja/cerrar",
        data={
            "csrf_token": token,
            "monto_efectivo": "50000.00",
            "monto_nequi": "0.00",
            "monto_daviplata": "0.00",
            "monto_tarjetas": "0.00",
            "monto_transferencia": "0.00",
            "notas": "Cierre perfecto",
        },
        follow_redirects=True,
    )
    assert res_cierre.status_code == 200
    assert "Cuadre perfecto" in res_cierre.get_data(as_text=True)

    with app.app_context():
        turno_cerrado = db.session.get(TurnoCaja, 1)
        assert turno_cerrado.estado == "cerrada"
        assert turno_cerrado.diferencia == Decimal("0.00")


def select_turnos_abiertos(usuario_id):
    from sqlalchemy import select
    return select(TurnoCaja).filter_by(usuario_id=usuario_id, estado="abierta")


# ---------------------------------------------------------------------------
# Terminal POS y Cobro
# ---------------------------------------------------------------------------


def test_no_se_puede_vender_sin_caja_abierta(client, admin, app):
    iniciar_sesion(client)

    # Redirección de /pos/terminal si no hay caja abierta
    res = client.get("/pos/terminal", follow_redirects=True)
    assert "Debes abrir la caja antes de ingresar" in res.get_data(as_text=True)

    # API /pos/venta/procesar debe retornar error 400
    token = token_csrf(client, "/pos/caja")
    res_api = client.post("/pos/venta/procesar", json={"items": [{"descripcion": "Test"}], "pagos": [{"metodo_pago": "efectivo", "monto": 1000}]}, headers={"X-CSRFToken": token})
    assert res_api.status_code == 400
    assert "Debes tener un turno de caja abierto" in res_api.get_json()["error"]


def test_procesar_venta_exitosa_productos_y_servicios(client, admin, app):
    prod_id = crear_producto(app, sku="PROD-POS-01", nombre="Shampoo Canino", precio_sugerido=Decimal("20000.00"), cantidad_stock=Decimal("10.00"))

    # Abrir caja
    with app.app_context():
        t = TurnoCaja(usuario_id=admin, monto_apertura=Decimal("100000.00"), estado="abierta")
        db.session.add(t)
        db.session.commit()

    iniciar_sesion(client)

    payload = {
        "descuento_monto": 2000,
        "items": [
            {
                "producto_id": prod_id,
                "cantidad": 2,
                "precio_unitario": 20000,
                "descuento": 0,
                "tipo": "producto",
            },
            {
                "producto_id": None,
                "descripcion": "Consulta General",
                "cantidad": 1,
                "precio_unitario": 35000,
                "descuento": 0,
                "tipo": "servicio",
            },
        ],
        "pagos": [{"metodo_pago": "efectivo", "monto": 73000}],
    }

    res = post_pos_venta(client, payload)
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert "VET-" in data["numero_factura"]

    with app.app_context():
        venta = db.session.get(Venta, data["venta_id"])
        assert venta.total == Decimal("73000.00")
        assert len(venta.detalles) == 2
        assert len(venta.pagos) == 1

        # Verificar descuento de stock de 10 a 8
        prod = db.session.get(Producto, prod_id)
        assert prod.cantidad_stock == Decimal("8.00")


def test_venta_descuenta_stock_fefo_y_registra_kardex(client, admin, app):
    prod_id = crear_producto(app, sku="MED-FEFO", nombre="Vacuna Antirrábica", controla_lote=True)

    with app.app_context():
        # Lote 1: vence en 10 días, disponible 5
        lote1 = Lote(
            producto_id=prod_id,
            numero_lote="LOT-PROX",
            fecha_vencimiento=hoy_bogota() + timedelta(days=10),
            cantidad_inicial=Decimal("5.00"),
            cantidad_disponible=Decimal("5.00"),
        )
        # Lote 2: vence en 60 días, disponible 10
        lote2 = Lote(
            producto_id=prod_id,
            numero_lote="LOT-LEJOS",
            fecha_vencimiento=hoy_bogota() + timedelta(days=60),
            cantidad_inicial=Decimal("10.00"),
            cantidad_disponible=Decimal("10.00"),
        )
        t = TurnoCaja(usuario_id=admin, monto_apertura=Decimal("50000.00"), estado="abierta")
        db.session.add_all([lote1, lote2, t])
        db.session.commit()

    iniciar_sesion(client)

    # Solicitar 7 unidades (debe descontar 5 del Lote 1 y 2 del Lote 2)
    payload = {
        "descuento_monto": 0,
        "items": [
            {
                "producto_id": prod_id,
                "cantidad": 7,
                "precio_unitario": 30000,
                "tipo": "producto",
            }
        ],
        "pagos": [{"metodo_pago": "efectivo", "monto": 210000}],
    }

    res = post_pos_venta(client, payload)
    assert res.status_code == 200

    with app.app_context():
        l1 = db.session.execute(select_lote_por_numero("LOT-PROX")).scalar_one()
        l2 = db.session.execute(select_lote_por_numero("LOT-LEJOS")).scalar_one()

        assert l1.cantidad_disponible == Decimal("0.00")
        assert l2.cantidad_disponible == Decimal("8.00")

        # Verificar Kardex
        movs = db.session.execute(select_movimientos_producto(prod_id)).scalars().all()
        assert len(movs) == 2
        assert movs[0].tipo_movimiento == "venta"


def select_lote_por_numero(numero):
    from sqlalchemy import select
    return select(Lote).filter_by(numero_lote=numero)


def select_movimientos_producto(prod_id):
    from sqlalchemy import select
    return select(MovimientoStock).filter_by(producto_id=prod_id)


# ---------------------------------------------------------------------------
# Multimedio de Pago y Anulación
# ---------------------------------------------------------------------------


def test_venta_multimedio_pago(client, admin, app):
    prod_id = crear_producto(app, sku="COMBO-01", nombre="Alimento 15kg", precio_sugerido=Decimal("120000.00"), cantidad_stock=Decimal("5.00"))

    with app.app_context():
        db.session.add(TurnoCaja(usuario_id=admin, monto_apertura=Decimal("50000.00"), estado="abierta"))
        db.session.commit()

    iniciar_sesion(client)

    # Pagar $120.000 dividido: $50.000 Efectivo y $70.000 Nequi
    payload = {
        "items": [{"producto_id": prod_id, "cantidad": 1, "precio_unitario": 120000, "tipo": "producto"}],
        "pagos": [
            {"metodo_pago": "efectivo", "monto": 50000},
            {"metodo_pago": "nequi", "monto": 70000, "referencia": "M123456"},
        ],
    }

    res = post_pos_venta(client, payload)
    assert res.status_code == 200

    with app.app_context():
        venta = db.session.get(Venta, res.get_json()["venta_id"])
        assert len(venta.pagos) == 2
        pagos_map = {p.metodo_pago: p.monto for p in venta.pagos}
        assert pagos_map["efectivo"] == Decimal("50000.00")
        assert pagos_map["nequi"] == Decimal("70000.00")


def test_anular_venta_revierte_stock_y_registra_devolucion_kardex(client, admin, app):
    prod_id = crear_producto(app, sku="ANULAR-01", nombre="Pastilla Antiparasitaria", precio_sugerido=Decimal("15000.00"), cantidad_stock=Decimal("10.00"))

    with app.app_context():
        db.session.add(TurnoCaja(usuario_id=admin, monto_apertura=Decimal("50000.00"), estado="abierta"))
        db.session.commit()

    iniciar_sesion(client)

    # 1. Comprar 3 pastillas (stock baja de 10 a 7)
    res_venta = post_pos_venta(
        client,
        {
            "items": [{"producto_id": prod_id, "cantidad": 3, "precio_unitario": 15000, "tipo": "producto"}],
            "pagos": [{"metodo_pago": "efectivo", "monto": 45000}],
        },
    )
    venta_id = res_venta.get_json()["venta_id"]

    with app.app_context():
        prod = db.session.get(Producto, prod_id)
        assert prod.cantidad_stock == Decimal("7.00")

    # 2. Anular la venta
    token = token_csrf(client, f"/pos/venta/{venta_id}")
    res_anular = client.post(
        f"/pos/venta/{venta_id}/anular",
        data={"csrf_token": token, "motivo": "Cliente desistió de la compra en caja"},
        follow_redirects=True,
    )
    assert res_anular.status_code == 200
    assert "anulada correctamente" in res_anular.get_data(as_text=True)

    with app.app_context():
        venta = db.session.get(Venta, venta_id)
        assert venta.estado == "anulada"

        # Stock revertido a 10.00
        prod = db.session.get(Producto, prod_id)
        assert prod.cantidad_stock == Decimal("10.00")

        # Kardex debe incluir movimiento 'devolucion'
        movs = db.session.execute(select_movimientos_producto(prod_id)).scalars().all()
        tipos = [m.tipo_movimiento for m in movs]
        assert "devolucion" in tipos


def test_busqueda_items_api_pos(client, admin, app):
    crear_producto(app, sku="BUSCAR-POS", nombre="Collar Antipulgas Perro", precio_sugerido=Decimal("45000.00"))
    iniciar_sesion(client)

    res = client.get("/api/pos/buscar-items?q=Collar")
    assert res.status_code == 200
    data = res.get_json()
    assert len(data) == 1
    assert data[0]["sku"] == "BUSCAR-POS"
    assert data[0]["precio_sugerido"] == 45000.0


def test_impresion_ticket_venta(client, admin, app):
    with app.app_context():
        t = TurnoCaja(usuario_id=admin, monto_apertura=Decimal("50000.00"), estado="abierta")
        db.session.add(t)
        db.session.commit()

    iniciar_sesion(client)

    res_v = post_pos_venta(
        client,
        {
            "items": [{"producto_id": None, "descripcion": "Servicio Baño Canino", "cantidad": 1, "precio_unitario": 40000, "tipo": "servicio"}],
            "pagos": [{"metodo_pago": "efectivo", "monto": 40000}],
        },
    )
    venta_id = res_v.get_json()["venta_id"]

    res_ticket = client.get(f"/pos/venta/{venta_id}/ticket")
    assert res_ticket.status_code == 200
    assert "FACTURA:" in res_ticket.get_data(as_text=True)
    assert "Servicio Baño Canino" in res_ticket.get_data(as_text=True)
