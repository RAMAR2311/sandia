import calendar
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from decorators import admin_required
from forms import GastoForm
from models import CATEGORIAS_GASTO, Gasto, TIPOS_GASTO, db
from utils import ZONA_BOGOTA, eliminar_documento, guardar_documento, hoy_bogota

bp = Blueprint("gastos", __name__, url_prefix="/gastos")


def _obtener_rango_gastos(periodo: str, desde_str: str = None, hasta_str: str = None):
    hoy = hoy_bogota()
    ultimo_dia_mes = calendar.monthrange(hoy.year, hoy.month)[1]

    if periodo == "hoy":
        inicio_date = hoy
        fin_date = hoy
    elif periodo == "ayer":
        inicio_date = hoy - timedelta(days=1)
        fin_date = hoy - timedelta(days=1)
    elif periodo == "semana":
        inicio_date = hoy - timedelta(days=hoy.weekday())
        fin_date = hoy
    elif periodo == "quincena":
        if hoy.day <= 15:
            inicio_date = hoy.replace(day=1)
            fin_date = hoy.replace(day=15)
        else:
            inicio_date = hoy.replace(day=16)
            fin_date = hoy.replace(day=ultimo_dia_mes)
    elif periodo == "primera_quincena":
        inicio_date = hoy.replace(day=1)
        fin_date = hoy.replace(day=15)
    elif periodo == "segunda_quincena":
        inicio_date = hoy.replace(day=16)
        fin_date = hoy.replace(day=ultimo_dia_mes)
    elif periodo == "mes":
        inicio_date = hoy.replace(day=1)
        fin_date = hoy.replace(day=ultimo_dia_mes)
    elif periodo == "mes_anterior":
        primer_dia_mes_actual = hoy.replace(day=1)
        ultimo_dia_mes_anterior = primer_dia_mes_actual - timedelta(days=1)
        inicio_date = ultimo_dia_mes_anterior.replace(day=1)
        fin_date = ultimo_dia_mes_anterior
    elif periodo == "personalizado" and desde_str and hasta_str:
        try:
            inicio_date = datetime.strptime(desde_str, "%Y-%m-%d").date()
            fin_date = datetime.strptime(hasta_str, "%Y-%m-%d").date()
        except ValueError:
            inicio_date = hoy.replace(day=1)
            fin_date = hoy
    else:
        # Si vienen parametros 'desde' y 'hasta' explicitos sin 'periodo'
        if desde_str and hasta_str:
            try:
                inicio_date = datetime.strptime(desde_str, "%Y-%m-%d").date()
                fin_date = datetime.strptime(hasta_str, "%Y-%m-%d").date()
                return "personalizado", inicio_date, fin_date
            except ValueError:
                pass
        inicio_date = hoy
        fin_date = hoy

    return periodo or "hoy", inicio_date, fin_date


@bp.route("/", methods=["GET"])
@login_required
@admin_required
def lista():
    periodo_req = request.args.get("periodo")
    desde_str = request.args.get("desde")
    hasta_str = request.args.get("hasta")

    if not periodo_req and (desde_str or hasta_str):
        periodo = "personalizado"
    else:
        periodo = periodo_req or "hoy"

    periodo, desde, hasta = _obtener_rango_gastos(periodo, desde_str, hasta_str)

    consulta = (
        select(Gasto)
        .where(Gasto.fecha_gasto >= desde, Gasto.fecha_gasto <= hasta)
        .options(selectinload(Gasto.usuario))
        .order_by(Gasto.fecha_gasto.desc(), Gasto.id.desc())
    )
    gastos = db.session.execute(consulta).scalars().all()

    total = sum((g.monto for g in gastos), Decimal("0.00"))
    total_diarios = sum((g.monto for g in gastos if g.tipo_gasto == "diario"), Decimal("0.00"))
    total_indirectos = sum((g.monto for g in gastos if g.tipo_gasto == "indirecto"), Decimal("0.00"))

    return render_template(
        "gastos/lista.html",
        gastos=gastos,
        total=total,
        total_diarios=total_diarios,
        total_indirectos=total_indirectos,
        desde=desde,
        hasta=hasta,
        periodo=periodo,
        categorias=CATEGORIAS_GASTO,
        tipos=TIPOS_GASTO,
    )


@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@admin_required
def nuevo():
    form = GastoForm(fecha_gasto=hoy_bogota())
    if form.validate_on_submit():
        nombre_archivo = None
        if form.comprobante.data and getattr(form.comprobante.data, "filename", ""):
            try:
                nombre_archivo = guardar_documento(form.comprobante.data, "gastos")
            except ValueError as exc:
                form.comprobante.errors.append(str(exc))

        if not form.comprobante.errors:
            gasto = Gasto(
                usuario_id=current_user.id,
                tipo_gasto=form.tipo_gasto.data,
                categoria=form.categoria.data,
                descripcion=form.descripcion.data,
                monto=form.monto.data,
                fecha_gasto=form.fecha_gasto.data,
                comprobante=nombre_archivo,
            )
            try:
                db.session.add(gasto)
                db.session.commit()
            except Exception:
                db.session.rollback()
                if nombre_archivo:
                    eliminar_documento("gastos", nombre_archivo)
                current_app.logger.exception("Error al registrar gasto")
                flash("No se pudo registrar el gasto.", "danger")
            else:
                flash(f"Gasto de {gasto.monto:,.0f} registrado.", "success")
                return redirect(url_for("gastos.lista"))
    return render_template("gastos/form.html", form=form)
