"""Rutas y controladores para Historias Clínicas, Consultas SOAP, Vacunas y Desparasitaciones."""

from datetime import datetime
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from forms import ConsultaMedicaForm, DesparasitacionMascotaForm, VacunaMascotaForm
from models import ConsultaMedica, DesparasitacionMascota, Mascota, RegistroPeso, Tutor, VacunaMascota, db
from utils import ZONA_BOGOTA, hoy_bogota, normalizar_texto, obtener_hora_bogota

bp = Blueprint("historias", __name__, url_prefix="/historias")


# ---------------------------------------------------------------------------
# Buscador y Ficha Médica Unificada
# ---------------------------------------------------------------------------


@bp.route("/", methods=["GET"])
@login_required
def lista():
    q = (request.args.get("q") or "").strip()
    normalizado = normalizar_texto(q)

    consulta = (
        select(Mascota)
        .filter(Mascota.activo.is_(True))
        .options(selectinload(Mascota.tutor), selectinload(Mascota.raza))
        .order_by(Mascota.nombre.asc())
    )

    if normalizado:
        consulta = consulta.join(Tutor).filter(
            or_(
                Mascota.nombre_busqueda.ilike(f"%{normalizado}%"),
                Tutor.nombre_busqueda.ilike(f"%{normalizado}%"),
                Tutor.numero_documento.ilike(f"%{normalizado}%"),
                Mascota.microchip.ilike(f"%{normalizado}%"),
            )
        )

    mascotas = db.session.execute(consulta.limit(50)).scalars().all()
    return render_template("historias/lista.html", mascotas=mascotas, q=q)


@bp.route("/mascota/<int:mascota_id>", methods=["GET"])
@login_required
def ficha_medica(mascota_id: int):
    mascota = db.session.execute(
        select(Mascota)
        .filter_by(id=mascota_id)
        .options(
            selectinload(Mascota.tutor),
            selectinload(Mascota.raza),
            selectinload(Mascota.consultas).selectinload(ConsultaMedica.veterinario),
            selectinload(Mascota.vacunas),
            selectinload(Mascota.desparasitaciones),
            selectinload(Mascota.registros_peso),
        )
    ).scalar_one_or_none()

    if not mascota:
        flash("La mascota no existe.", "danger")
        return redirect(url_for("historias.lista"))

    return render_template("historias/ficha_medica.html", mascota=mascota)


# ---------------------------------------------------------------------------
# Consultas Médicas (SOAP)
# ---------------------------------------------------------------------------


@bp.route("/mascota/<int:mascota_id>/consulta/nueva", methods=["GET", "POST"])
@login_required
def consulta_nueva(mascota_id: int):
    mascota = db.session.get(Mascota, mascota_id)
    if not mascota:
        flash("La mascota no existe.", "danger")
        return redirect(url_for("historias.lista"))

    form = ConsultaMedicaForm()
    if not form.is_submitted():
        # Prellenar peso actual si existe
        if mascota.peso_actual:
            form.peso_kg.data = mascota.peso_actual

    if form.validate_on_submit():
        try:
            consulta = ConsultaMedica(
                mascota_id=mascota.id,
                tutor_id=mascota.tutor_id,
                veterinario_id=current_user.id,
                fecha_hora=obtener_hora_bogota(),
                motivo_consulta=form.motivo_consulta.data.strip(),
                anamnesis=form.anamnesis.data.strip() if form.anamnesis.data else None,
                peso_kg=form.peso_kg.data,
                temperatura_c=form.temperatura_c.data,
                frecuencia_cardiaca=form.frecuencia_cardiaca.data,
                frecuencia_respiratoria=form.frecuencia_respiratoria.data,
                tllc_segundos=form.tllc_segundos.data,
                mucosas=form.mucosas.data or None,
                condicion_corporal=form.condicion_corporal.data or None,
                examen_sistemas=form.examen_sistemas.data.strip() if form.examen_sistemas.data else None,
                diagnostico=form.diagnostico.data.strip(),
                plan_tratamiento=form.plan_tratamiento.data.strip(),
                receta_medica=form.receta_medica.data.strip() if form.receta_medica.data else None,
                observaciones=form.observaciones.data.strip() if form.observaciones.data else None,
                creado_por_id=current_user.id,
            )
            db.session.add(consulta)

            # Actualizar peso de la mascota si se registró uno nuevo
            if form.peso_kg.data and form.peso_kg.data != mascota.peso_actual:
                mascota.peso_actual = form.peso_kg.data

            db.session.commit()
            flash("Consulta médica (SOAP) guardada correctamente.", "success")
            return redirect(url_for("historias.ficha_medica", mascota_id=mascota.id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al guardar consulta médica")
            flash("Ocurrió un error al guardar la consulta.", "danger")

    return render_template("historias/form_consulta.html", form=form, mascota=mascota)


@bp.route("/consulta/<int:id>", methods=["GET"])
@login_required
def consulta_detalle(id: int):
    consulta = db.session.execute(
        select(ConsultaMedica)
        .filter_by(id=id)
        .options(
            selectinload(ConsultaMedica.mascota).selectinload(Mascota.raza),
            selectinload(ConsultaMedica.tutor),
            selectinload(ConsultaMedica.veterinario),
        )
    ).scalar_one_or_none()

    if not consulta:
        flash("La consulta médica no existe.", "danger")
        return redirect(url_for("historias.lista"))

    return render_template("historias/consulta_detalle.html", consulta=consulta)


# ---------------------------------------------------------------------------
# Vacunación
# ---------------------------------------------------------------------------


@bp.route("/mascota/<int:mascota_id>/vacuna/nueva", methods=["GET", "POST"])
@login_required
def vacuna_nueva(mascota_id: int):
    mascota = db.session.get(Mascota, mascota_id)
    if not mascota:
        flash("La mascota no existe.", "danger")
        return redirect(url_for("historias.lista"))

    form = VacunaMascotaForm()
    if not form.is_submitted():
        form.fecha_aplicacion.data = hoy_bogota()

    if form.validate_on_submit():
        try:
            vacuna = VacunaMascota(
                mascota_id=mascota.id,
                tutor_id=mascota.tutor_id,
                veterinario_id=current_user.id,
                nombre_vacuna=form.nombre_vacuna.data.strip(),
                lote=form.lote.data.strip() if form.lote.data else None,
                laboratorio=form.laboratorio.data.strip() if form.laboratorio.data else None,
                dosis=form.dosis.data.strip(),
                fecha_aplicacion=form.fecha_aplicacion.data,
                fecha_proxima=form.fecha_proxima.data,
                observaciones=form.observaciones.data.strip() if form.observaciones.data else None,
                creado_por_id=current_user.id,
            )
            db.session.add(vacuna)
            db.session.commit()
            flash(f"Vacuna '{vacuna.nombre_vacuna}' registrada exitosamente.", "success")
            return redirect(url_for("historias.ficha_medica", mascota_id=mascota.id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al registrar vacuna")
            flash("Error al registrar la vacuna.", "danger")
    elif form.is_submitted():
        print("FORM VACUNA ERRORS:", form.errors)

    return render_template("historias/form_vacuna.html", form=form, mascota=mascota)


# ---------------------------------------------------------------------------
# Desparasitación
# ---------------------------------------------------------------------------


@bp.route("/mascota/<int:mascota_id>/desparasitacion/nueva", methods=["GET", "POST"])
@login_required
def desparasitacion_nueva(mascota_id: int):
    mascota = db.session.get(Mascota, mascota_id)
    if not mascota:
        flash("La mascota no existe.", "danger")
        return redirect(url_for("historias.lista"))

    form = DesparasitacionMascotaForm()
    if not form.is_submitted():
        form.fecha_aplicacion.data = hoy_bogota()
        if mascota.peso_actual:
            form.peso_kg.data = mascota.peso_actual

    if form.validate_on_submit():
        try:
            desparasitacion = DesparasitacionMascota(
                mascota_id=mascota.id,
                tutor_id=mascota.tutor_id,
                veterinario_id=current_user.id,
                producto=form.producto.data.strip(),
                tipo=form.tipo.data,
                dosis=form.dosis.data.strip() if form.dosis.data else None,
                peso_kg=form.peso_kg.data,
                fecha_aplicacion=form.fecha_aplicacion.data,
                fecha_proxima=form.fecha_proxima.data,
                observaciones=form.observaciones.data.strip() if form.observaciones.data else None,
                creado_por_id=current_user.id,
            )
            db.session.add(desparasitacion)
            db.session.commit()
            flash(f"Desparasitación '{desparasitacion.producto}' registrada.", "success")
            return redirect(url_for("historias.ficha_medica", mascota_id=mascota.id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al registrar desparasitación")
            flash("Error al registrar desparasitación.", "danger")

    return render_template("historias/form_desparasitacion.html", form=form, mascota=mascota)
