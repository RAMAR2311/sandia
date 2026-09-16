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
from models import ESTADOS_CITA, TIPOS_CITA, Cita, CitaSpa, Mascota, ServicioSpa, Tutor, Usuario, db
from utils import ZONA_BOGOTA, enlace_whatsapp, hoy_bogota


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

    # 1. Consultas y Citas Médicas
    citas_medicas = db.session.execute(
        select(Cita)
        .where(Cita.fecha_hora >= inicio, Cita.fecha_hora <= fin)
        .options(selectinload(Cita.mascota), selectinload(Cita.tutor), selectinload(Cita.profesional))
        .order_by(Cita.fecha_hora)
    ).scalars().all()

    # 2. Citas de Spa & Grooming
    citas_spa = db.session.execute(
        select(CitaSpa)
        .where(CitaSpa.fecha_hora >= inicio, CitaSpa.fecha_hora <= fin)
        .options(
            selectinload(CitaSpa.mascota),
            selectinload(CitaSpa.tutor),
            selectinload(CitaSpa.groomer),
            selectinload(CitaSpa.servicio_spa),
        )
        .order_by(CitaSpa.fecha_hora)
    ).scalars().all()

    # 3. Consolidar Citas Unificadas con Identificación Clara
    citas_unificadas = []

    for cm in citas_medicas:
        msg_wa = (
            f"Hola {cm.tutor.nombre_completo if cm.tutor else ''}, te recordamos la cita médica de {cm.mascota.nombre if cm.mascota else ''} "
            f"para hoy a las {cm.fecha_hora.strftime('%I:%M %p')} en Sandía Medicina & Spa Veterinario 🐾."
        ) if cm.tutor else ""
        tel_tutor = (cm.tutor.whatsapp or cm.tutor.telefono) if cm.tutor else ""
        wa_url = enlace_whatsapp(tel_tutor, msg_wa) if tel_tutor else ""

        citas_unificadas.append({
            "id": cm.id,
            "origen": "medica",
            "categoria_nombre": "Médica & Consulta",
            "categoria_icono": "bi-heart-pulse-fill",
            "categoria_badge_color": "danger",
            "tipo_codigo": cm.tipo,
            "tipo_nombre": TIPOS_CITA.get(cm.tipo, cm.tipo.capitalize()),
            "fecha_hora": cm.fecha_hora,
            "duracion_minutos": cm.duracion_minutos or 30,
            "mascota": cm.mascota,
            "tutor": cm.tutor,
            "profesional_nombre": cm.profesional.nombre if cm.profesional else "Sin médico asignado",
            "profesional_cargo": "Médico/a Veterinario",
            "motivo_o_servicio": cm.motivo or "Consulta médica general",
            "estado": cm.estado,
            "estado_etiqueta": ESTADOS_CITA.get(cm.estado, cm.estado.capitalize()),
            "enlace_detalle": url_for("agenda.detalle", id=cm.id),
            "enlace_accion": url_for("historias.consulta_nueva", mascota_id=cm.mascota_id) if cm.mascota_id else None,
            "texto_accion": "Consulta SOAP",
            "icono_accion": "bi-journal-medical",
            "clase_accion": "btn-primary",
            "wa_url": wa_url,
            "objeto": cm,
        })

    estado_spa_map = {
        "programada": ("Programada", "bg-primary-subtle text-primary border-primary-subtle", "bi-clock"),
        "en_proceso": ("En Proceso / Baño", "bg-danger text-white", "bi-droplet-fill"),
        "listo_recogida": ("Listo para Recogida", "bg-warning text-dark border-warning", "bi-bell-fill"),
        "entregado": ("Entregado", "bg-success-subtle text-success border-success-subtle", "bi-check-all"),
        "cancelada": ("Cancelada", "bg-secondary-subtle text-secondary border", "bi-x-circle"),
    }

    for cs in citas_spa:
        serv_nombre = cs.servicio_spa.nombre if cs.servicio_spa else "Servicio de Peluquería"
        msg_wa = (
            f"Hola {cs.tutor.nombre_completo if cs.tutor else ''}, te recordamos la cita de Spa & Grooming ({serv_nombre}) de "
            f"{cs.mascota.nombre if cs.mascota else ''} para hoy a las {cs.fecha_hora.strftime('%I:%M %p')} en Sandía 🐾✂️."
        ) if cs.tutor else ""
        tel_tutor = (cs.tutor.whatsapp or cs.tutor.telefono) if cs.tutor else ""
        wa_url = enlace_whatsapp(tel_tutor, msg_wa) if tel_tutor else ""

        info_est = estado_spa_map.get(cs.estado, (cs.estado.capitalize(), "bg-secondary", "bi-clock"))

        citas_unificadas.append({
            "id": cs.id,
            "origen": "spa",
            "categoria_nombre": "Spa & Grooming",
            "categoria_icono": "bi-scissors",
            "categoria_badge_color": "teal",
            "tipo_codigo": "spa",
            "tipo_nombre": serv_nombre,
            "fecha_hora": cs.fecha_hora,
            "duracion_minutos": cs.duracion_minutos or (cs.servicio_spa.duracion_minutos if cs.servicio_spa else 60),
            "mascota": cs.mascota,
            "tutor": cs.tutor,
            "profesional_nombre": cs.groomer.nombre if cs.groomer else "Estilista general",
            "profesional_cargo": "Estilista / Groomer",
            "motivo_o_servicio": serv_nombre + (f" - {cs.notas_ingreso}" if cs.notas_ingreso else ""),
            "estado": cs.estado,
            "estado_etiqueta": info_est[0],
            "enlace_detalle": url_for("spa.cita_detalle", id=cs.id),
            "enlace_accion": url_for("spa.cita_detalle", id=cs.id),
            "texto_accion": "Ver Turno Spa",
            "icono_accion": "bi-scissors",
            "clase_accion": "btn-dark",
            "wa_url": wa_url,
            "objeto": cs,
        })

    # Orden cronológico por hora
    citas_unificadas.sort(key=lambda x: x["fecha_hora"])

    # Conteo de métricas consolidadas
    count_medicas = len(citas_medicas)
    count_spa = len(citas_spa)
    count_programadas = sum(1 for c in citas_unificadas if c["estado"] in ("programada", "confirmada"))
    count_en_atencion = sum(1 for c in citas_unificadas if c["estado"] in ("en_atencion", "en_proceso"))
    count_cumplidas = sum(1 for c in citas_unificadas if c["estado"] in ("cumplida", "listo_recogida", "entregado"))
    count_canceladas = sum(1 for c in citas_unificadas if c["estado"] in ("cancelada", "no_asistio"))

    fecha_anterior = fecha - timedelta(days=1)
    fecha_siguiente = fecha + timedelta(days=1)

    return render_template(
        "agenda/lista.html",
        citas=citas_unificadas,
        citas_medicas_count=count_medicas,
        citas_spa_count=count_spa,
        count_programadas=count_programadas,
        count_en_atencion=count_en_atencion,
        count_cumplidas=count_cumplidas,
        count_canceladas=count_canceladas,
        fecha=fecha,
        fecha_anterior=fecha_anterior,
        fecha_siguiente=fecha_siguiente,
        ESTADOS_CITA=ESTADOS_CITA,
        TIPOS_CITA=TIPOS_CITA,
    )


@bp.route("/nueva", methods=["GET", "POST"])
@login_required
@recepcion_required
def nueva():
    form = CitaForm()
    form.profesional_id.choices = _opciones_profesionales()
    if request.method == "GET":
        form.fecha.data = hoy_bogota()

    if form.validate_on_submit():
        mascota = db.session.get(Mascota, int(form.mascota_id.data)) if form.mascota_id.data else None
        tutor = db.session.get(Tutor, int(form.tutor_id.data)) if form.tutor_id.data else (mascota.tutor if mascota else None)
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
    return render_template("agenda/form.html", form=form, hoy=hoy_bogota())


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
