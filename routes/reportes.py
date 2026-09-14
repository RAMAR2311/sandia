"""Controladores y vistas para la Fase 7: Reportes, Métricas y Tableros."""

from datetime import datetime, time, timedelta
from decimal import Decimal
from flask import Blueprint, render_template, request
from decorators import admin_required
from flask_login import login_required
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from models import (
    CitaSpa,
    ConsultaMedica,
    DetalleVenta,
    Lote,
    PagoVenta,
    Producto,
    ServicioSpa,
    Tutor,
    Venta,
    db,
)
from utils import ZONA_BOGOTA, hoy_bogota, obtener_hora_bogota

bp = Blueprint("reportes", __name__, url_prefix="/reportes")


def _obtener_rango_fechas(periodo: str, fecha_inicio_str: str = None, fecha_fin_str: str = None):
    hoy = hoy_bogota()
    if periodo == "hoy":
        inicio_date = hoy
        fin_date = hoy
    elif periodo == "semana":
        inicio_date = hoy - timedelta(days=hoy.weekday())
        fin_date = hoy
    elif periodo == "mes":
        inicio_date = hoy.replace(day=1)
        fin_date = hoy
    elif periodo == "personalizado" and fecha_inicio_str and fecha_fin_str:
        try:
            inicio_date = datetime.strptime(fecha_inicio_str, "%Y-%m-%d").date()
            fin_date = datetime.strptime(fecha_fin_str, "%Y-%m-%d").date()
        except ValueError:
            inicio_date = hoy.replace(day=1)
            fin_date = hoy
    else:
        inicio_date = hoy.replace(day=1)
        fin_date = hoy

    inicio_dt = datetime.combine(inicio_date, time.min, tzinfo=ZONA_BOGOTA)
    fin_dt = datetime.combine(fin_date, time.max, tzinfo=ZONA_BOGOTA)
    return inicio_date, fin_date, inicio_dt, fin_dt


# ---------------------------------------------------------------------------
# Tablero General de Reportes (KPIs)
# ---------------------------------------------------------------------------


@bp.route("/", methods=["GET"])
@login_required
@admin_required
def dashboard():
    periodo = request.args.get("periodo", "mes")
    fecha_inicio_str = request.args.get("fecha_inicio")
    fecha_fin_str = request.args.get("fecha_fin")

    inicio_date, fin_date, inicio_dt, fin_dt = _obtener_rango_fechas(periodo, fecha_inicio_str, fecha_fin_str)

    # 1. Total Ventas e Ingresos
    ventas_q = select(func.coalesce(func.sum(Venta.total), Decimal("0.00"))).where(
        Venta.estado == "completada", Venta.fecha_venta >= inicio_dt, Venta.fecha_venta <= fin_dt
    )
    total_ventas = db.session.execute(ventas_q).scalar_one()

    num_ventas_q = select(func.count(Venta.id)).where(
        Venta.estado == "completada", Venta.fecha_venta >= inicio_dt, Venta.fecha_venta <= fin_dt
    )
    num_ventas = db.session.execute(num_ventas_q).scalar_one()

    # 2. Desglose por Método de Pago
    pagos_q = (
        select(PagoVenta.metodo_pago, func.sum(PagoVenta.monto))
        .join(Venta)
        .where(Venta.estado == "completada", Venta.fecha_venta >= inicio_dt, Venta.fecha_venta <= fin_dt)
        .group_by(PagoVenta.metodo_pago)
    )
    pagos_por_metodo = {fil[0]: fil[1] for fil in db.session.execute(pagos_q).all()}

    # 3. Servicios de Grooming / Citas de Spa
    citas_spa_q = select(func.count(CitaSpa.id)).where(
        CitaSpa.fecha_hora >= inicio_dt, CitaSpa.fecha_hora <= fin_dt, CitaSpa.estado.in_(("entregado", "listo_recogida", "en_proceso", "programada"))
    )
    citas_spa_total = db.session.execute(citas_spa_q).scalar_one()

    # 4. Consultas Médicas Atendidas
    consultas_q = select(func.count(ConsultaMedica.id)).where(
        ConsultaMedica.fecha_hora >= inicio_dt, ConsultaMedica.fecha_hora <= fin_dt
    )
    consultas_total = db.session.execute(consultas_q).scalar_one()

    # 5. Valoración de Stock en Inventario
    productos = db.session.execute(select(Producto).filter_by(activo=True)).scalars().all()
    valoracion_inventario = sum((p.cantidad_stock * p.precio_costo for p in productos if p.tipo == "producto"), Decimal("0.00"))
    productos_stock_bajo = len([p for p in productos if p.stock_bajo])

    return render_template(
        "reportes/dashboard.html",
        periodo=periodo,
        fecha_inicio=inicio_date,
        fecha_fin=fin_date,
        total_ventas=total_ventas,
        num_ventas=num_ventas,
        pagos_por_metodo=pagos_por_metodo,
        citas_spa_total=citas_spa_total,
        consultas_total=consultas_total,
        valoracion_inventario=valoracion_inventario,
        productos_stock_bajo=productos_stock_bajo,
    )


# ---------------------------------------------------------------------------
# Reporte Detallado de Ventas
# ---------------------------------------------------------------------------


@bp.route("/ventas", methods=["GET"])
@login_required
@admin_required
def ventas():
    periodo = request.args.get("periodo", "mes")
    fecha_inicio_str = request.args.get("fecha_inicio")
    fecha_fin_str = request.args.get("fecha_fin")

    inicio_date, fin_date, inicio_dt, fin_dt = _obtener_rango_fechas(periodo, fecha_inicio_str, fecha_fin_str)

    consulta = (
        select(Venta)
        .where(Venta.fecha_venta >= inicio_dt, Venta.fecha_venta <= fin_dt)
        .options(
            selectinload(Venta.usuario),
            selectinload(Venta.tutor),
            selectinload(Venta.mascota),
            selectinload(Venta.pagos),
            selectinload(Venta.detalles),
        )
        .order_by(Venta.fecha_venta.desc())
    )
    ventas_lista = db.session.execute(consulta).scalars().all()

    total_completadas = sum((v.total for v in ventas_lista if v.estado == "completada"), Decimal("0.00"))
    total_anuladas = sum((v.total for v in ventas_lista if v.estado == "anulada"), Decimal("0.00"))

    return render_template(
        "reportes/ventas.html",
        ventas=ventas_lista,
        periodo=periodo,
        fecha_inicio=inicio_date,
        fecha_fin=fin_date,
        total_completadas=total_completadas,
        total_anuladas=total_anuladas,
    )


# ---------------------------------------------------------------------------
# Reporte de Inventario y Stock
# ---------------------------------------------------------------------------


@bp.route("/inventario", methods=["GET"])
@login_required
@admin_required
def inventario():
    productos = db.session.execute(
        select(Producto).filter_by(activo=True).order_by(Producto.nombre.asc())
    ).scalars().all()

    hoy = hoy_bogota()
    lotes_proximos = db.session.execute(
        select(Lote)
        .filter(Lote.cantidad_disponible > 0, Lote.fecha_vencimiento <= hoy + timedelta(days=30))
        .order_by(Lote.fecha_vencimiento.asc())
    ).scalars().all()

    valoracion_total = sum((p.cantidad_stock * p.precio_costo for p in productos if p.tipo == "producto"), Decimal("0.00"))

    return render_template(
        "reportes/inventario.html",
        productos=productos,
        lotes_proximos=lotes_proximos,
        valoracion_total=valoracion_total,
    )
