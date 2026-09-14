"""Registro de gastos diarios y costos indirectos."""

from datetime import date

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select

from decorators import admin_required
from forms import GastoForm
from models import CATEGORIAS_GASTO, Gasto, TIPOS_GASTO, db
from utils import eliminar_documento, guardar_documento, hoy_bogota

bp = Blueprint("gastos", __name__, url_prefix="/gastos")


@bp.route("/", methods=["GET"])
@login_required
@admin_required
def lista():
    desde_str = request.args.get("desde") or hoy_bogota().replace(day=1).isoformat()
    hasta_str = request.args.get("hasta") or hoy_bogota().isoformat()
    try:
        desde = date.fromisoformat(desde_str)
        hasta = date.fromisoformat(hasta_str)
    except ValueError:
        desde, hasta = hoy_bogota().replace(day=1), hoy_bogota()
        desde_str, hasta_str = desde.isoformat(), hasta.isoformat()

    consulta = select(Gasto).where(Gasto.fecha_gasto >= desde, Gasto.fecha_gasto <= hasta).order_by(Gasto.fecha_gasto.desc())
    gastos = db.session.execute(consulta).scalars().all()
    total = db.session.execute(
        select(func.coalesce(func.sum(Gasto.monto), 0)).where(Gasto.fecha_gasto >= desde, Gasto.fecha_gasto <= hasta)
    ).scalar_one()

    return render_template("gastos/lista.html", gastos=gastos, total=total, desde=desde_str, hasta=hasta_str)


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
