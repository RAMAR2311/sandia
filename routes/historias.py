"""Rutas y controladores para Historias Clínicas, Consultas SOAP, Vacunas y Desparasitaciones."""

from datetime import datetime
from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from decorators import clinico_required
from flask_login import current_user, login_required
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from forms import (
    AltaHospitalizacionForm,
    CirugiaForm,
    ConsultaMedicaForm,
    DesparasitacionMascotaForm,
    EnmiendaConsultaForm,
    EvolucionHospitalariaForm,
    ExamenLaboratorioForm,
    HospitalizacionForm,
    NotasPostquirurgicasForm,
    ResultadoExamenForm,
    VacunaMascotaForm,
)
from models import (
    Cirugia,
    ConsultaMedica,
    DesparasitacionMascota,
    EnmiendaConsulta,
    EvolucionHospitalaria,
    ExamenLaboratorio,
    Hospitalizacion,
    Mascota,
    RegistroPeso,
    Tutor,
    VacunaMascota,
    db,
)
from utils import (
    ZONA_BOGOTA,
    eliminar_documento,
    guardar_documento,
    hoy_bogota,
    normalizar_texto,
    obtener_hora_bogota,
)

bp = Blueprint("historias", __name__, url_prefix="/historias")


# ---------------------------------------------------------------------------
# Buscador y Ficha Médica Unificada
# ---------------------------------------------------------------------------


@bp.route("/", methods=["GET"])
@login_required
@clinico_required
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
@clinico_required
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

    hospitalizaciones = db.session.execute(
        select(Hospitalizacion).filter_by(mascota_id=mascota.id).order_by(Hospitalizacion.fecha_ingreso.desc())
    ).scalars().all()
    cirugias = db.session.execute(
        select(Cirugia).filter_by(mascota_id=mascota.id).order_by(Cirugia.fecha.desc())
    ).scalars().all()
    examenes = db.session.execute(
        select(ExamenLaboratorio).filter_by(mascota_id=mascota.id).order_by(ExamenLaboratorio.fecha_toma.desc())
    ).scalars().all()

    return render_template(
        "historias/ficha_medica.html",
        mascota=mascota,
        hospitalizaciones=hospitalizaciones,
        cirugias=cirugias,
        examenes=examenes,
    )


# ---------------------------------------------------------------------------
# Consultas Médicas (SOAP)
# ---------------------------------------------------------------------------


@bp.route("/mascota/<int:mascota_id>/consulta/nueva", methods=["GET", "POST"])
@login_required
@clinico_required
def consulta_nueva(mascota_id: int):
    mascota = db.session.get(Mascota, mascota_id)
    if not mascota:
        flash("La mascota no existe.", "danger")
        return redirect(url_for("historias.lista"))

    form = ConsultaMedicaForm()
    if not form.is_submitted():
        # Prellenar peso actual si existe
        if mascota.peso_actual:
            form.peso_kg.data = mascota.peso_actual.peso_kg

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
            if form.peso_kg.data and (not mascota.peso_actual or form.peso_kg.data != mascota.peso_actual.peso_kg):
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
@clinico_required
def consulta_detalle(id: int):
    consulta = db.session.execute(
        select(ConsultaMedica)
        .filter_by(id=id)
        .options(
            selectinload(ConsultaMedica.mascota).selectinload(Mascota.raza),
            selectinload(ConsultaMedica.tutor),
            selectinload(ConsultaMedica.veterinario),
            selectinload(ConsultaMedica.enmiendas).selectinload(EnmiendaConsulta.autor),
        )
    ).scalar_one_or_none()

    if not consulta:
        flash("La consulta médica no existe.", "danger")
        return redirect(url_for("historias.lista"))

    return render_template("historias/consulta_detalle.html", consulta=consulta, form_enmienda=EnmiendaConsultaForm())


# ---------------------------------------------------------------------------
# Vacunación
# ---------------------------------------------------------------------------


@bp.route("/mascota/<int:mascota_id>/vacuna/nueva", methods=["GET", "POST"])
@login_required
@clinico_required
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
        current_app.logger.debug("Errores de validación en formulario de vacuna: %s", form.errors)

    return render_template("historias/form_vacuna.html", form=form, mascota=mascota)


# ---------------------------------------------------------------------------
# Desparasitación
# ---------------------------------------------------------------------------


@bp.route("/mascota/<int:mascota_id>/desparasitacion/nueva", methods=["GET", "POST"])
@login_required
@clinico_required
def desparasitacion_nueva(mascota_id: int):
    mascota = db.session.get(Mascota, mascota_id)
    if not mascota:
        flash("La mascota no existe.", "danger")
        return redirect(url_for("historias.lista"))

    form = DesparasitacionMascotaForm()
    if not form.is_submitted():
        form.fecha_aplicacion.data = hoy_bogota()
        if mascota.peso_actual:
            form.peso_kg.data = mascota.peso_actual.peso_kg

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


# ---------------------------------------------------------------------------
# Enmienda de historia clínica (consulta inmutable, corrección aparte)
# ---------------------------------------------------------------------------


@bp.route("/consulta/<int:id>/enmienda", methods=["POST"])
@login_required
@clinico_required
def consulta_enmienda(id: int):
    consulta = db.session.get(ConsultaMedica, id)
    if not consulta:
        flash("La consulta no existe.", "danger")
        return redirect(url_for("historias.lista"))
    form = EnmiendaConsultaForm()
    if form.validate_on_submit():
        try:
            db.session.add(EnmiendaConsulta(consulta_id=consulta.id, autor_id=current_user.id, texto=form.texto.data))
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al agregar enmienda a la consulta %d", id)
            flash("No se pudo guardar la enmienda.", "danger")
        else:
            flash("Enmienda agregada. La consulta original no se modifica.", "success")
    else:
        flash("Escribe el texto de la enmienda (mínimo 5 caracteres).", "danger")
    return redirect(url_for("historias.consulta_detalle", id=id))


# ---------------------------------------------------------------------------
# Hospitalización
# ---------------------------------------------------------------------------


@bp.route("/mascota/<int:mascota_id>/hospitalizacion/nueva", methods=["GET", "POST"])
@login_required
@clinico_required
def hospitalizacion_nueva(mascota_id: int):
    mascota = db.session.get(Mascota, mascota_id)
    if not mascota:
        flash("La mascota no existe.", "danger")
        return redirect(url_for("historias.lista"))

    form = HospitalizacionForm(mascota_id=str(mascota_id))
    if form.validate_on_submit():
        hosp = Hospitalizacion(
            mascota_id=mascota.id,
            tutor_id=mascota.tutor_id,
            veterinario_responsable_id=current_user.id,
            motivo=form.motivo.data,
            diagnostico=form.diagnostico.data,
            jaula=form.jaula.data,
            costo_dia=form.costo_dia.data or 0,
            creado_por_id=current_user.id,
        )
        try:
            db.session.add(hosp)
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al registrar hospitalización")
            flash("No se pudo registrar el ingreso.", "danger")
        else:
            flash(f"{mascota.nombre} quedó hospitalizado/a.", "success")
            return redirect(url_for("historias.hospitalizacion_detalle", id=hosp.id))
    return render_template("historias/form_hospitalizacion.html", form=form, mascota=mascota)


@bp.route("/hospitalizacion/<int:id>", methods=["GET"])
@login_required
@clinico_required
def hospitalizacion_detalle(id: int):
    hosp = db.session.execute(
        select(Hospitalizacion)
        .filter_by(id=id)
        .options(selectinload(Hospitalizacion.mascota), selectinload(Hospitalizacion.tutor), selectinload(Hospitalizacion.evoluciones))
    ).scalar_one_or_none()
    if not hosp:
        flash("La hospitalización no existe.", "danger")
        return redirect(url_for("historias.lista"))
    return render_template(
        "historias/hospitalizacion_detalle.html",
        hosp=hosp,
        form_evolucion=EvolucionHospitalariaForm(),
        form_alta=AltaHospitalizacionForm(),
    )


@bp.route("/hospitalizacion/<int:id>/evolucion", methods=["POST"])
@login_required
@clinico_required
def hospitalizacion_evolucion(id: int):
    hosp = db.session.get(Hospitalizacion, id)
    if not hosp:
        flash("La hospitalización no existe.", "danger")
        return redirect(url_for("historias.lista"))
    form = EvolucionHospitalariaForm()
    if form.validate_on_submit():
        try:
            db.session.add(EvolucionHospitalaria(
                hospitalizacion_id=hosp.id,
                usuario_id=current_user.id,
                constantes=form.constantes.data,
                tratamiento_aplicado=form.tratamiento_aplicado.data,
                alimentacion=form.alimentacion.data,
                eliminaciones=form.eliminaciones.data,
                observaciones=form.observaciones.data,
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al registrar evolución de hospitalización %d", id)
            flash("No se pudo registrar la evolución.", "danger")
        else:
            flash("Evolución registrada.", "success")
    return redirect(url_for("historias.hospitalizacion_detalle", id=id))


@bp.route("/hospitalizacion/<int:id>/egreso", methods=["POST"])
@login_required
@clinico_required
def hospitalizacion_egreso(id: int):
    hosp = db.session.get(Hospitalizacion, id)
    if not hosp:
        flash("La hospitalización no existe.", "danger")
        return redirect(url_for("historias.lista"))
    form = AltaHospitalizacionForm()
    if form.validate_on_submit():
        try:
            hosp.estado = form.estado.data
            hosp.fecha_egreso = obtener_hora_bogota()
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al registrar egreso de hospitalización %d", id)
            flash("No se pudo registrar el egreso.", "danger")
        else:
            flash("Egreso registrado.", "success")
    return redirect(url_for("historias.hospitalizacion_detalle", id=id))


# ---------------------------------------------------------------------------
# Cirugías
# ---------------------------------------------------------------------------


@bp.route("/mascota/<int:mascota_id>/cirugia/nueva", methods=["GET", "POST"])
@login_required
@clinico_required
def cirugia_nueva(mascota_id: int):
    mascota = db.session.get(Mascota, mascota_id)
    if not mascota:
        flash("La mascota no existe.", "danger")
        return redirect(url_for("historias.lista"))

    form = CirugiaForm(mascota_id=str(mascota_id))
    if form.validate_on_submit():
        nombre_archivo = None
        if form.archivo_consentimiento.data and getattr(form.archivo_consentimiento.data, "filename", ""):
            try:
                nombre_archivo = guardar_documento(form.archivo_consentimiento.data, "cirugias")
            except ValueError as exc:
                form.archivo_consentimiento.errors.append(str(exc))

        if not form.archivo_consentimiento.errors:
            cirugia = Cirugia(
                mascota_id=mascota.id,
                tutor_id=mascota.tutor_id,
                veterinario_id=current_user.id,
                tipo_procedimiento=form.tipo_procedimiento.data,
                fecha=datetime.combine(form.fecha.data, datetime.min.time(), tzinfo=ZONA_BOGOTA),
                consentimiento_firmado=form.consentimiento_firmado.data,
                archivo_consentimiento=nombre_archivo,
                notas_prequirurgicas=form.notas_prequirurgicas.data,
                protocolo_anestesico=form.protocolo_anestesico.data,
                creado_por_id=current_user.id,
            )
            try:
                db.session.add(cirugia)
                db.session.commit()
            except Exception:
                db.session.rollback()
                if nombre_archivo:
                    eliminar_documento("cirugias", nombre_archivo)
                current_app.logger.exception("Error al registrar cirugía")
                flash("No se pudo registrar la cirugía.", "danger")
            else:
                flash("Cirugía registrada.", "success")
                return redirect(url_for("historias.cirugia_detalle", id=cirugia.id))
    return render_template("historias/form_cirugia.html", form=form, mascota=mascota)


@bp.route("/cirugia/<int:id>", methods=["GET"])
@login_required
@clinico_required
def cirugia_detalle(id: int):
    cirugia = db.session.execute(
        select(Cirugia).filter_by(id=id).options(selectinload(Cirugia.mascota), selectinload(Cirugia.tutor), selectinload(Cirugia.veterinario))
    ).scalar_one_or_none()
    if not cirugia:
        flash("La cirugía no existe.", "danger")
        return redirect(url_for("historias.lista"))
    return render_template("historias/cirugia_detalle.html", cirugia=cirugia, form_notas=NotasPostquirurgicasForm(notas_postquirurgicas=cirugia.notas_postquirurgicas or ""))


@bp.route("/cirugia/<int:id>/notas", methods=["POST"])
@login_required
@clinico_required
def cirugia_notas(id: int):
    cirugia = db.session.get(Cirugia, id)
    if not cirugia:
        flash("La cirugía no existe.", "danger")
        return redirect(url_for("historias.lista"))
    form = NotasPostquirurgicasForm()
    if form.validate_on_submit():
        try:
            cirugia.notas_postquirurgicas = form.notas_postquirurgicas.data
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al guardar notas postquirúrgicas de la cirugía %d", id)
            flash("No se pudieron guardar las notas.", "danger")
        else:
            flash("Notas guardadas.", "success")
    return redirect(url_for("historias.cirugia_detalle", id=id))


# ---------------------------------------------------------------------------
# Exámenes de laboratorio
# ---------------------------------------------------------------------------


@bp.route("/mascota/<int:mascota_id>/examen/nuevo", methods=["GET", "POST"])
@login_required
@clinico_required
def examen_nuevo(mascota_id: int):
    mascota = db.session.get(Mascota, mascota_id)
    if not mascota:
        flash("La mascota no existe.", "danger")
        return redirect(url_for("historias.lista"))

    form = ExamenLaboratorioForm(mascota_id=str(mascota_id))
    if form.validate_on_submit():
        examen = ExamenLaboratorio(
            mascota_id=mascota.id,
            solicitado_por_id=current_user.id,
            tipo_examen=form.tipo_examen.data,
            fecha_toma=datetime.combine(form.fecha_toma.data, datetime.min.time(), tzinfo=ZONA_BOGOTA),
            laboratorio_externo=form.laboratorio_externo.data,
        )
        try:
            db.session.add(examen)
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al solicitar examen")
            flash("No se pudo registrar el examen.", "danger")
        else:
            flash("Examen solicitado.", "success")
            return redirect(url_for("historias.examen_detalle", id=examen.id))
    return render_template("historias/form_examen.html", form=form, mascota=mascota)


@bp.route("/examen/<int:id>", methods=["GET"])
@login_required
@clinico_required
def examen_detalle(id: int):
    examen = db.session.execute(
        select(ExamenLaboratorio).filter_by(id=id).options(selectinload(ExamenLaboratorio.mascota))
    ).scalar_one_or_none()
    if not examen:
        flash("El examen no existe.", "danger")
        return redirect(url_for("historias.lista"))
    return render_template("historias/examen_detalle.html", examen=examen, form_resultado=ResultadoExamenForm(estado=examen.estado, interpretacion=examen.interpretacion or ""))


@bp.route("/examen/<int:id>/resultado", methods=["POST"])
@login_required
@clinico_required
def examen_resultado(id: int):
    examen = db.session.get(ExamenLaboratorio, id)
    if not examen:
        flash("El examen no existe.", "danger")
        return redirect(url_for("historias.lista"))
    form = ResultadoExamenForm()
    if form.validate_on_submit():
        nombre_archivo = examen.archivo_resultado
        if form.archivo_resultado.data and getattr(form.archivo_resultado.data, "filename", ""):
            try:
                nombre_archivo = guardar_documento(form.archivo_resultado.data, "examenes")
            except ValueError as exc:
                form.archivo_resultado.errors.append(str(exc))

        if not form.archivo_resultado.errors:
            anterior = examen.archivo_resultado
            examen.interpretacion = form.interpretacion.data
            examen.estado = form.estado.data
            examen.archivo_resultado = nombre_archivo
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Error al guardar resultado del examen %d", id)
                flash("No se pudo guardar el resultado.", "danger")
            else:
                if nombre_archivo != anterior and anterior:
                    eliminar_documento("examenes", anterior)
                flash("Resultado guardado.", "success")
    return redirect(url_for("historias.examen_detalle", id=id))
