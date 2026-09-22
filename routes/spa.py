"""Módulo de Spa, Peluquería y Grooming de Mascotas.

Gestión del catálogo de servicios de estética, agendamiento de citas,
control de flujo de estados (programada -> en proceso -> listo -> entregado),
generación de notificaciones de aviso por WhatsApp y cobro directo en POS.
"""

from datetime import datetime, time, timedelta
from typing import Optional

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from decorators import agenda_spa_required, admin_required, spa_required
from pdf_generator import generar_pdf_spa
from flask_login import current_user, login_required
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from forms import (
    CambioEstadoSpaForm,
    CitaSpaForm,
    FotoSpaModalForm,
    ServicioSpaForm,
    SoloCsrfForm,
    VincularVentaSpaForm,
)
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
from utils import ZONA_BOGOTA, eliminar_imagen, guardar_imagen, hoy_bogota, obtener_hora_bogota

bp = Blueprint("spa", __name__, url_prefix="/spa")


def _procesar_foto_spa(form_campo) -> str | None:
    """Guarda una foto subida para spa si existe. Devuelve el nombre generado o None."""
    if form_campo.data and hasattr(form_campo.data, "filename") and form_campo.data.filename:
        try:
            return guardar_imagen(form_campo.data, subcarpeta="spa")
        except ValueError as exc:
            form_campo.errors.append(str(exc))
    return None


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


@bp.route("/servicio/<int:id>/eliminar", methods=["POST"])
@login_required
@admin_required
def servicio_eliminar(id: int):
    servicio = db.session.get(ServicioSpa, id)
    if not servicio:
        flash("El servicio de spa no existe o ya fue eliminado.", "danger")
        return redirect(url_for("spa.servicios_lista"))

    form = SoloCsrfForm()
    if not form.validate_on_submit():
        flash("Error de validación de seguridad (CSRF).", "danger")
        return redirect(url_for("spa.servicios_lista"))

    tiene_citas = db.session.execute(select(CitaSpa.id).filter_by(servicio_spa_id=servicio.id).limit(1)).scalar_one_or_none()

    try:
        if tiene_citas:
            servicio.activo = False
            db.session.commit()
            flash(
                f"El servicio '{servicio.nombre}' tiene citas previas registradas en el historial. Para conservar la integridad histórica, ha sido desactivado del catálogo.",
                "warning",
            )
        else:
            nombre = servicio.nombre
            db.session.delete(servicio)
            db.session.commit()
            flash(f"Servicio de Spa '{nombre}' eliminado definitivamente.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error al eliminar servicio de spa %d", id)
        flash("Error interno al eliminar el servicio de spa.", "danger")

    return redirect(url_for("spa.servicios_lista"))


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

    fecha_anterior = fecha_sel - timedelta(days=1)
    fecha_siguiente = fecha_sel + timedelta(days=1)

    return render_template(
        "spa/agenda.html",
        citas=citas,
        fecha_sel=fecha_sel,
        fecha_anterior=fecha_anterior,
        fecha_siguiente=fecha_siguiente,
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
    mascotas = db.session.execute(
        select(Mascota).filter_by(activo=True).options(selectinload(Mascota.tutor)).order_by(Mascota.nombre)
    ).scalars().all()
    servicios = db.session.execute(select(ServicioSpa).filter_by(activo=True).order_by(ServicioSpa.nombre)).scalars().all()
    groomers = db.session.execute(select(Usuario).filter(Usuario.activo.is_(True), Usuario.rol.in_(("groomer", "auxiliar", "admin"))).order_by(Usuario.nombre)).scalars().all()

    form.tutor_id.choices = [(t.id, f"{t.nombre_completo} (Doc: {t.documento_texto or 'S/N'})") for t in tutores]
    form.mascota_id.choices = [
        (m.id, f"{m.nombre} ({m.especie_etiqueta}) - Tutor: {m.tutor.nombre_completo if m.tutor else 'Sin tutor'}")
        for m in mascotas
    ]
    form.servicio_spa_id.choices = [(s.id, f"{s.nombre} (${s.precio_sugerido:,.0f} - {s.duracion_minutos} min)") for s in servicios]
    form.groomer_id.choices = [(0, "-- Sin groomer asignado --")] + [(g.id, f"{g.nombre} ({g.rol.capitalize()})") for g in groomers]

    mascotas_data = [
        {"id": m.id, "nombre": m.nombre, "especie": m.especie_etiqueta, "emoji": m.especie_emoji, "tutor_id": m.tutor_id}
        for m in mascotas
    ]

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
        nombre_foto_ingreso = _procesar_foto_spa(form.foto_ingreso)
        if not form.foto_ingreso.errors:
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
                    foto_ingreso=nombre_foto_ingreso,
                    creado_por_id=current_user.id,
                    fecha_registro=obtener_hora_bogota(),
                )
                db.session.add(nueva_cita)
                db.session.commit()
                flash("Cita de grooming agendada correctamente.", "success")
                return redirect(url_for("spa.agenda", fecha=form.fecha.data.strftime("%Y-%m-%d")))
            except Exception:
                db.session.rollback()
                if nombre_foto_ingreso:
                    eliminar_imagen("spa", nombre_foto_ingreso)
                current_app.logger.exception("Error al agendar cita de spa")
                flash("Error al agendar la cita. Verifica los campos e inténtalo de nuevo.", "danger")

    return render_template("spa/form_cita.html", form=form, mascotas_data=mascotas_data)


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

    # Cargar citas previas de spa de la misma mascota para consultar looks / notas anteriores ("Como la última vez")
    citas_previas = db.session.execute(
        select(CitaSpa)
        .filter(CitaSpa.mascota_id == cita.mascota_id, CitaSpa.id != cita.id)
        .options(
            selectinload(CitaSpa.servicio_spa),
            selectinload(CitaSpa.groomer),
        )
        .order_by(CitaSpa.fecha_hora.desc())
        .limit(6)
    ).scalars().all()

    form_estado = CambioEstadoSpaForm(obj=cita)
    form_venta = VincularVentaSpaForm()
    form_foto = FotoSpaModalForm()
    return render_template(
        "spa/cita_detalle.html",
        cita=cita,
        citas_previas=citas_previas,
        form_estado=form_estado,
        form_venta=form_venta,
        form_foto=form_foto,
    )


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


@bp.route("/cita/<int:id>/foto", methods=["POST"])
@login_required
@spa_required
def cita_subir_foto(id: int):
    """Sube o actualiza la foto de ingreso o salida de una cita de spa."""
    cita = db.session.get(CitaSpa, id)
    if not cita:
        flash("La cita de spa no existe.", "danger")
        return redirect(url_for("spa.agenda"))

    form = FotoSpaModalForm()
    if form.validate_on_submit():
        tipo = form.tipo.data  # 'ingreso' o 'salida'
        if tipo not in ("ingreso", "salida"):
            flash("Tipo de foto no válido.", "danger")
            return redirect(url_for("spa.cita_detalle", id=id))

        try:
            nombre_foto = guardar_imagen(form.foto.data, subcarpeta="spa")
            if tipo == "ingreso":
                anterior = cita.foto_ingreso
                cita.foto_ingreso = nombre_foto
                flash("Foto de ingreso guardada exitosamente.", "success")
            else:
                anterior = cita.foto_salida
                cita.foto_salida = nombre_foto
                # Regla de negocio: al registrar la foto de salida, el estado cambia automáticamente a 'listo_recogida'
                if cita.estado in ("programada", "en_proceso"):
                    cita.estado = "listo_recogida"
                    if not cita.fecha_listo:
                        cita.fecha_listo = obtener_hora_bogota()
                    flash(f"¡Foto de salida guardada! {cita.mascota.nombre} cambió automáticamente a 'Listo para recogida'. Ya puedes enviar la notificación por WhatsApp.", "success")
                else:
                    flash("Foto de salida guardada exitosamente.", "success")

            db.session.commit()
            if anterior:
                eliminar_imagen("spa", anterior)
        except ValueError as exc:
            flash(str(exc), "danger")
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al subir foto de spa %d", id)
            flash("Ocurrió un error al guardar la foto.", "danger")
    else:
        for errs in form.foto.errors:
            flash(errs, "danger")

    return redirect(url_for("spa.cita_detalle", id=id))


@bp.route("/cita/<int:id>/pdf", methods=["GET"])
def cita_spa_pdf(id: int):
    """Descarga el Certificado Oficial de Atención de Spa en PDF."""
    cita = db.session.execute(
        select(CitaSpa)
        .filter_by(id=id)
        .options(
            selectinload(CitaSpa.mascota).selectinload(Mascota.raza),
            selectinload(CitaSpa.tutor),
            selectinload(CitaSpa.servicio_spa),
            selectinload(CitaSpa.groomer),
        )
    ).scalar_one_or_none()
    if not cita:
        flash("La cita de spa no existe.", "danger")
        return redirect(url_for("spa.agenda"))

    pdf_buffer = generar_pdf_spa(cita, db.session)
    nombre_archivo = f"Spa_{cita.mascota.nombre if cita.mascota else 'Paciente'}_{cita.id:04d}.pdf"
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=nombre_archivo,
    )


@bp.route("/cita/<int:id>/foto/<string:tipo>/eliminar", methods=["POST"])
@login_required
@spa_required
def cita_eliminar_foto(id: int, tipo: str):
    """Elimina la foto de ingreso o salida de la cita de spa."""
    cita = db.session.get(CitaSpa, id)
    if not cita:
        flash("La cita no existe.", "danger")
        return redirect(url_for("spa.agenda"))

    if tipo not in ("ingreso", "salida"):
        flash("Tipo de foto no válido.", "danger")
        return redirect(url_for("spa.cita_detalle", id=id))

    foto_eliminar = cita.foto_ingreso if tipo == "ingreso" else cita.foto_salida
    if foto_eliminar:
        try:
            if tipo == "ingreso":
                cita.foto_ingreso = None
            else:
                cita.foto_salida = None
            db.session.commit()
            eliminar_imagen("spa", foto_eliminar)
            flash(f"Foto de {tipo} eliminada.", "info")
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al eliminar foto de spa %d", id)
            flash("No se pudo eliminar la foto.", "danger")

    return redirect(url_for("spa.cita_detalle", id=id))


@bp.route("/cita/<int:id>/estado", methods=["POST"])
@login_required
@spa_required
def cita_cambiar_estado(id: int):
    cita = db.session.get(CitaSpa, id)
    if not cita:
        flash("La cita de spa no existe.", "danger")
        return redirect(url_for("spa.agenda"))

    form = CambioEstadoSpaForm()
    nuevo_estado = request.form.get("estado")
    notas_salida = request.form.get("notas_salida", "").strip()

    if nuevo_estado == "entregado" and not cita.venta_id:
        flash(
            f"No se puede entregar a {cita.mascota.nombre} sin registrar el cobro en POS primero.",
            "warning",
        )
        next_url = request.form.get("next")
        if next_url:
            return redirect(next_url)
        return redirect(url_for("spa.cita_detalle", id=id))

    if nuevo_estado in ESTADOS_SPA:
        foto_ingreso_subida = _procesar_foto_spa(form.foto_ingreso)
        foto_salida_subida = _procesar_foto_spa(form.foto_salida)

        try:
            cita.estado = nuevo_estado
            if nuevo_estado == "listo_recogida" and not cita.fecha_listo:
                cita.fecha_listo = obtener_hora_bogota()
            if "notas_salida" in request.form:
                cita.notas_salida = notas_salida if notas_salida else None

            if foto_ingreso_subida:
                ant_ingreso = cita.foto_ingreso
                cita.foto_ingreso = foto_ingreso_subida
                if ant_ingreso:
                    eliminar_imagen("spa", ant_ingreso)

            if foto_salida_subida:
                ant_salida = cita.foto_salida
                cita.foto_salida = foto_salida_subida
                if ant_salida:
                    eliminar_imagen("spa", ant_salida)

            db.session.commit()

            next_url = request.form.get("next")
            if next_url:
                if nuevo_estado == "entregado":
                    flash(f"¡{cita.mascota.nombre} entregado/a a su tutor exitosamente!", "success")
                elif nuevo_estado == "listo_recogida":
                    flash(f"¡{cita.mascota.nombre} marcado como listo para recogida!", "success")
                return redirect(next_url)

            if nuevo_estado == "listo_recogida":
                flash(f"¡{cita.mascota.nombre} está listo/a! Puedes enviar el aviso por WhatsApp.", "success")
            else:
                flash(f"Estado de la cita actualizado a '{ESTADOS_SPA[nuevo_estado]}'.", "info")

            return redirect(url_for("spa.cita_detalle", id=id))
        except Exception:
            db.session.rollback()
            if foto_ingreso_subida:
                eliminar_imagen("spa", foto_ingreso_subida)
            if foto_salida_subida:
                eliminar_imagen("spa", foto_salida_subida)
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


@bp.route("/cita/<int:id>/eliminar", methods=["POST"])
@login_required
@spa_required
def cita_eliminar(id: int):
    cita = db.session.get(CitaSpa, id)
    if not cita:
        flash("La cita de spa no existe o ya fue eliminada.", "danger")
        next_url = request.form.get("next")
        return redirect(next_url or url_for("spa.agenda"))

    form = SoloCsrfForm()
    if not form.validate_on_submit():
        flash("Error de validación de seguridad (CSRF).", "danger")
        next_url = request.form.get("next")
        return redirect(next_url or url_for("spa.agenda"))

    # Si tiene venta facturada en POS y no está anulada, prevenir borrado accidental
    if cita.venta_id and cita.venta and cita.venta.estado != "anulada":
        flash(
            f"No se puede eliminar la cita #{cita.id} porque tiene vinculada la factura {cita.venta.numero_factura} en POS. Si deseas eliminarla, primero anula o desvincula la factura.",
            "warning",
        )
        next_url = request.form.get("next")
        return redirect(next_url or url_for("spa.cita_detalle", id=id))

    try:
        mascota_nombre = cita.mascota.nombre if cita.mascota else "Paciente"
        foto_ingreso = cita.foto_ingreso
        foto_salida = cita.foto_salida

        db.session.delete(cita)
        db.session.commit()

        if foto_ingreso:
            eliminar_imagen("spa", foto_ingreso)
        if foto_salida:
            eliminar_imagen("spa", foto_salida)

        flash(f"La cita de spa de {mascota_nombre} ha sido eliminada correctamente.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error al eliminar cita de spa %d", id)
        flash("Error interno al intentar eliminar la cita de spa.", "danger")

    next_url = request.form.get("next")
    return redirect(next_url or url_for("spa.agenda"))

