"""Endpoints JSON para búsquedas rápidas (formularios, POS y agenda).

Todas las respuestas son listas de diccionarios. Las peticiones que modifican
datos (fases posteriores) exigen el token CSRF en el header ``X-CSRFToken``.
"""

from flask import Blueprint, jsonify, request, url_for
from flask_login import login_required
from sqlalchemy import case, or_, select

from models import ESPECIES, Mascota, Producto, Raza, ServicioSpa, Tutor, db
from utils import PREFIJO_MINIATURA, normalizar_texto, solo_digitos

bp = Blueprint("api", __name__, url_prefix="/api")

LIMITE_MAXIMO = 50


def _limite() -> int:
    limite = request.args.get("limite", 15, type=int)
    return max(1, min(limite, LIMITE_MAXIMO))


def _foto_mini(mascota):
    if not mascota.foto:
        return None
    return url_for("static", filename=f"uploads/mascotas/{PREFIJO_MINIATURA}{mascota.foto}")


def tutor_a_dict(tutor: Tutor) -> dict:
    return {
        "id": tutor.id,
        "nombre": tutor.nombre_completo,
        "documento": tutor.documento_texto,
        "telefono": tutor.telefono or "",
        "whatsapp": tutor.whatsapp_efectivo,
        "activo": tutor.activo,
        "mascotas": [
            {"id": m.id, "nombre": m.nombre, "especie": m.especie, "emoji": m.especie_emoji}
            for m in tutor.mascotas_activas
        ],
        "url": url_for("tutores.detalle", tutor_id=tutor.id),
    }


def mascota_a_dict(mascota: Mascota) -> dict:
    return {
        "id": mascota.id,
        "nombre": mascota.nombre,
        "especie": mascota.especie,
        "especie_etiqueta": mascota.especie_etiqueta,
        "emoji": mascota.especie_emoji,
        "raza": mascota.raza.nombre if mascota.raza else "Mestizo",
        "sexo": mascota.sexo,
        "edad": mascota.edad,
        "tamano": mascota.tamano or "",
        "activo": mascota.activo and not mascota.fallecido,
        "microchip": mascota.microchip or "",
        "foto_mini": _foto_mini(mascota),
        "tutor": {
            "id": mascota.tutor.id if mascota.tutor else None,
            "nombre": mascota.tutor.nombre_completo if mascota.tutor else "Sin tutor",
            "telefono": mascota.tutor.telefono or "",
            "whatsapp": mascota.tutor.whatsapp_efectivo if mascota.tutor else None,
            "documento": mascota.tutor.documento_texto if mascota.tutor else "",
        },
        "url": url_for("mascotas.detalle", mascota_id=mascota.id),
        "url_detalle": url_for("mascotas.detalle", mascota_id=mascota.id),
        "url_ficha": url_for("historias.ficha_medica", mascota_id=mascota.id),
        "url_consulta_nueva": url_for("historias.consulta_nueva", mascota_id=mascota.id),
        "url_cita_spa": url_for("spa.cita_nueva", mascota_id=mascota.id),
    }


@bp.route("/tutores/buscar")
@login_required
def buscar_tutores():
    texto = request.args.get("q", "").strip()
    if not texto:
        return jsonify([])
    condiciones = []
    normalizado = normalizar_texto(texto)
    if normalizado:
        condiciones.append(Tutor.nombre_busqueda.ilike(f"%{normalizado}%"))
    digitos = solo_digitos(texto)
    if digitos:
        patron = f"%{digitos}%"
        condiciones += [Tutor.telefono.ilike(patron), Tutor.whatsapp.ilike(patron), Tutor.numero_documento.ilike(patron)]
    condiciones.append(Tutor.numero_documento.ilike(f"%{texto}%"))
    condiciones.append(Tutor.telefono.ilike(f"%{texto}%"))
    consulta = (
        select(Tutor)
        .where(Tutor.activo.is_(True), or_(*condiciones))
        .order_by(Tutor.nombre_busqueda)
        .limit(_limite())
    )
    return jsonify([tutor_a_dict(t) for t in db.session.execute(consulta).scalars()])


@bp.route("/mascotas/buscar")
@login_required
def buscar_mascotas():
    texto = request.args.get("q", "").strip()
    if not texto:
        return jsonify([])
    normalizado = normalizar_texto(texto)
    condiciones = [
        Mascota.nombre_busqueda.ilike(f"%{normalizado}%"),
        Tutor.nombre_busqueda.ilike(f"%{normalizado}%"),
    ]
    if texto:
        condiciones.append(Mascota.microchip.ilike(f"%{texto}%"))
        condiciones.append(Tutor.numero_documento.ilike(f"%{texto}%"))
        condiciones.append(Tutor.telefono.ilike(f"%{texto}%"))
    
    orden_relevancia = case(
        (Mascota.nombre_busqueda.ilike(f"{normalizado}%"), 1),
        (Mascota.nombre_busqueda.ilike(f"%{normalizado}%"), 2),
        (Tutor.nombre_busqueda.ilike(f"{normalizado}%"), 3),
        else_=4,
    )
    
    consulta = (
        select(Mascota)
        .join(Mascota.tutor)
        .where(
            or_(*condiciones),
        )
        .order_by(orden_relevancia, Mascota.nombre_busqueda.asc())
        .limit(_limite())
    )
    return jsonify([mascota_a_dict(m) for m in db.session.execute(consulta).scalars()])


@bp.route("/razas")
@login_required
def razas():
    especie = request.args.get("especie", "").strip()
    if especie not in ESPECIES:
        return jsonify(error="Especie no válida."), 400
    consulta = select(Raza).where(Raza.especie == especie, Raza.activo.is_(True)).order_by(Raza.nombre)
    return jsonify([{"id": r.id, "nombre": r.nombre} for r in db.session.execute(consulta).scalars()])


def producto_a_dict(producto: Producto, es_admin: bool = False) -> dict:
    datos = {
        "id": producto.id,
        "sku": producto.sku,
        "codigo_barras": producto.codigo_barras or "",
        "nombre": producto.nombre,
        "categoria": producto.categoria,
        "categoria_etiqueta": producto.categoria_etiqueta,
        "tipo": producto.tipo,
        "unidad_medida": producto.unidad_medida,
        "precio_minimo": float(producto.precio_minimo),
        "precio_sugerido": float(producto.precio_sugerido),
        "stock_total": float(producto.stock_total),
        "stock_minimo": float(producto.stock_minimo),
        "stock_bajo": producto.stock_bajo,
        "controla_lote": producto.controla_lote,
        "requiere_receta": producto.requiere_receta,
        "tiene_variantes": producto.tiene_variantes,
        "variantes": [
            {
                "id": v.id,
                "nombre_variante": v.nombre_variante,
                "sku": v.sku or "",
                "codigo_barras": v.codigo_barras or "",
                "precio_minimo": float(v.precio_minimo),
                "precio_sugerido": float(v.precio_sugerido),
                "cantidad_stock": float(v.cantidad_stock),
                "stock_bajo": v.stock_bajo,
                "precio_costo": float(v.precio_costo) if es_admin else None,
            }
            for v in producto.variantes
            if v.activo
        ],
        "lotes": [
            {
                "id": l.id,
                "numero_lote": l.numero_lote,
                "fecha_vencimiento": l.fecha_vencimiento.strftime("%Y-%m-%d"),
                "cantidad_disponible": float(l.cantidad_disponible),
                "variante_id": l.variante_id,
            }
            for l in producto.lotes_disponibles
        ],
        "url": url_for("inventario.detalle", producto_id=producto.id),
    }
    # Regla de oro: precio_costo SOLO se devuelve al admin
    if es_admin:
        datos["precio_costo"] = float(producto.precio_costo)
    else:
        datos["precio_costo"] = None

    return datos


@bp.route("/productos/buscar")
@login_required
def buscar_productos():
    from flask_login import current_user
    from models import Producto

    texto = request.args.get("q", "").strip()
    if len(texto) < 1:
        return jsonify([])

    normalizado = normalizar_texto(texto)
    consulta = (
        select(Producto)
        .where(
            Producto.activo.is_(True),
            or_(
                Producto.nombre_busqueda.ilike(f"%{normalizado}%"),
                Producto.sku.ilike(f"%{normalizado}%"),
                Producto.codigo_barras.ilike(f"%{normalizado}%"),
            ),
        )
        .order_by(Producto.nombre_busqueda)
        .limit(_limite())
    )
    es_admin = getattr(current_user, "es_admin", False)
    return jsonify([producto_a_dict(p, es_admin=es_admin) for p in db.session.execute(consulta).scalars()])


@bp.route("/pos/buscar-items", methods=["GET"])
@login_required
def pos_buscar_items():
    """Búsqueda rápida de productos y servicios para la terminal POS."""
    texto = request.args.get("q", "").strip()
    categoria_filtro = request.args.get("categoria", "").strip()
    limite_pos = min(request.args.get("limite", 36, type=int), 60)
    normalizado = normalizar_texto(texto)

    items = []

    # 1. Buscar en catálogo de productos y servicios clínicos
    if categoria_filtro in ("", "todos", "productos", "clinica"):
        consulta = select(Producto).where(Producto.activo.is_(True))
        if categoria_filtro == "productos":
            consulta = consulta.where(Producto.tipo == "producto")
        elif categoria_filtro == "clinica":
            consulta = consulta.where(Producto.tipo == "servicio")

        if normalizado:
            consulta = consulta.where(
                or_(
                    Producto.nombre_busqueda.ilike(f"%{normalizado}%"),
                    Producto.sku.ilike(f"%{normalizado}%"),
                    Producto.codigo_barras.ilike(f"%{normalizado}%"),
                )
            )

        consulta = consulta.order_by(Producto.tipo.desc(), Producto.nombre_busqueda).limit(limite_pos)
        productos = db.session.execute(consulta).scalars().all()

        for p in productos:
            variantes = []
            if p.tiene_variantes:
                for v in p.variantes:
                    if v.activo:
                        variantes.append({
                            "id": v.id,
                            "nombre": v.nombre_variante,
                            "sku": v.sku or p.sku,
                            "codigo_barras": v.codigo_barras or p.codigo_barras,
                            "precio_sugerido": float(v.precio_sugerido),
                            "stock_total": float(v.cantidad_stock),
                        })
            items.append({
                "id": p.id,
                "sku": p.sku,
                "codigo_barras": p.codigo_barras or "",
                "nombre": p.nombre,
                "tipo": p.tipo,
                "categoria": "clinica" if p.tipo == "servicio" else p.categoria,
                "precio_sugerido": float(p.precio_sugerido),
                "stock_total": float(p.stock_total) if p.tipo == "producto" else None,
                "controla_lote": p.controla_lote,
                "requiere_receta": p.requiere_receta,
                "variantes": variantes,
            })

    # 2. Buscar en catálogo de Spa & Peluquería
    if categoria_filtro in ("", "todos", "spa"):
        consulta_spa = select(ServicioSpa).where(ServicioSpa.activo.is_(True))
        if normalizado:
            consulta_spa = consulta_spa.where(ServicioSpa.nombre.ilike(f"%{normalizado}%"))
        consulta_spa = consulta_spa.order_by(ServicioSpa.nombre).limit(limite_pos)
        servicios_spa = db.session.execute(consulta_spa).scalars().all()

        for s in servicios_spa:
            items.append({
                "id": f"spa_{s.id}",
                "servicio_spa_id": s.id,
                "sku": f"SPA-{s.id:02d}",
                "codigo_barras": "",
                "nombre": s.nombre,
                "tipo": "servicio",
                "categoria": "spa",
                "precio_sugerido": float(s.precio_sugerido),
                "stock_total": None,
                "controla_lote": False,
                "requiere_receta": False,
                "variantes": [],
            })

    if categoria_filtro in ("", "todos"):
        items.sort(key=lambda x: x["nombre"].lower())

    return jsonify(items)


@bp.route("/pos/tutores-mascotas", methods=["GET"])
@login_required
def pos_buscar_tutores_mascotas():
    """Búsqueda de tutores y sus mascotas para asociar a una venta en POS."""
    texto = request.args.get("q", "").strip()
    if len(texto) < 1:
        return jsonify([])

    normalizado = normalizar_texto(texto)
    digitos = solo_digitos(texto)

    filtros = []
    if normalizado:
        filtros.append(Tutor.nombre_busqueda.ilike(f"%{normalizado}%"))
        filtros.append(
            Tutor.id.in_(
                select(Mascota.tutor_id).where(
                    Mascota.activo.is_(True),
                    Mascota.nombre_busqueda.ilike(f"%{normalizado}%")
                )
            )
        )
    if len(digitos) >= 2:
        filtros.append(Tutor.numero_documento.ilike(f"%{digitos}%"))
        filtros.append(Tutor.telefono.ilike(f"%{digitos}%"))
        filtros.append(Tutor.whatsapp.ilike(f"%{digitos}%"))

    if not filtros:
        return jsonify([])

    consulta = (
        select(Tutor)
        .where(Tutor.activo.is_(True), or_(*filtros))
        .order_by(Tutor.nombre_busqueda)
        .limit(15)
    )
    tutores = db.session.execute(consulta).scalars().all()

    resultado = []
    for t in tutores:
        mascotas = [
            {"id": m.id, "nombre": m.nombre, "especie": m.especie, "emoji": m.especie_emoji}
            for m in t.mascotas if m.activo and not m.fallecido
        ]
        resultado.append({
            "id": t.id,
            "nombre": t.nombre_completo,
            "documento": t.documento_texto or "Sin documento",
            "telefono": t.telefono or t.whatsapp or "",
            "mascotas": mascotas,
        })

    return jsonify(resultado)


@bp.route("/spa/citas-hoy", methods=["GET"])
@login_required
def spa_citas_hoy():
    """Consulta rápida de citas de spa del día para widgets o notificaciones."""
    from datetime import datetime, time
    from models import CitaSpa
    from utils import ZONA_BOGOTA, hoy_bogota

    inicio = datetime.combine(hoy_bogota(), time.min, tzinfo=ZONA_BOGOTA)
    fin = datetime.combine(hoy_bogota(), time.max, tzinfo=ZONA_BOGOTA)

    consulta = (
        select(CitaSpa)
        .filter(CitaSpa.fecha_hora >= inicio, CitaSpa.fecha_hora <= fin)
        .order_by(CitaSpa.fecha_hora.asc())
    )
    citas = db.session.execute(consulta).scalars().all()

    return jsonify([
        {
            "id": c.id,
            "hora": c.fecha_hora.strftime("%H:%M"),
            "mascota": c.mascota.nombre if c.mascota else "Sin mascota",
            "tutor": c.tutor.nombre_completo if c.tutor else "Sin tutor",
            "servicio": c.servicio_spa.nombre if c.servicio_spa else "Spa",
            "estado": c.estado,
            "estado_etiqueta": c.estado_etiqueta,
            "enlace_whatsapp": c.enlace_whatsapp,
        }
        for c in citas
    ])


@bp.route("/historias/vacunas-pendientes", methods=["GET"])
@login_required
def historias_vacunas_pendientes():
    """Retorna vacunas y desparasitaciones próximas a vencer o vencidas."""
    from datetime import timedelta
    from models import DesparasitacionMascota, VacunaMascota
    from utils import hoy_bogota

    hoy = hoy_bogota()
    limite = hoy + timedelta(days=15)

    vacunas = db.session.execute(
        select(VacunaMascota)
        .filter(VacunaMascota.fecha_proxima <= limite)
        .order_by(VacunaMascota.fecha_proxima.asc())
    ).scalars().all()

    desparasitaciones = db.session.execute(
        select(DesparasitacionMascota)
        .filter(DesparasitacionMascota.fecha_proxima.is_not(None), DesparasitacionMascota.fecha_proxima <= limite)
        .order_by(DesparasitacionMascota.fecha_proxima.asc())
    ).scalars().all()

    resultado = {
        "vacunas": [
            {
                "id": v.id,
                "mascota_id": v.mascota_id,
                "mascota_nombre": v.mascota.nombre if v.mascota else "",
                "tutor_nombre": v.tutor.nombre_completo if v.tutor else "",
                "tutor_whatsapp": v.tutor.whatsapp_efectivo if v.tutor else "",
                "nombre_vacuna": v.nombre_vacuna,
                "fecha_proxima": v.fecha_proxima.strftime("%Y-%m-%d"),
                "estado_vencimiento": v.estado_vencimiento,
            }
            for v in vacunas
        ],
        "desparasitaciones": [
            {
                "id": d.id,
                "mascota_id": d.mascota_id,
                "mascota_nombre": d.mascota.nombre if d.mascota else "",
                "tutor_nombre": d.tutor.nombre_completo if d.tutor else "",
                "tutor_whatsapp": d.tutor.whatsapp_efectivo if d.tutor else "",
                "producto": d.producto,
                "tipo": d.tipo,
                "fecha_proxima": d.fecha_proxima.strftime("%Y-%m-%d") if d.fecha_proxima else "",
                "estado_vencimiento": d.estado_vencimiento,
            }
            for d in desparasitaciones
        ],
    }
    return jsonify(resultado)


@bp.route("/reportes/dashboard-kpis", methods=["GET"])
@login_required
def reportes_dashboard_kpis():
    """Resumen rápido de métricas financieras y operativas del día."""
    from datetime import datetime, time
    from decimal import Decimal
    from sqlalchemy import func
    from models import CitaSpa, ConsultaMedica, Venta
    from utils import ZONA_BOGOTA, hoy_bogota

    hoy = hoy_bogota()
    inicio = datetime.combine(hoy, time.min, tzinfo=ZONA_BOGOTA)
    fin = datetime.combine(hoy, time.max, tzinfo=ZONA_BOGOTA)

    ventas_hoy = db.session.execute(
        select(func.coalesce(func.sum(Venta.total), Decimal("0.00")))
        .where(Venta.estado == "completada", Venta.fecha_venta >= inicio, Venta.fecha_venta <= fin)
    ).scalar_one()

    citas_hoy = db.session.execute(
        select(func.count(CitaSpa.id)).where(CitaSpa.fecha_hora >= inicio, CitaSpa.fecha_hora <= fin)
    ).scalar_one()

    consultas_hoy = db.session.execute(
        select(func.count(ConsultaMedica.id)).where(ConsultaMedica.fecha_hora >= inicio, ConsultaMedica.fecha_hora <= fin)
    ).scalar_one()

    return jsonify({
        "ventas_hoy": float(ventas_hoy),
        "citas_hoy": citas_hoy,
        "consultas_hoy": consultas_hoy,
    })




