"""Módulo de Spa, Peluquería y Grooming de Mascotas.

Gestión del catálogo de servicios de estética, agendamiento de citas,
control de flujo de estados (programada -> en proceso -> listo -> entregado),
generación de notificaciones de aviso por WhatsApp y cobro directo en POS.
"""

from datetime import datetime, time, timedelta
from typing import Optional

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from decorators import agenda_spa_required, admin_required, spa_required
from flask_login import current_user, login_required
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from forms import CambioEstadoSpaForm, CitaSpaForm, ServicioSpaForm, SoloCsrfForm, VincularVentaSpaForm
from models import (
    ESTADOS_SPA,
    CitaSpa,
    Mascota,
    ServicioSpa,
    Tutor,
    Usuario,
    Venta,
    db,
)
from utils import ZONA_BOGOTA, hoy_bogota, obtener_hora_bogota

bp = Blueprint("spa", __name__, url_prefix="/spa")


# ---------------------------------------------------------------------------
# Catálogo de Servicios de Spa
# ---------------------------------------------------------------------------


@bp.route("/servicios", methods=["GET"])
@login_required
@admin_required
def servicios_lista():
    servicios = db.session.execute(
        select(ServicioSpa).order_by(ServicioSpa.activo.desc(), ServicioSpa.nombre)
    ).scalars().all()
    form_csrf = SoloCsrfForm()
    return render_template("spa/servicios.html", servicios=servicios, form_csrf=form_csrf)


@bp.route("/servicio/nuevo", methods=["GET", "POST"])
@login_required
@admin_required
def servicio_nuevo():

    form = ServicioSpaForm()
    if form.validate_on_submit():
        try:
            nuevo_servicio = ServicioSpa(
                nombre=form.nombre.data.strip(),
                descripcion=form.descripcion.data.strip() if form.descripcion.data else None,
                duracion_minutos=form.duracion_minutos.data,
                precio_sugerido=form.precio_sugerido.data,
                especie=form.especie.data or None,
                tamano_mascota=form.tamano_mascota.data or None,
                activo=form.activo.data,
            )
            db.session.add(nuevo_servicio)
            db.session.commit()
            flash(f"Servicio de Spa '{nuevo_servicio.nombre}' creado correctamente.", "success")
            return redirect(url_for("spa.servicios_lista"))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al crear servicio de spa")
            flash("Error interno al crear el servicio.", "danger")

    return render_template("spa/form_servicio.html", form=form, titulo="Nuevo Servicio de Spa")


@bp.route("/servicio/<int:id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def servicio_editar(id: int):

    servicio = db.session.get(ServicioSpa, id)
    if not servicio:
        flash("El servicio de spa no existe.", "danger")
        return redirect(url_for("spa.servicios_lista"))

    form = ServicioSpaForm(obj=servicio)
    if form.validate_on_submit():
        try:
            servicio.nombre = form.nombre.data.strip()
            servicio.descripcion = form.descripcion.data.strip() if form.descripcion.data else None
            servicio.duracion_minutos = form.duracion_minutos.data
            servicio.precio_sugerido = form.precio_sugerido.data
            servicio.especie = form.especie.data or None
            servicio.tamano_mascota = form.tamano_mascota.data or None
            servicio.activo = form.activo.data

            db.session.commit()
            flash(f"Servicio de Spa '{servicio.nombre}' actualizado correctamente.", "success")
            return redirect(url_for("spa.servicios_lista"))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al editar servicio de spa %d", id)
            flash("Error al actualizar el servicio.", "danger")

    return render_template("spa/form_servicio.html", form=form, titulo=f"Editar Servicio: {servicio.nombre}")


# ---------------------------------------------------------------------------
# Agenda y Citas de Grooming
# ---------------------------------------------------------------------------


@bp.route("/agenda", methods=["GET"])
@login_required
@agenda_spa_required
def agenda():
    fecha_str = request.args.get("fecha")
    estado_filtro = (request.args.get("estado") or "").strip()

    if fecha_str:
        try:
            fecha_sel = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except ValueError:
            fecha_sel = hoy_bogota()
    else:
        fecha_sel = hoy_bogota()

    inicio_dia = datetime.combine(fecha_sel, time.min, tzinfo=ZONA_BOGOTA)
    fin_dia = datetime.combine(fecha_sel, time.max, tzinfo=ZONA_BOGOTA)

    consulta = (
        select(CitaSpa)
        .filter(CitaSpa.fecha_hora >= inicio_dia, CitaSpa.fecha_hora <= fin_dia)
        .options(
            selectinload(CitaSpa.mascota),
            selectinload(CitaSpa.tutor),
            selectinload(CitaSpa.groomer),
            selectinload(CitaSpa.servicio_spa),
        )
        .order_by(CitaSpa.fecha_hora.asc())
    )

    if estado_filtro in ESTADOS_SPA:
        consulta = consulta.filter(CitaSpa.estado == estado_filtro)

    citas = db.session.execute(consulta).scalars().all()
    form_csrf = SoloCsrfForm()

    return render_template(
        "spa/agenda.html",
        citas=citas,
        fecha_sel=fecha_sel,
        estado_filtro=estado_filtro,
        form_csrf=form_csrf,
    )


@bp.route("/cita/nueva", methods=["GET", "POST"])
@login_required
@agenda_spa_required
def cita_nueva():
    form = CitaSpaForm()

    # Cargar opciones de selects
    tutores = db.session.execute(select(Tutor).filter_by(activo=True).order_by(Tutor.nombre_completo)).scalars().all()
    mascotas = db.session.execute(select(Mascota).filter_by(activo=True).order_by(Mascota.nombre)).scalars().all()
    servicios = db.session.execute(select(ServicioSpa).filter_by(activo=True).order_by(ServicioSpa.nombre)).scalars().all()
    groomers = db.session.execute(select(Usuario).filter(Usuario.activo.is_(True), Usuario.rol.in_(("groomer", "auxiliar", "admin"))).order_by(Usuario.nombre)).scalars().all()

    form.tutor_id.choices = [(t.id, f"{t.nombre_completo} (Doc: {t.documento_texto or 'S/N'})") for t in tutores]
    form.mascota_id.choices = [(m.id, f"{m.nombre} ({m.especie}) - Tutor ID: {m.tutor_id}") for m in mascotas]
    form.servicio_spa_id.choices = [(s.id, f"{s.nombre} (${s.precio_sugerido:,.2f} - {s.duracion_minutos} min)") for s in servicios]
    form.groomer_id.choices = [(0, "-- Sin groomer asignado --")] + [(g.id, f"{g.nombre} ({g.rol.capitalize()})") for g in groomers]

    # Pre-selección por parámetros GET si vienen desde la ficha de mascota o tutor
    mascota_pre = request.args.get("mascota_id", type=int)
    if mascota_pre and not form.is_submitted():
        mascota_obj = db.session.get(Mascota, mascota_pre)
        if mascota_obj:
            form.mascota_id.data = mascota_obj.id
            form.tutor_id.data = mascota_obj.tutor_id

    if not form.is_submitted():
        form.fecha.data = hoy_bogota()
        form.hora.data = obtener_hora_bogota().time().replace(second=0, microsecond=0)

    if form.validate_on_submit():
        try:
            fecha_combinada = datetime.combine(form.fecha.data, form.hora.data, tzinfo=ZONA_BOGOTA)
            nueva_cita = CitaSpa(
                tutor_id=form.tutor_id.data,
                mascota_id=form.mascota_id.data,
                servicio_spa_id=form.servicio_spa_id.data,
                groomer_id=form.groomer_id.data if form.groomer_id.data and form.groomer_id.data > 0 else None,
                fecha_hora=fecha_combinada,
                duracion_minutos=form.duracion_minutos.data,
                estado="programada",
                notas_ingreso=form.notas_ingreso.data.strip() if form.notas_ingreso.data else None,
                creado_por_id=current_user.id,
                fecha_registro=obtener_hora_bogota(),
            )
            db.session.add(nueva_cita)
            db.session.commit()
            flash("Cita de grooming agendada correctamente.", "success")
            return redirect(url_for("spa.agenda", fecha=form.fecha.data.strftime("%Y-%m-%d")))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al agendar cita de spa")
            flash("Error al agendar la cita. Verifica los campos e inténtalo de nuevo.", "danger")

    return render_template("spa/form_cita.html", form=form)


@bp.route("/cita/<int:id>", methods=["GET"])
@login_required
@agenda_spa_required
def cita_detalle(id: int):
    cita = db.session.execute(
        select(CitaSpa)
        .filter_by(id=id)
        .options(
            selectinload(CitaSpa.mascota),
            selectinload(CitaSpa.tutor),
            selectinload(CitaSpa.groomer),
            selectinload(CitaSpa.servicio_spa),
            selectinload(CitaSpa.venta),
            selectinload(CitaSpa.creado_por),
        )
    ).scalar_one_or_none()

    if not cita:
        flash("La cita de spa especificada no existe.", "danger")
        return redirect(url_for("spa.agenda"))

    form_estado = CambioEstadoSpaForm(obj=cita)
    form_venta = VincularVentaSpaForm()
    return render_template("spa/cita_detalle.html", cita=cita, form_estado=form_estado, form_venta=form_venta)


@bp.route("/cita/<int:id>/vincular-venta", methods=["POST"])
@login_required
@spa_required
def cita_vincular_venta(id: int):
    """Asocia una factura ya cobrada en el POS a la cita (requisito para poder entregar)."""
    cita = db.session.get(CitaSpa, id)
    if not cita:
        flash("La cita de spa no existe.", "danger")
        return redirect(url_for("spa.agenda"))

    form = VincularVentaSpaForm()
    if form.validate_on_submit():
        numero = form.numero_factura.data.strip().upper()
        venta = db.session.execute(select(Venta).filter_by(numero_factura=numero)).scalar_one_or_none()
        if venta is None:
            form.numero_factura.errors.append("No existe ninguna factura con ese número.")
        elif venta.estado == "anulada":
            form.numero_factura.errors.append("Esa factura está anulada y no se puede vincular.")
        elif venta.tutor_id != cita.tutor_id:
            form.numero_factura.errors.append("La factura pertenece a otro tutor; verifica el número.")
        else:
            ya_vinculada = db.session.execute(
                select(CitaSpa.id).filter_by(venta_id=venta.id)
            ).scalar_one_or_none()
            if ya_vinculada and ya_vinculada != cita.id:
                form.numero_factura.errors.append("Esa factura ya está vinculada a otra cita de spa.")
            else:
                try:
                    cita.venta_id = venta.id
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    current_app.logger.exception("Error al vincular venta a la cita %d", id)
                    flash("No se pudo vincular la factura. Inténtalo de nuevo.", "danger")
                else:
                    flash(f"Factura {venta.numero_factura} vinculada correctamente.", "success")
                return redirect(url_for("spa.cita_detalle", id=id))

    for errores in form.numero_factura.errors:
        flash(errores, "danger")
    return redirect(url_for("spa.cita_detalle", id=id))


@bp.route("/cita/<int:id>/estado", methods=["POST"])
@login_required
@spa_required
def cita_cambiar_estado(id: int):
    cita = db.session.get(CitaSpa, id)
    if not cita:
        flash("La cita de spa no existe.", "danger")
        return redirect(url_for("spa.agenda"))

    nuevo_estado = request.form.get("estado")
    notas_salida = request.form.get("notas_salida", "").strip()

    # Regla de negocio: una orden no puede entregarse sin estar pagada
    # (asociada a una venta). Evita que la mascota salga sin cobrar el servicio.
    if nuevo_estado == "entregado" and not cita.venta_id:
        flash(
            "No se puede entregar sin cobrar. Registra el pago en el Punto de Venta y asócialo a esta cita antes de continuar.",
            "danger",
        )
        return redirect(url_for("spa.cita_detalle", id=id))

    if nuevo_estado in ESTADOS_SPA:
        try:
            cita.estado = nuevo_estado
            if notas_salida:
                cita.notas_salida = notas_salida

            db.session.commit()

            if nuevo_estado == "listo_recogida":
                flash(f"¡{cita.mascota.nombre} está listo/a! Puedes enviar el aviso por WhatsApp.", "success")
            else:
                flash(f"Estado de la cita actualizado a '{ESTADOS_SPA[nuevo_estado]}'.", "info")

            return redirect(url_for("spa.cita_detalle", id=id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al cambiar estado de la cita %d", id)
            flash("Error al actualizar el estado.", "danger")

    flash("Estado no válido.", "danger")
    return redirect(url_for("spa.cita_detalle", id=id))


@bp.route("/cita/<int:id>/notificado-wa", methods=["POST"])
@login_required
@spa_required
def cita_marcar_wa(id: int):
    cita = db.session.get(CitaSpa, id)
    if not cita:
        return jsonify(error="Cita no encontrada"), 404
    try:
        cita.notificado_whatsapp = True
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error al marcar como notificada la cita %d", id)
        return jsonify(error="No se pudo registrar la notificación."), 500
    return jsonify(ok=True)
