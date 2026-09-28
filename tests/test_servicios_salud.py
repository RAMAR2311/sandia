"""Pruebas del Catálogo de Servicios Médicos y facturación conjunta en POS."""

from decimal import Decimal
from models import Cita, CitaSpa, Producto, ServicioSalud, ServicioSpa, Tutor, Mascota, TurnoCaja, Usuario, Venta, DetalleVenta, db
from tests.conftest import iniciar_sesion, token_csrf
from utils import hoy_bogota, obtener_hora_bogota


def test_catalogo_servicios_salud_crud(client, admin):
    """Verifica que se pueden listar, crear y editar servicios médicos independientes."""
    iniciar_sesion(client)

    # 1. Listar catálogo
    res = client.get("/agenda/servicios")
    assert res.status_code == 200
    assert "Catálogo de Servicios Médicos" in res.text

    token = token_csrf(client, "/agenda/servicios/nuevo")

    # 2. Crear nuevo servicio médico
    res_crear = client.post(
        "/agenda/servicios/nuevo",
        data={
            "csrf_token": token,
            "nombre": "Profilaxis Dental Felina",
            "categoria": "procedimiento",
            "descripcion": "Limpieza profunda con ultrasonido",
            "duracion_minutos": 45,
            "precio_sugerido": "120000.00",
            "especie": "felino",
            "activo": "y",
        },
        follow_redirects=True,
    )
    assert res_crear.status_code == 200
    assert "Profilaxis Dental Felina" in res_crear.text

    # 3. Verificar en base de datos
    with client.application.app_context():
        srv = db.session.execute(
            db.select(ServicioSalud).filter_by(nombre="Profilaxis Dental Felina")
        ).scalar_one_or_none()
        assert srv is not None
        assert srv.precio_sugerido == Decimal("120000.00")
        assert srv.duracion_minutos == 45
        assert srv.categoria == "procedimiento"
        srv_id = srv.id

    # 4. Editar servicio
    token_edit = token_csrf(client, f"/agenda/servicios/{srv_id}/editar")
    res_edit = client.post(
        f"/agenda/servicios/{srv_id}/editar",
        data={
            "csrf_token": token_edit,
            "nombre": "Profilaxis Dental Felina Avanzada",
            "categoria": "procedimiento",
            "descripcion": "Incluye pulido",
            "duracion_minutos": 50,
            "precio_sugerido": "135000.00",
            "especie": "felino",
            "activo": "y",
        },
        follow_redirects=True,
    )
    assert res_edit.status_code == 200

    with client.application.app_context():
        srv_actualizado = db.session.get(ServicioSalud, srv_id)
        assert srv_actualizado.nombre == "Profilaxis Dental Felina Avanzada"
        assert srv_actualizado.precio_sugerido == Decimal("135000.00")


def test_pos_buscar_items_incluye_servicios_salud(client, admin):
    """Verifica que el endpoint del POS devuelva los servicios médicos en el filtro clinica y todos."""
    iniciar_sesion(client)

    with client.application.app_context():
        srv = ServicioSalud(
            nombre="Ecografía Renal de Urgencia",
            categoria="imagenologia",
            duracion_minutos=30,
            precio_sugerido=Decimal("80000.00"),
            activo=True,
        )
        db.session.add(srv)
        db.session.commit()

    # Buscar bajo filtro de clínica por texto
    res = client.get("/api/pos/buscar-items?categoria=clinica&q=Renal")
    assert res.status_code == 200
    datos = res.get_json()
    assert any(item["nombre"] == "Ecografía Renal de Urgencia" for item in datos)
    item_eco = next(item for item in datos if item["nombre"] == "Ecografía Renal de Urgencia")
    assert item_eco["precio_sugerido"] == 80000.0
    assert item_eco["categoria"] == "clinica"
    assert item_eco["tipo"] == "servicio"


def test_pos_facturar_spa_y_servicio_medico_conjunto(client, admin):
    """Verifica que se pueden cobrar un servicio de spa y un servicio médico en la misma factura única."""
    iniciar_sesion(client)

    with client.application.app_context():
        # Crear turno de caja
        turno = TurnoCaja(
            usuario_id=admin,
            monto_apertura=Decimal("100000.00"),
            estado="abierta",
        )
        db.session.add(turno)

        # Crear tutor y mascota
        tutor = Tutor(nombre_completo="Carlos Méndez", telefono="3101234567")
        db.session.add(tutor)
        db.session.flush()

        mascota = Mascota(nombre="Max", especie="canino", tutor_id=tutor.id)
        db.session.add(mascota)
        db.session.flush()

        # Crear servicio de spa y servicio de salud
        s_spa = ServicioSpa(nombre="Baño Antipulgas", precio_sugerido=Decimal("45000.00"), duracion_minutos=60)
        s_med = ServicioSalud(nombre="Consulta Médica General", categoria="consulta", precio_sugerido=Decimal("50000.00"), duracion_minutos=30)
        db.session.add_all([s_spa, s_med])
        db.session.commit()

        tutor_id = tutor.id
        mascota_id = mascota.id
        spa_id = s_spa.id
        med_id = s_med.id

    token = token_csrf(client, "/pos/terminal")

    # Procesar venta conjunta de Spa ($45.000) + Consulta ($50.000) = $95.000
    res_venta = client.post(
        "/pos/venta/procesar",
        json={
            "tutor_id": tutor_id,
            "mascota_id": mascota_id,
            "descuento_monto": "0.00",
            "items": [
                {
                    "producto_id": f"spa_{spa_id}",
                    "nombre": "Baño Antipulgas",
                    "tipo": "servicio",
                    "categoria": "spa",
                    "precio_unitario": "45000.00",
                    "cantidad": 1,
                    "descuento": "0.00",
                },
                {
                    "producto_id": f"salud_{med_id}",
                    "nombre": "Consulta Médica General",
                    "tipo": "servicio",
                    "categoria": "clinica",
                    "precio_unitario": "50000.00",
                    "cantidad": 1,
                    "descuento": "0.00",
                },
            ],
            "pagos": [
                {
                    "metodo_pago": "efectivo",
                    "monto": "95000.00",
                }
            ],
        },
        headers={"X-CSRFToken": token},
    )

    assert res_venta.status_code == 200
    datos = res_venta.get_json()
    assert datos.get("ok") is True
    assert datos.get("total") == 95000.0

    # Verificar que en la base de datos se generó una sola venta con dos detalles
    with client.application.app_context():
        venta = db.session.get(Venta, datos["venta_id"])
        assert venta is not None
        assert venta.total == Decimal("95000.00")
        assert len(venta.detalles) == 2
        nombres_items = [d.descripcion for d in venta.detalles]
        assert "Baño Antipulgas" in nombres_items
        assert "Consulta Médica General" in nombres_items
