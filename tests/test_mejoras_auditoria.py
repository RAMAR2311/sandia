"""Pruebas de las correcciones de la auditoría: aprobación de precio mínimo,
bloqueo de caja cerrada, interruptor de descuento de stock y pago obligatorio
antes de entregar una orden de spa.
"""

from decimal import Decimal

import pytest
from sqlalchemy import select

from models import (
    AprobacionPrecio,
    CitaSpa,
    ConfiguracionSistema,
    Mascota,
    Producto,
    ServicioSpa,
    TurnoCaja,
    Tutor,
    Venta,
    db,
)
from tests.conftest import crear_producto, crear_usuario, iniciar_sesion, token_csrf
from utils import obtener_hora_bogota


def post_pos_venta(client, payload):
    token = token_csrf(client, "/pos/caja")
    return client.post("/pos/venta/procesar", json=payload, headers={"X-CSRFToken": token})


def abrir_turno(client):
    token = token_csrf(client, "/pos/caja")
    return client.post(
        "/pos/caja/abrir",
        data={"csrf_token": token, "monto_apertura": "50000.00"},
        follow_redirects=True,
    )


def payload_venta(producto_id, precio_unitario, cantidad=1):
    return {
        "items": [
            {
                "producto_id": producto_id,
                "cantidad": cantidad,
                "precio_unitario": precio_unitario,
                "tipo": "producto",
                "descripcion": "línea de prueba",
            }
        ],
        "pagos": [{"metodo_pago": "efectivo", "monto": precio_unitario * cantidad}],
    }


@pytest.fixture
def cajero(app):
    return crear_usuario(app, email="cajero@prueba.local", rol="cajero", nombre="Cajero Prueba")


@pytest.fixture
def producto(app):
    return crear_producto(
        app,
        sku="AUD-001",
        nombre="Shampoo Antipulgas",
        precio_costo=Decimal("5000.00"),
        precio_minimo=Decimal("10000.00"),
        precio_sugerido=Decimal("15000.00"),
        cantidad_stock=Decimal("20.00"),
        controla_lote=False,
    )


# ---------------------------------------------------------------------------
# Regla 1: precio mínimo con aprobación remota
# ---------------------------------------------------------------------------


def test_cajero_no_puede_vender_bajo_minimo_sin_aprobacion(client, cajero, producto, app):
    iniciar_sesion(client, email="cajero@prueba.local")
    abrir_turno(client)

    respuesta = post_pos_venta(client, payload_venta(producto, 8000))
    datos = respuesta.get_json()

    assert respuesta.status_code == 409
    assert datos["requiere_aprobacion"] is True
    assert datos["estado_aprobacion"] == "pendiente"

    with app.app_context():
        solicitud = db.session.get(AprobacionPrecio, datos["aprobacion_id"])
        assert solicitud.estado == "pendiente"
        assert solicitud.precio_solicitado == Decimal("8000.00")
        assert solicitud.precio_original == Decimal("10000.00")
        # La venta no se registró: nada se confirmó a mitad de camino.
        assert db.session.execute(select(Venta)).first() is None


def test_admin_puede_vender_bajo_minimo_sin_restriccion(client, admin, producto, app):
    iniciar_sesion(client)
    abrir_turno(client)

    respuesta = post_pos_venta(client, payload_venta(producto, 8000))
    datos = respuesta.get_json()

    assert respuesta.status_code == 200
    assert datos["ok"] is True
    with app.app_context():
        assert db.session.execute(select(AprobacionPrecio)).first() is None


def test_flujo_completo_de_aprobacion_y_reuso_bloqueado(client, cajero, producto, app):
    iniciar_sesion(client, email="cajero@prueba.local")
    abrir_turno(client)

    bloqueo = post_pos_venta(client, payload_venta(producto, 8000)).get_json()
    aprobacion_id = bloqueo["aprobacion_id"]

    # El admin aprueba con una contraoferta distinta a la solicitada.
    with app.app_context():
        solicitud = db.session.get(AprobacionPrecio, aprobacion_id)
        solicitud.estado = "aprobado"
        solicitud.precio_aprobado = Decimal("9000.00")
        solicitud.admin_id = crear_usuario(app, email="admin2@prueba.local")
        solicitud.fecha_resolucion = obtener_hora_bogota()
        db.session.commit()

    # El cajero consulta el estado (lo que hace el sondeo del terminal).
    consulta = client.get(f"/pos/aprobaciones/{aprobacion_id}/estado")
    assert consulta.get_json()["estado"] == "aprobado"
    assert consulta.get_json()["precio_aprobado"] == 9000.0

    # Reintenta al precio EXACTO autorizado: debe pasar.
    ok = post_pos_venta(client, payload_venta(producto, 9000))
    assert ok.status_code == 200
    assert ok.get_json()["ok"] is True

    with app.app_context():
        solicitud = db.session.get(AprobacionPrecio, aprobacion_id)
        assert solicitud.estado == "utilizada"
        assert solicitud.venta_id is not None

    # Una segunda venta al mismo precio ya NO puede reutilizar esa aprobación.
    otra = post_pos_venta(client, payload_venta(producto, 9000))
    assert otra.status_code == 409
    assert otra.get_json()["aprobacion_id"] != aprobacion_id


def test_solicitud_rechazada_se_informa_sin_generar_duplicados(client, cajero, producto, app):
    iniciar_sesion(client, email="cajero@prueba.local")
    abrir_turno(client)

    bloqueo = post_pos_venta(client, payload_venta(producto, 8000)).get_json()
    with app.app_context():
        solicitud = db.session.get(AprobacionPrecio, bloqueo["aprobacion_id"])
        solicitud.estado = "rechazado"
        solicitud.motivo_rechazo = "Precio muy por debajo del costo."
        db.session.commit()

    repetido = post_pos_venta(client, payload_venta(producto, 8000))
    datos = repetido.get_json()
    assert repetido.status_code == 409
    assert datos["aprobacion_id"] == bloqueo["aprobacion_id"]  # reutiliza el registro, no crea uno nuevo
    assert datos["estado_aprobacion"] == "rechazado"
    assert "Precio muy por debajo del costo" in datos["motivo_rechazo"]

    with app.app_context():
        cantidad = db.session.execute(
            select(AprobacionPrecio).where(AprobacionPrecio.producto_id == producto)
        ).scalars().all()
        assert len(cantidad) == 1


def test_admin_aprueba_y_rechaza_desde_el_tablero(client, admin, cajero, producto, app):
    iniciar_sesion(client, email="cajero@prueba.local")
    abrir_turno(client)
    bloqueo = post_pos_venta(client, payload_venta(producto, 8000)).get_json()

    iniciar_sesion(client)  # el admin entra a resolverla
    token = token_csrf(client, "/pos/aprobaciones")
    respuesta = client.post(
        f"/pos/aprobaciones/{bloqueo['aprobacion_id']}/aprobar",
        data={"csrf_token": token, "precio_aprobado": "8500.00"},
        follow_redirects=True,
    )
    assert respuesta.status_code == 200
    with app.app_context():
        solicitud = db.session.get(AprobacionPrecio, bloqueo["aprobacion_id"])
        assert solicitud.estado == "aprobado"
        assert solicitud.precio_aprobado == Decimal("8500.00")


def test_cajero_no_accede_al_tablero_de_aprobaciones(client, cajero):
    iniciar_sesion(client, email="cajero@prueba.local")
    assert client.get("/pos/aprobaciones").status_code == 403


# ---------------------------------------------------------------------------
# Regla 2: caja cerrada bloquea el día
# ---------------------------------------------------------------------------


def test_no_se_puede_anular_venta_de_turno_cerrado(client, admin, producto, app):
    iniciar_sesion(client)
    abrir_turno(client)
    venta_id = post_pos_venta(client, payload_venta(producto, 15000)).get_json()["venta_id"]

    token = token_csrf(client, "/pos/caja")
    client.post(
        "/pos/caja/cerrar",
        data={
            "csrf_token": token,
            "monto_efectivo": "65000.00",
            "monto_nequi": "0",
            "monto_daviplata": "0",
            "monto_tarjetas": "0",
            "monto_transferencia": "0",
        },
        follow_redirects=True,
    )

    token2 = token_csrf(client, f"/pos/venta/{venta_id}")
    respuesta = client.post(
        f"/pos/venta/{venta_id}/anular",
        data={"csrf_token": token2, "motivo": "Intento de anulación tras cierre"},
        follow_redirects=True,
    )
    assert "ya fue cerrada y arqueada" in respuesta.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Venta, venta_id).estado == "completada"


# ---------------------------------------------------------------------------
# Regla 3: descuento de stock configurable
# ---------------------------------------------------------------------------


def test_toggle_descontar_stock_apagado_no_mueve_inventario(client, admin, producto, app):
    with app.app_context():
        ConfiguracionSistema.establecer("descontar_stock_ventas", False)
        db.session.commit()

    iniciar_sesion(client)
    abrir_turno(client)
    respuesta = post_pos_venta(client, payload_venta(producto, 15000, cantidad=3))
    assert respuesta.status_code == 200

    with app.app_context():
        assert db.session.get(Producto, producto).cantidad_stock == Decimal("20.00")  # sin cambios
        ConfiguracionSistema.establecer("descontar_stock_ventas", True)
        db.session.commit()


def test_toggle_descontar_stock_encendido_descuenta_normalmente(client, admin, producto, app):
    iniciar_sesion(client)
    abrir_turno(client)
    respuesta = post_pos_venta(client, payload_venta(producto, 15000, cantidad=3))
    assert respuesta.status_code == 200
    with app.app_context():
        assert db.session.get(Producto, producto).cantidad_stock == Decimal("17.00")


# ---------------------------------------------------------------------------
# Regla 6 (spa): no se entrega sin estar pagado
# ---------------------------------------------------------------------------


@pytest.fixture
def cita_spa(app):
    with app.app_context():
        tutor = Tutor(nombre_completo="Tutor Spa", telefono="3001112233")
        db.session.add(tutor)
        db.session.flush()
        mascota = Mascota(tutor_id=tutor.id, nombre="Nina", especie="canino")
        db.session.add(mascota)
        db.session.flush()
        servicio = ServicioSpa(nombre="Baño Prueba", duracion_minutos=45, precio_sugerido=Decimal("25000.00"))
        db.session.add(servicio)
        db.session.flush()
        cita = CitaSpa(mascota_id=mascota.id, tutor_id=tutor.id, servicio_spa_id=servicio.id, fecha_hora=obtener_hora_bogota())
        db.session.add(cita)
        db.session.commit()
        return {"cita_id": cita.id, "tutor_id": tutor.id, "mascota_id": mascota.id}


@pytest.fixture
def groomer(app):
    return crear_usuario(app, email="groomer@prueba.local", rol="groomer", nombre="Groomer Prueba")


def test_no_se_puede_entregar_sin_venta_vinculada(client, groomer, cita_spa):
    iniciar_sesion(client, email="groomer@prueba.local")
    token = token_csrf(client, f"/spa/cita/{cita_spa['cita_id']}")
    respuesta = client.post(
        f"/spa/cita/{cita_spa['cita_id']}/estado",
        data={"csrf_token": token, "estado": "entregado"},
        follow_redirects=True,
    )
    assert "No se puede entregar sin cobrar" in respuesta.get_data(as_text=True)


def test_vincular_venta_permite_entregar(client, admin, groomer, cita_spa, producto, app):
    iniciar_sesion(client)
    abrir_turno(client)
    venta = post_pos_venta(client, payload_venta(producto, 15000)).get_json()
    with app.app_context():
        v = db.session.get(Venta, venta["venta_id"])
        v.tutor_id = cita_spa["tutor_id"]
        db.session.commit()
        numero_factura = v.numero_factura

    iniciar_sesion(client, email="groomer@prueba.local")
    token = token_csrf(client, f"/spa/cita/{cita_spa['cita_id']}")
    vinculo = client.post(
        f"/spa/cita/{cita_spa['cita_id']}/vincular-venta",
        data={"csrf_token": token, "numero_factura": numero_factura},
        follow_redirects=True,
    )
    assert "vinculada correctamente" in vinculo.get_data(as_text=True)

    token2 = token_csrf(client, f"/spa/cita/{cita_spa['cita_id']}")
    entrega = client.post(
        f"/spa/cita/{cita_spa['cita_id']}/estado",
        data={"csrf_token": token2, "estado": "entregado"},
        follow_redirects=True,
    )
    assert "actualizado a" in entrega.get_data(as_text=True) or "Entregado" in entrega.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(CitaSpa, cita_spa["cita_id"]).estado == "entregado"
