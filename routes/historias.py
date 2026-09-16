"""Rutas y controladores para Historias Clínicas, Consultas SOAP, Vacunas y Desparasitaciones."""

import json
from datetime import datetime
from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for
from decorators import clinico_required
from pdf_generator import generar_pdf_consulta, generar_pdf_receta
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
    RemisionInternaForm,
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
    RemisionInterna,
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


POR_PAGINA = 9


@bp.route("/", methods=["GET"])
@login_required
@clinico_required
def lista():
    pagina = request.args.get("page", 1, type=int)
    q = (request.args.get("q") or "").strip()
    normalizado = normalizar_texto(q)

    consulta = (
        select(Mascota)
        .filter(Mascota.activo.is_(True))
        .options(
            selectinload(Mascota.tutor),
            selectinload(Mascota.raza),
            selectinload(Mascota.consultas),
            selectinload(Mascota.vacunas),
            selectinload(Mascota.registros_peso),
        )
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

    paginacion = db.paginate(consulta, page=pagina, per_page=POR_PAGINA, error_out=False)
    mascotas = paginacion.items
    return render_template("historias/lista.html", mascotas=mascotas, pagina=paginacion, q=q)


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
    remisiones = db.session.execute(
        select(RemisionInterna)
        .filter_by(mascota_id=mascota.id)
        .options(selectinload(RemisionInterna.veterinario))
        .order_by(RemisionInterna.fecha_remision.desc())
    ).scalars().all()

    # Pre-cargar formulario de nueva remisión con antecedentes existentes del paciente
    form_remision = RemisionInternaForm()
    if request.method == "GET":
        # Antecedentes de enfermedades y alergias
        enfermedades = mascota.condiciones_preexistentes or ""
        if mascota.alergias:
            enfermedades = f"{enfermedades} | Alergias: {mascota.alergias}".strip(" |")
        form_remision.antecedentes_enfermedades.data = enfermedades

        # Antecedentes de cirugías
        if cirugias:
            form_remision.antecedentes_cirugias.data = ", ".join(
                [f"{c.tipo_procedimiento} ({c.fecha.strftime('%d/%m/%Y') if c.fecha else 'Sin fecha'})" for c in cirugias]
            )

        # Última vacuna
        if mascota.vacunas:
            ult_vac = mascota.vacunas[0]
            form_remision.vacunacion_ultima_fecha.data = ult_vac.fecha_aplicacion
            form_remision.vacunacion_al_dia.data = (ult_vac.estado_vencimiento == "al_dia")

        # Últimas desparasitaciones interna y externa
        if mascota.desparasitaciones:
            for d in mascota.desparasitaciones:
                if d.tipo in ("interna", "mixta") and not form_remision.desparasitacion_interna_producto.data:
                    form_remision.desparasitacion_interna_producto.data = d.producto
                    form_remision.desparasitacion_interna_fecha.data = d.fecha_aplicacion
                if d.tipo in ("externa", "mixta") and not form_remision.desparasitacion_externa_producto.data:
                    form_remision.desparasitacion_externa_producto.data = d.producto
                    form_remision.desparasitacion_externa_fecha.data = d.fecha_aplicacion

    datos_peso = [
        {
            "fecha": r.fecha.strftime("%Y-%m-%d") if hasattr(r.fecha, "strftime") else str(r.fecha),
            "peso_kg": float(r.peso_kg),
        }
        for r in mascota.registros_peso
    ]

    tab_activa = request.args.get("tab", "soap")

    return render_template(
        "historias/ficha_medica.html",
        mascota=mascota,
        hospitalizaciones=hospitalizaciones,
        cirugias=cirugias,
        examenes=examenes,
        remisiones=remisiones,
        form_remision=form_remision,
        datos_peso=datos_peso,
        tab_activa=tab_activa,
    )


SISTEMAS_MEDICOS_CATALOGO = [
    {
        "id": "musculo_esqueletico",
        "nombre": "Músculo esquelético",
        "icono": "bi-activity",
        "badge_color": "primary",
        "descripcion": "Huesos, articulaciones, tono muscular, marcha y simetría",
        "sugerencias": ["Sin dolor a la palpación", "Tono muscular adecuado", "Claudicación en extremidad", "Dolor articular leve", "Crepitación articular"],
    },
    {
        "id": "tegumentario",
        "nombre": "Tegumentario",
        "icono": "bi-shield-shaded",
        "badge_color": "success",
        "descripcion": "Piel, pelaje, uñas, ectoparásitos, prurito, pioderma y alopecias",
        "sugerencias": [
            "Piel íntegra y pelaje brillante sin ectoparásitos",
            "Sin lesiones alopécicas, eritema ni prurito",
            "Prurito moderado / Lesiones por rascado",
            "Eritema y descamación cutánea",
            "Presencia de pulgas / garrapatas / ectoparásitos",
            "Pioderma superficial / Alopecia focal",
        ],
    },
    {
        "id": "gastrointestinal",
        "nombre": "Gastrointestinal",
        "icono": "bi-egg-fried",
        "badge_color": "warning",
        "descripcion": "Boca, dientes, deglución, palpación abdominal y evacuación",
        "sugerencias": ["Palpación abdominal no dolorosa", "Abdomen blando y depresible", "Sensibilidad epigástrica", "Gases / Timpanismo", "Tártaro dental moderado"],
    },
    {
        "id": "ganglio_linfatico",
        "nombre": "Ganglios linfáticos",
        "icono": "bi-shield-check",
        "badge_color": "info",
        "descripcion": "Mandibulares, preescapulares, axilares, inguinales y poplíteos",
        "sugerencias": ["De tamaño, forma y consistencia normal", "No reactivos a la palpación", "Linfadenomegalia submandibular", "Linfadenomegalia poplítea", "Sensibles a la palpación"],
    },
    {
        "id": "organos_sentidos",
        "nombre": "Órganos de los sentidos",
        "icono": "bi-eye",
        "badge_color": "purple",
        "descripcion": "Ojos (córnea, reflejos), oídos (conductos, pabellón) y olfato",
        "sugerencias": ["Ojos claros, reflejos pupilares normales", "Conductos auditivos limpios sin secreción", "Eritema en pabellón auricular", "Secreción ocular serosa", "Epífora / Blefarospasmo"],
    },
    {
        "id": "respiratorio",
        "nombre": "Sistema Respiratorio",
        "icono": "bi-lungs",
        "badge_color": "cyan",
        "descripcion": "Auscultación pulmonar, tráquea, patrón respiratorio y ritmo",
        "sugerencias": ["Campos pulmonares limpios sin ruidos agregados", "Patrón costo-abdominal normal", "Estertores / Roncus bilaterales", "Reflejo traqueal positivo / Tos", "Sibilancias espiratorias"],
    },
    {
        "id": "cardiaco",
        "nombre": "Cardiovascular / Cardíaco",
        "icono": "bi-heart-pulse",
        "badge_color": "danger",
        "descripcion": "Auscultación cardíaca, soplos, arritmias, pulso femoral y sincronía",
        "sugerencias": ["Tonos cardíacos rítmicos sin soplos", "Pulsos femorales fuertes y simétricos", "Soplo sistólico grado II/VI", "Arritmia sinusal respiratoria", "Pulso débil / Irregular"],
    },
    {
        "id": "nervioso",
        "nombre": "Sistema Nervioso",
        "icono": "bi-lightning-charge",
        "badge_color": "amber",
        "descripcion": "Estado mental, marcha, propiocepción, reflejos espinales y pares craneales",
        "sugerencias": ["Alerta y responsivo al entorno", "Propiocepción y reflejos espinales normales", "Ataxia / Descoordinación leve", "Reflejo de amenaza disminuido", "Letárgico / Deprimido"],
    },
    {
        "id": "urinario",
        "nombre": "Urinario / Renal",
        "icono": "bi-droplet-half",
        "badge_color": "blue",
        "descripcion": "Palpación de riñones y vejiga, micción y aspecto de la orina",
        "sugerencias": ["Vejiga normodistendida no dolorosa", "Riñones simétricos y sin dolor", "Dolor a la palpación renal", "Vejiga pletórica / Tensa", "Hematuria / Disuria referida"],
    },
    {
        "id": "reproductivo",
        "nombre": "Reproductivo",
        "icono": "bi-gender-ambiguous",
        "badge_color": "pink",
        "descripcion": "Genitales externos, mamas, testículos, secreciones y estado reproductivo",
        "sugerencias": ["Genitales externos sin alteraciones ni secreciones", "Glándulas mamarias sin nódulos", "Testículos descendidos simétricos", "Castrado / Esterilizada previamente", "Secreción prepucial / vulvar leve"],
    },
]


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
        # Validar si el examen de sistemas viene en formato JSON estructurado
        examen_raw = form.examen_sistemas.data.strip() if form.examen_sistemas.data else ""
        if examen_raw.startswith("{"):
            try:
                s_data = json.loads(examen_raw)
                s_dict = s_data.get("sistemas", {}) if isinstance(s_data, dict) else {}
                faltantes = []
                for sist in SISTEMAS_MEDICOS_CATALOGO:
                    item = s_dict.get(sist["id"])
                    if not item or item.get("estado") not in ("normal", "anormal"):
                        faltantes.append(sist["nombre"])
                if faltantes:
                    flash(
                        f"Debes completar la evaluación de todos los sistemas. Faltan {len(faltantes)}: {', '.join(faltantes)}.",
                        "danger",
                    )
                    return render_template(
                        "historias/form_consulta.html",
                        form=form,
                        mascota=mascota,
                        catalogo_sistemas=SISTEMAS_MEDICOS_CATALOGO,
                    )
            except json.JSONDecodeError:
                pass

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

    return render_template(
        "historias/form_consulta.html",
        form=form,
        mascota=mascota,
        catalogo_sistemas=SISTEMAS_MEDICOS_CATALOGO,
    )


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

    return render_template("historias/consulta_detalle.html", consulta=consulta, form_enmienda=EnmiendaConsultaForm())


@bp.route("/consulta/<int:id>/pdf", methods=["GET"])
def consulta_pdf(id: int):
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

    pdf_buffer = generar_pdf_consulta(consulta, db.session)
    nombre_archivo = f"Consulta_{consulta.mascota.nombre if consulta.mascota else 'Paciente'}_{consulta.id:04d}.pdf"
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=nombre_archivo,
    )


@bp.route("/consulta/<int:id>/receta/pdf", methods=["GET"])
def receta_pdf(id: int):
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

    pdf_buffer = generar_pdf_receta(consulta, db.session)
    nombre_archivo = f"Formula_Medica_{consulta.mascota.nombre if consulta.mascota else 'Paciente'}_{consulta.id:04d}.pdf"
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=nombre_archivo,
    )


@bp.route("/consulta/<int:id>/documento", methods=["GET"])
def consulta_documento_publico(id: int):
    """Vista web oficial del documento para compartir con el tutor por WhatsApp o imprimir."""
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
        flash("El documento solicitado no está disponible.", "danger")
        return redirect(url_for("auth.login"))

    clinica_datos = ConfiguracionSistema.datos_clinica()
    return render_template("historias/documento_consulta.html", consulta=consulta, clinica=clinica_datos)


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
# Exámenes, Radiografías, Ecografías y Ayudas Diagnósticas
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
    
    # Preseleccionar categoría si viene por URL (ej: ?categoria=radiografia)
    cat_param = request.args.get("categoria", "")
    if request.method == "GET" and cat_param in ("radiografia", "laboratorio", "ecografia", "cardiologia", "otro"):
        form.categoria.data = cat_param

    if form.validate_on_submit():
        nombre_archivo = None
        if form.archivo_resultado.data and getattr(form.archivo_resultado.data, "filename", ""):
            try:
                nombre_archivo = guardar_documento(form.archivo_resultado.data, "examenes")
            except ValueError as exc:
                form.archivo_resultado.errors.append(str(exc))

        if not form.archivo_resultado.errors:
            estado_final = form.estado.data
            # Si se adjuntó archivo o comentarios y estaba en solicitado, marcar como con resultado
            if (nombre_archivo or (form.interpretacion.data and form.interpretacion.data.strip())) and estado_final == "solicitado":
                estado_final = "con_resultado"

            examen = ExamenLaboratorio(
                mascota_id=mascota.id,
                solicitado_por_id=current_user.id,
                categoria=form.categoria.data or "laboratorio",
                tipo_examen=form.tipo_examen.data,
                fecha_toma=datetime.combine(form.fecha_toma.data, datetime.min.time(), tzinfo=ZONA_BOGOTA),
                laboratorio_externo=form.laboratorio_externo.data or None,
                archivo_resultado=nombre_archivo,
                interpretacion=form.interpretacion.data or None,
                estado=estado_final,
            )
            try:
                db.session.add(examen)
                db.session.commit()
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Error al registrar examen")
                flash("No se pudo registrar el examen.", "danger")
            else:
                flash(f"{examen.categoria_etiqueta} guardada exitosamente.", "success")
                return redirect(url_for("historias.ficha_medica", mascota_id=mascota.id))

    return render_template("historias/form_examen.html", form=form, mascota=mascota)


@bp.route("/examen/<int:id>", methods=["GET"])
@login_required
@clinico_required
def examen_detalle(id: int):
    examen = db.session.execute(
        select(ExamenLaboratorio)
        .filter_by(id=id)
        .options(
            selectinload(ExamenLaboratorio.mascota).selectinload(Mascota.raza),
            selectinload(ExamenLaboratorio.mascota).selectinload(Mascota.tutor),
            selectinload(ExamenLaboratorio.solicitado_por),
        )
    ).scalar_one_or_none()
    if not examen:
        flash("El examen no existe.", "danger")
        return redirect(url_for("historias.lista"))

    form_resultado = ResultadoExamenForm(
        categoria=examen.categoria,
        tipo_examen=examen.tipo_examen,
        laboratorio_externo=examen.laboratorio_externo or "",
        estado=examen.estado,
        interpretacion=examen.interpretacion or "",
    )
    return render_template("historias/examen_detalle.html", examen=examen, form_resultado=form_resultado)


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
            if form.categoria.data:
                examen.categoria = form.categoria.data
            if form.tipo_examen.data:
                examen.tipo_examen = form.tipo_examen.data
            if form.laboratorio_externo.data is not None:
                examen.laboratorio_externo = form.laboratorio_externo.data or None
            examen.interpretacion = form.interpretacion.data or None
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
                flash("Resultado y comentarios actualizados exitosamente.", "success")

    return redirect(url_for("historias.examen_detalle", id=id))


@bp.route("/examen/<int:id>/eliminar-archivo", methods=["POST"])
@login_required
@clinico_required
def examen_eliminar_archivo(id: int):
    examen = db.session.get(ExamenLaboratorio, id)
    if not examen:
        flash("El examen no existe.", "danger")
        return redirect(url_for("historias.lista"))

    if examen.archivo_resultado:
        eliminar_documento("examenes", examen.archivo_resultado)
        examen.archivo_resultado = None
        try:
            db.session.commit()
            flash("Archivo adjunto eliminado.", "info")
        except Exception:
            db.session.rollback()
            flash("Error al actualizar el examen.", "danger")

    return redirect(url_for("historias.examen_detalle", id=id))


@bp.route("/examen/<int:id>/eliminar", methods=["POST"])
@login_required
@clinico_required
def examen_eliminar(id: int):
    examen = db.session.get(ExamenLaboratorio, id)
    if not examen:
        flash("El examen no existe.", "danger")
        return redirect(url_for("historias.lista"))

    mascota_id = examen.mascota_id
    if examen.archivo_resultado:
        eliminar_documento("examenes", examen.archivo_resultado)

    try:
        db.session.delete(examen)
        db.session.commit()
        flash("Registro de examen eliminado.", "info")
    except Exception:
        db.session.rollback()
        flash("No se pudo eliminar el examen.", "danger")

    return redirect(url_for("historias.ficha_medica", mascota_id=mascota_id))


# ---------------------------------------------------------------------------
# Remisiones Clínicas Internas
# ---------------------------------------------------------------------------


@bp.route("/remisiones/nueva/<int:mascota_id>", methods=["POST"])
@login_required
@clinico_required
def remision_nueva(mascota_id: int):
    mascota = db.session.get(Mascota, mascota_id)
    if not mascota:
        flash("La mascota no existe.", "danger")
        return redirect(url_for("historias.lista"))

    form = RemisionInternaForm()
    if form.validate_on_submit():
        remision = RemisionInterna(
            mascota_id=mascota.id,
            tutor_id=mascota.tutor_id,
            veterinario_id=current_user.id,
            creado_por_id=current_user.id,
            fecha_remision=obtener_hora_bogota(),
            dieta_marca_tipo=(form.dieta_marca_tipo.data or "").strip() or None,
            antecedentes_cirugias=(form.antecedentes_cirugias.data or "").strip() or None,
            antecedentes_enfermedades=(form.antecedentes_enfermedades.data or "").strip() or None,
            desparasitacion_interna_producto=(form.desparasitacion_interna_producto.data or "").strip() or None,
            desparasitacion_interna_fecha=form.desparasitacion_interna_fecha.data,
            desparasitacion_externa_producto=(form.desparasitacion_externa_producto.data or "").strip() or None,
            desparasitacion_externa_fecha=form.desparasitacion_externa_fecha.data,
            vacunacion_al_dia=bool(form.vacunacion_al_dia.data),
            vacunacion_ultima_fecha=form.vacunacion_ultima_fecha.data,
            especialidad_destino=form.especialidad_destino.data.strip(),
            centro_medico_destino=(form.centro_medico_destino.data or "").strip() or None,
            motivo_remision=form.motivo_remision.data.strip(),
            observaciones_clinicas=(form.observaciones_clinicas.data or "").strip() or None,
            fecha_registro=obtener_hora_bogota(),
        )
        db.session.add(remision)
        db.session.commit()
        flash(f"Remisión para {remision.especialidad_destino} guardada exitosamente en el expediente.", "success")
        return redirect(url_for("historias.ficha_medica", mascota_id=mascota.id, tab="remisiones"))

    for campo, errores in form.errors.items():
        for error in errores:
            flash(f"Error en {campo}: {error}", "danger")
    return redirect(url_for("historias.ficha_medica", mascota_id=mascota.id, tab="remisiones"))


@bp.route("/remisiones/<int:id>/json", methods=["GET"])
@login_required
@clinico_required
def remision_detalle_json(id: int):
    remision = db.session.execute(
        select(RemisionInterna).filter_by(id=id).options(
            selectinload(RemisionInterna.veterinario),
            selectinload(RemisionInterna.mascota),
            selectinload(RemisionInterna.tutor),
        )
    ).scalar_one_or_none()

    if not remision:
        return {"ok": False, "error": "Remisión no encontrada."}, 404

    return {"ok": True, "remision": remision.to_dict()}

