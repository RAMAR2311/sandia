"""Agenda médica general: consultas, vacunación, cirugía y controles.

Independiente de la agenda de spa (``routes/spa.py``).
"""

from datetime import datetime, time, timedelta

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from decorators import recepcion_required
from forms import CambiarEstadoCitaForm, CitaForm, SoloCsrfForm
from models import ESTADOS_CITA, Cita, Mascota, Tutor, Usuario, db
from utils import ZONA_BOGOTA, hoy_bogota

bp = Blueprint("agenda", __name__, url_prefix="/agenda")


def _opciones_profesionales():
    usuarios = db.session.execute(
        select(Usuario).where(Usuario.activo.is_(True), Usuario.rol.in_(("admin", "veterinario", "auxiliar"))).order_by(Usuario.nombre)
    ).scalars()
    return [(0, "Sin asignar")] + [(u.id, u.nombre) for u in usuarios]


@bp.route("/", methods=["GET"])
@login_required
@recepcion_required
def lista():
    fecha_str = request.args.get("fecha")
    try:
        fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date() if fecha_str else hoy_bogota()
    except ValueError:
        fecha = hoy_bogota()

    inicio = datetime.combine(fecha, time.min, tzinfo=ZONA_BOGOTA)
    fin = datetime.combine(fecha, time.max, tzinfo=ZONA_BOGOTA)
    citas = db.session.execute(
        select(Cita)
        .where(Cita.fecha_hora >= inicio, Cita.fecha_hora <= fin)
        .options(selectinload(Cita.mascota), selectinload(Cita.tutor), selectinload(Cita.profesional))
        .order_by(Cita.fecha_hora)
    ).scalars().all()
    return render_template("agenda/lista.html", citas=citas, fecha=fecha, ESTADOS_CITA=ESTADOS_CITA)


@bp.route("/nueva", methods=["GET", "POST"])
@login_required
@recepcion_required
def nueva():
    form = CitaForm()
    form.profesional_id.choices = _opciones_profesionales()
    if request.method == "GET":
        form.fecha.data = hoy_bogota()

    if form.validate_on_submit():
        tutor = db.session.get(Tutor, int(form.tutor_id.data)) if form.tutor_id.data else None
        mascota = db.session.get(Mascota, int(form.mascota_id.data)) if form.mascota_id.data else None
        if not tutor or not mascota:
            flash("Selecciona la mascota (y su tutor) de la cita.", "danger")
        else:
            fecha_hora = datetime.combine(form.fecha.data, form.hora.data, tzinfo=ZONA_BOGOTA)
            cita = Cita(
                mascota_id=mascota.id,
                tutor_id=tutor.id,
                profesional_id=form.profesional_id.data or None,
                tipo=form.tipo.data,
                fecha_hora=fecha_hora,
                duracion_minutos=form.duracion_minutos.data,
                motivo=form.motivo.data,
                notas=form.notas.data,
                creado_por_id=current_user.id,
            )
            try:
                db.session.add(cita)
                db.session.commit()
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Error al crear cita")
                flash("No se pudo agendar la cita. Inténtalo de nuevo.", "danger")
            else:
                flash(f"Cita de {mascota.nombre} agendada.", "success")
                return redirect(url_for("agenda.lista", fecha=form.fecha.data.isoformat()))
    return render_template("agenda/form.html", form=form)


@bp.route("/<int:id>", methods=["GET"])
@login_required
@recepcion_required
def detalle(id: int):
    cita = db.session.get(Cita, id)
    if not cita:
        abort(404)
    return render_template(
        "agenda/detalle.html", cita=cita, form_estado=CambiarEstadoCitaForm(estado=cita.estado), form_csrf=SoloCsrfForm()
    )


@bp.route("/<int:id>/estado", methods=["POST"])
@login_required
@recepcion_required
def cambiar_estado(id: int):
    cita = db.session.get(Cita, id)
    if not cita:
        abort(404)
    form = CambiarEstadoCitaForm()
    if form.validate_on_submit():
        try:
            cita.estado = form.estado.data
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al cambiar estado de la cita %d", id)
            flash("No se pudo actualizar el estado.", "danger")
        else:
            flash("Estado actualizado.", "success")
    return redirect(url_for("agenda.detalle", id=id))


@bp.route("/<int:id>/recordatorio-enviado", methods=["POST"])
@login_required
@recepcion_required
def marcar_recordatorio(id: int):
    cita = db.session.get(Cita, id)
    if not cita:
        abort(404)
    form = SoloCsrfForm()
    if not form.validate_on_submit():
        abort(400)
    try:
        cita.recordatorio_enviado = True
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error al marcar recordatorio de la cita %d", id)
        return {"error": "No se pudo registrar el recordatorio."}, 500
    return {"ok": True}
