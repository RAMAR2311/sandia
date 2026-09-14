"""Sondeo general: visita cada ruta GET registrada y confirma que nada truena con 500.

No sustituye a las pruebas específicas de cada fase (esas verifican reglas de
negocio); esto es una red de seguridad barata para detectar errores de plomería
— nombres de columna equivocados, variables de plantilla faltantes, imports
rotos — que un test unitario aislado con mocks no vería porque nunca ejercita
la ruta real de punta a punta contra una base de datos real.
"""

from datetime import timedelta
from decimal import Decimal

import pytest

from models import (
    CitaSpa,
    ConsultaMedica,
    DesparasitacionMascota,
    Lote,
    Mascota,
    PagoVenta,
    Producto,
    Proveedor,
    ServicioSpa,
    TurnoCaja,
    Tutor,
    VacunaMascota,
    Venta,
    db,
)
from tests.conftest import crear_usuario, iniciar_sesion
from utils import hoy_bogota, obtener_hora_bogota


@pytest.fixture
def mundo(app, admin):
    """Un ejemplar de (casi) cada entidad, para que ninguna ficha se vea vacía."""
    with app.app_context():
        tutor = Tutor(nombre_completo="Tutor de Prueba", telefono="3105551234")
        db.session.add(tutor)
        db.session.flush()

        mascota = Mascota(tutor_id=tutor.id, nombre="Firulais", especie="canino", tamano="mediano")
        db.session.add(mascota)
        db.session.flush()

        proveedor = Proveedor(nombre="Proveedor de Prueba")
        db.session.add(proveedor)
        db.session.flush()

        producto = Producto(
            sku="SMK-001",
            nombre="Producto de Humo",
            tipo="producto",
            categoria="otro",
            unidad_medida="unidad",
            precio_costo=Decimal("1000.00"),
            precio_minimo=Decimal("1500.00"),
            precio_sugerido=Decimal("2000.00"),
            cantidad_stock=Decimal("10.00"),
            controla_lote=True,
            proveedor_id=proveedor.id,
        )
        db.session.add(producto)
        db.session.flush()

        lote = Lote(
            producto_id=producto.id,
            numero_lote="L-001",
            fecha_vencimiento=hoy_bogota() + timedelta(days=180),
            cantidad_inicial=Decimal("10.00"),
            cantidad_disponible=Decimal("10.00"),
        )
        db.session.add(lote)

        servicio = ServicioSpa(nombre="Baño de Prueba", duracion_minutos=60, precio_sugerido=Decimal("30000.00"))
        db.session.add(servicio)
        db.session.flush()

        cita = CitaSpa(
            mascota_id=mascota.id,
            tutor_id=tutor.id,
            servicio_spa_id=servicio.id,
            fecha_hora=obtener_hora_bogota(),
        )
        db.session.add(cita)

        consulta = ConsultaMedica(
            mascota_id=mascota.id,
            tutor_id=tutor.id,
            veterinario_id=admin,
            motivo_consulta="Control de rutina",
            diagnostico="Sano",
            plan_tratamiento="Ninguno",
        )
        db.session.add(consulta)

        vacuna = VacunaMascota(
            mascota_id=mascota.id,
            tutor_id=tutor.id,
            nombre_vacuna="Polivalente",
            fecha_aplicacion=hoy_bogota(),
            fecha_proxima=hoy_bogota() + timedelta(days=5),
        )
        db.session.add(vacuna)

        despara = DesparasitacionMascota(
            mascota_id=mascota.id,
            tutor_id=tutor.id,
            producto="Drontal",
            fecha_aplicacion=hoy_bogota(),
        )
        db.session.add(despara)

        turno = TurnoCaja(usuario_id=admin, monto_apertura=Decimal("50000.00"))
        db.session.add(turno)
        db.session.flush()

        venta = Venta(
            numero_factura="VET-SMOKE-0001",
            turno_caja_id=turno.id,
            tutor_id=tutor.id,
            mascota_id=mascota.id,
            usuario_id=admin,
            subtotal=Decimal("30000.00"),
            total=Decimal("30000.00"),
        )
        db.session.add(venta)
        db.session.flush()
        db.session.add(PagoVenta(venta_id=venta.id, metodo_pago="efectivo", monto=Decimal("30000.00")))

        db.session.commit()

        return {
            "tutor_id": tutor.id,
            "mascota_id": mascota.id,
            "producto_id": producto.id,
            "proveedor_id": proveedor.id,
            "servicio_id": servicio.id,
            "cita_id": cita.id,
            "consulta_id": consulta.id,
            "venta_id": venta.id,
        }


def _get_no_debe_ser_500(client, url):
    respuesta = client.get(url)
    assert respuesta.status_code != 500, f"{url} respondió 500:\n{respuesta.get_data(as_text=True)[:2000]}"
    return respuesta


def test_rutas_get_sin_parametros_como_admin(client, admin):
    """Cada ruta GET sin parámetros de URL responde algo distinto de 500 para el admin."""
    iniciar_sesion(client)
    rutas = [
        "/", "/salud",
        "/admin/usuarios", "/admin/usuarios/nuevo", "/admin/configuracion", "/admin/razas", "/admin/razas/nueva",
        "/tutores/", "/tutores/nuevo",
        "/mascotas/", "/mascotas/nueva",
        "/historias/",
        "/inventario/", "/inventario/nuevo", "/inventario/alertas", "/inventario/importar",
        "/inventario/plantilla-excel", "/inventario/proveedores", "/inventario/proveedores/nuevo",
        "/pos/caja", "/pos/terminal", "/pos/ventas", "/pos/aprobaciones", "/pos/aprobaciones/json",
        "/reportes/", "/reportes/ventas", "/reportes/inventario",
        "/spa/servicios", "/spa/servicio/nuevo", "/spa/agenda", "/spa/cita/nueva",
        "/auth/cambiar-password",
        "/api/tutores/buscar?q=ta", "/api/mascotas/buscar?q=fi", "/api/razas?especie=canino",
        "/api/productos/buscar?q=a", "/api/pos/buscar-items?q=a", "/api/pos/tutores-mascotas?q=tut",
        "/api/pos/tutores-mascotas?q=310", "/api/spa/citas-hoy", "/api/historias/vacunas-pendientes",
        "/api/reportes/dashboard-kpis",
    ]
    for url in rutas:
        _get_no_debe_ser_500(client, url)


def test_rutas_get_con_ids_como_admin(client, admin, mundo):
    iniciar_sesion(client)
    rutas = [
        f"/admin/usuarios/{admin}/editar",
        f"/tutores/{mundo['tutor_id']}",
        f"/tutores/{mundo['tutor_id']}/editar",
        f"/mascotas/{mundo['mascota_id']}",
        f"/mascotas/{mundo['mascota_id']}/editar",
        f"/historias/mascota/{mundo['mascota_id']}",
        f"/historias/mascota/{mundo['mascota_id']}/consulta/nueva",
        f"/historias/mascota/{mundo['mascota_id']}/vacuna/nueva",
        f"/historias/mascota/{mundo['mascota_id']}/desparasitacion/nueva",
        f"/historias/consulta/{mundo['consulta_id']}",
        f"/inventario/{mundo['producto_id']}",
        f"/inventario/{mundo['producto_id']}/editar",
        f"/inventario/proveedores/{mundo['proveedor_id']}/editar",
        f"/pos/venta/{mundo['venta_id']}",
        f"/pos/venta/{mundo['venta_id']}/ticket",
        f"/spa/servicio/{mundo['servicio_id']}/editar",
        f"/spa/cita/{mundo['cita_id']}",
    ]
    for url in rutas:
        _get_no_debe_ser_500(client, url)


@pytest.mark.parametrize(
    "rol, email, rutas_permitidas, rutas_prohibidas",
    [
        ("cajero", "cajero@prueba.local", ["/pos/caja"], ["/historias/", "/reportes/", "/inventario/nuevo", "/admin/usuarios"]),
        ("veterinario", "vet@prueba.local", ["/historias/"], ["/pos/terminal", "/reportes/", "/admin/usuarios"]),
        ("groomer", "groomer@prueba.local", ["/spa/agenda"], ["/spa/servicios", "/historias/", "/pos/terminal", "/admin/usuarios"]),
        ("recepcion", "recepcion@prueba.local", ["/tutores/", "/mascotas/"], ["/historias/", "/pos/terminal", "/reportes/", "/admin/usuarios"]),
    ],
)
def test_matriz_de_permisos_por_rol(client, app, rol, email, rutas_permitidas, rutas_prohibidas):
    crear_usuario(app, email=email, rol=rol, nombre=f"{rol} Prueba")
    iniciar_sesion(client, email=email)
    for url in rutas_permitidas:
        respuesta = client.get(url)
        assert respuesta.status_code == 200, f"{rol} debería poder ver {url}, respondió {respuesta.status_code}"
    for url in rutas_prohibidas:
        respuesta = client.get(url)
        assert respuesta.status_code == 403, f"{rol} NO debería poder ver {url}, respondió {respuesta.status_code}"
