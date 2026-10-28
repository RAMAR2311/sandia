import io
import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import pandas as pd
from flask import Blueprint, Response, abort, current_app, flash, redirect, render_template, request, send_file, url_for
from decorators import admin_required, clinico_required
from pdf_generator import (
    generar_pdf_carnet_vacunacion,
    generar_pdf_consulta,
    generar_pdf_control,
    generar_pdf_expediente_completo,
    generar_pdf_receta,
    generar_pdf_remision,
)
from flask_login import current_user, login_required
from sqlalchemy import case, desc, func, or_, select
from sqlalchemy.orm import selectinload

from forms import (
    AltaHospitalizacionForm,
    CirugiaForm,
    ConsultaMedicaForm,
    ControlMedicoForm,
    DesparasitacionMascotaForm,
    EnmiendaConsultaForm,
    EvolucionHospitalariaForm,
    ExamenLaboratorioForm,
    HospitalizacionForm,
    ImportarExcelForm,
    NotasPostquirurgicasForm,
    ResultadoExamenForm,
    VacunaMascotaForm,
    RemisionInternaForm,
    SoloCsrfForm,
)
from models import (
    CATEGORIAS_NOTA_CLINICA,
    CertificadoSaludAnimal,
    Cirugia,
    ConfiguracionSistema,
    ConsentimientoEmitido,
    ConsultaMedica,
    ControlMedico,
    DesparasitacionMascota,
    EnmiendaConsulta,
    EvolucionHospitalaria,
    ExamenLaboratorio,
    Hospitalizacion,
    LoteImportacion,
    Mascota,
    NotaClinica,
    Raza,
    RegistroPeso,
    RemisionInterna,
    Tutor,
    Usuario,
    VacunaMascota,
    db,
)
from utils import (
    ZONA_BOGOTA,
    eliminar_documento,
    generar_archivo_ics,
    generar_enlace_google_calendar,
    guardar_documento,
    hoy_bogota,
    leer_archivo_tabular,
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
    orden = request.args.get("orden", "recientes").strip()
    vista = request.args.get("vista", "pacientes").strip()  # 'pacientes' o 'atenciones'
    normalizado = normalizar_texto(q)

    # Subconsultas para obtener la fecha de última actividad médica (Consulta SOAP o Control Médico)
    subq_consulta = (
        select(ConsultaMedica.mascota_id, func.max(ConsultaMedica.fecha_hora).label("max_c"))
        .group_by(ConsultaMedica.mascota_id)
        .subquery()
    )
    subq_control = (
        select(ControlMedico.mascota_id, func.max(ControlMedico.fecha_hora).label("max_ctl"))
        .group_by(ControlMedico.mascota_id)
        .subquery()
    )

    ultima_fecha = case(
        (subq_control.c.max_ctl.is_not(None) & subq_consulta.c.max_c.is_not(None),
         case((subq_control.c.max_ctl > subq_consulta.c.max_c, subq_control.c.max_ctl), else_=subq_consulta.c.max_c)),
        (subq_control.c.max_ctl.is_not(None), subq_control.c.max_ctl),
        (subq_consulta.c.max_c.is_not(None), subq_consulta.c.max_c),
        else_=Mascota.fecha_registro
    )

    consulta = (
        select(Mascota)
        .filter(Mascota.activo.is_(True))
        .outerjoin(subq_consulta, Mascota.id == subq_consulta.c.mascota_id)
        .outerjoin(subq_control, Mascota.id == subq_control.c.mascota_id)
        .options(
            selectinload(Mascota.tutor),
            selectinload(Mascota.raza),
            selectinload(Mascota.consultas).selectinload(ConsultaMedica.veterinario),
            selectinload(Mascota.controles).selectinload(ControlMedico.veterinario),
            selectinload(Mascota.vacunas),
            selectinload(Mascota.registros_peso),
        )
    )

    if orden == "alfabetico":
        consulta = consulta.order_by(Mascota.nombre.asc())
    else:
        consulta = consulta.order_by(desc(ultima_fecha), desc(Mascota.id))

    if normalizado:
        subq_c_match = select(ConsultaMedica.mascota_id).where(
            or_(
                ConsultaMedica.motivo_consulta.ilike(f"%{normalizado}%"),
                ConsultaMedica.diagnostico.ilike(f"%{normalizado}%"),
            )
        )
        subq_ctl_match = select(ControlMedico.mascota_id).where(
            or_(
                ControlMedico.motivo.ilike(f"%{normalizado}%"),
                ControlMedico.diagnostico.ilike(f"%{normalizado}%"),
            )
        )
        consulta = consulta.outerjoin(Tutor, Mascota.tutor_id == Tutor.id).filter(
            or_(
                Mascota.nombre_busqueda.ilike(f"%{normalizado}%"),
                Tutor.nombre_busqueda.ilike(f"%{normalizado}%"),
                Tutor.numero_documento.ilike(f"%{normalizado}%"),
                Mascota.microchip.ilike(f"%{normalizado}%"),
                Mascota.id.in_(subq_c_match),
                Mascota.id.in_(subq_ctl_match),
            )
        )

    paginacion = db.paginate(consulta, page=pagina, per_page=POR_PAGINA, error_out=False)
    mascotas = paginacion.items

    # Totales globales reales para los KPIs
    total_pacientes = db.session.execute(select(func.count(Mascota.id)).filter(Mascota.activo.is_(True))).scalar() or 0
    total_consultas = db.session.execute(select(func.count(ConsultaMedica.id))).scalar() or 0
    total_controles = db.session.execute(select(func.count(ControlMedico.id))).scalar() or 0
    kpis = {
        "total_pacientes": total_pacientes,
        "total_consultas": total_consultas,
        "total_controles": total_controles,
        "total_historias": total_consultas + total_controles,
    }

    # Atenciones clínicas recientes (Consultas SOAP y Controles) unificadas y ordenadas por fecha reciente
    ultimas_consultas = db.session.execute(
        select(ConsultaMedica)
        .options(
            selectinload(ConsultaMedica.mascota),
            selectinload(ConsultaMedica.tutor),
            selectinload(ConsultaMedica.veterinario)
        )
        .order_by(ConsultaMedica.fecha_hora.desc())
        .limit(25)
    ).scalars().all()

    ultimos_controles = db.session.execute(
        select(ControlMedico)
        .options(
            selectinload(ControlMedico.mascota),
            selectinload(ControlMedico.tutor),
            selectinload(ControlMedico.veterinario)
        )
        .order_by(ControlMedico.fecha_hora.desc())
        .limit(25)
    ).scalars().all()

    atenciones_recientes = []
    for c in ultimas_consultas:
        atenciones_recientes.append({
            "id": c.id,
            "tipo": "soap",
            "tipo_etiqueta": "Consulta SOAP",
            "badge_color": "danger",
            "icono": "bi-journal-medical",
            "fecha": c.fecha_hora,
            "mascota": c.mascota,
            "tutor": c.tutor,
            "veterinario": c.veterinario,
            "motivo": c.motivo_consulta,
            "diagnostico": c.diagnostico,
            "peso_kg": c.peso_kg,
            "temperatura_c": c.temperatura_c,
            "url_detalle": url_for("historias.consulta_detalle", id=c.id),
            "url_editar": url_for("historias.consulta_editar", id=c.id),
            "url_pdf": url_for("historias.consulta_pdf", id=c.id),
            "url_whatsapp": getattr(c, "enlace_whatsapp", None),
        })

    for ctrl in ultimos_controles:
        atenciones_recientes.append({
            "id": ctrl.id,
            "tipo": "control",
            "tipo_etiqueta": "Control Clínico",
            "badge_color": "info",
            "icono": "bi-clipboard2-check",
            "fecha": ctrl.fecha_hora,
            "mascota": ctrl.mascota,
            "tutor": ctrl.tutor,
            "veterinario": ctrl.veterinario,
            "motivo": ctrl.motivo or "Revisión y evolución",
            "diagnostico": ctrl.diagnostico or ctrl.avances,
            "peso_kg": ctrl.peso_kg,
            "temperatura_c": ctrl.temperatura_c,
            "url_detalle": url_for("historias.ficha_medica", mascota_id=ctrl.mascota_id, tab="controles"),
            "url_editar": url_for("historias.control_editar", id=ctrl.id),
            "url_pdf": url_for("historias.control_pdf", id=ctrl.id),
            "url_whatsapp": getattr(ctrl, "enlace_whatsapp", None),
        })

    atenciones_recientes.sort(key=lambda x: _normalizar_para_orden(x["fecha"]), reverse=True)
    atenciones_recientes = atenciones_recientes[:30]

    return render_template(
        "historias/lista.html",
        mascotas=mascotas,
        pagina=paginacion,
        q=q,
        orden=orden,
        vista=vista,
        kpis=kpis,
        atenciones_recientes=atenciones_recientes,
    )


def _normalizar_para_orden(dt):
    if dt is None:
        return datetime.min.replace(tzinfo=ZONA_BOGOTA)
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=ZONA_BOGOTA)
        return dt
    if isinstance(dt, date):
        return datetime.combine(dt, datetime.min.time()).replace(tzinfo=ZONA_BOGOTA)
    return datetime.min.replace(tzinfo=ZONA_BOGOTA)


def _construir_eventos_generales(mascota, hospitalizaciones, cirugias, examenes, remisiones):
    eventos = []

    # 1. Consultas SOAP
    for c in getattr(mascota, "consultas", []):
        eventos.append({
            "tipo": "soap",
            "categoria": "Consulta SOAP",
            "badge_color": "danger",
            "icono": "bi-journal-medical",
            "fecha": c.fecha_hora,
            "titulo": f"Consulta Médica: {c.motivo_consulta}",
            "descripcion": c.diagnostico or c.plan_tratamiento or "",
            "profesional": f"Dr/a. {c.veterinario.nombre}" if getattr(c, "veterinario", None) else "",
            "objeto": c,
            "url_detalle": url_for("historias.consulta_detalle", id=c.id),
            "url_editar": url_for("historias.consulta_editar", id=c.id),
            "url_whatsapp": getattr(c, "enlace_whatsapp", None),
            "url_pdf": url_for("historias.consulta_pdf", id=c.id),
            "tab_destino": "soap",
        })

    # 2. Controles Médicos
    for ctrl in getattr(mascota, "controles", []):
        eventos.append({
            "tipo": "control",
            "categoria": "Control Clínico",
            "badge_color": "info",
            "icono": "bi-clipboard2-check",
            "fecha": ctrl.fecha_hora,
            "titulo": f"Control Médico: {ctrl.motivo or 'Revisión y Evolución'}",
            "descripcion": ctrl.avances or ctrl.plan_terapeutico or "",
            "profesional": f"Dr/a. {ctrl.veterinario.nombre}" if getattr(ctrl, "veterinario", None) else "",
            "objeto": ctrl,
            "url_detalle": None,
            "url_editar": url_for("historias.control_editar", id=ctrl.id),
            "url_whatsapp": getattr(ctrl, "enlace_whatsapp", None),
            "url_pdf": url_for("historias.control_pdf", id=ctrl.id),
            "tab_destino": "controles",
        })

    # 3. Exámenes / Ayudas Diagnósticas & Rx
    for e in examenes:
        cat_nombre = e.categoria.capitalize() if getattr(e, "categoria", None) else "Laboratorio"
        url_archivo = url_for("static", filename=f"uploads/examenes/{e.archivo_resultado}") if e.archivo_resultado else None
        eventos.append({
            "tipo": "examen",
            "categoria": f"Ayuda Diagnóstica ({cat_nombre})",
            "badge_color": "primary",
            "icono": "bi-clipboard2-pulse",
            "fecha": e.fecha_toma,
            "titulo": f"{cat_nombre}: {e.tipo_examen or 'Examen'}",
            "descripcion": e.interpretacion or (f"Laboratorio: {e.laboratorio_externo}" if getattr(e, "laboratorio_externo", None) else ""),
            "profesional": f"Dr/a. {e.solicitado_por.nombre}" if getattr(e, "solicitado_por", None) else "",
            "objeto": e,
            "url_detalle": url_for("historias.examen_detalle", id=e.id),
            "url_editar": url_for("historias.examen_detalle", id=e.id),
            "url_pdf": url_archivo if (e.archivo_resultado and e.es_pdf) else None,
            "url_descargar": url_archivo if e.archivo_resultado else None,
            "tab_destino": "examenes",
        })

    # 4. Vacunas
    for v in getattr(mascota, "vacunas", []):
        eventos.append({
            "tipo": "vacuna",
            "categoria": "Vacunación",
            "badge_color": "warning",
            "icono": "bi-shield-check",
            "fecha": v.fecha_aplicacion,
            "titulo": f"Vacunación: {v.nombre_vacuna}",
            "descripcion": f"Lote: {v.lote or 'N/A'}" + (f" • Próx. Dosis: {v.fecha_proxima.strftime('%d/%m/%Y')}" if getattr(v, "fecha_proxima", None) else ""),
            "profesional": f"Dr/a. {v.veterinario.nombre}" if getattr(v, "veterinario", None) else "",
            "objeto": v,
            "url_editar": None,
            "url_pdf": url_for("historias.carnet_vacunacion_pdf", mascota_id=mascota.id),
            "url_whatsapp": getattr(v, "enlace_whatsapp", None),
            "tab_destino": "vacunas",
        })

    # 5. Desparasitaciones
    for d in getattr(mascota, "desparasitaciones", []):
        eventos.append({
            "tipo": "desparasitacion",
            "categoria": f"Desparasitación {d.tipo.capitalize() if getattr(d, 'tipo', None) else ''}".strip(),
            "badge_color": "success",
            "icono": "bi-capsule",
            "fecha": d.fecha_aplicacion,
            "titulo": f"Desparasitación: {d.producto}",
            "descripcion": f"Dosis: {d.dosis or 'N/A'}" + (f" • Próxima: {d.fecha_proxima.strftime('%d/%m/%Y')}" if getattr(d, "fecha_proxima", None) else ""),
            "profesional": f"Dr/a. {d.veterinario.nombre}" if getattr(d, "veterinario", None) else "",
            "objeto": d,
            "url_editar": None,
            "tab_destino": "desparasitaciones",
        })

    # 6. Hospitalizaciones
    for h in hospitalizaciones:
        eventos.append({
            "tipo": "hospitalizacion",
            "categoria": "Hospitalización",
            "badge_color": "secondary",
            "icono": "bi-hospital",
            "fecha": h.fecha_ingreso,
            "titulo": f"Hospitalización: {getattr(h, 'motivo', None) or getattr(h, 'motivo_ingreso', 'Ingreso Clínico')}",
            "descripcion": f"Estado: {h.estado.capitalize()}" + (f" • Jaula: {h.jaula}" if getattr(h, "jaula", None) else ""),
            "profesional": f"Dr/a. {h.veterinario_responsable.nombre}" if getattr(h, "veterinario_responsable", None) else "",
            "objeto": h,
            "url_detalle": url_for("historias.hospitalizacion_detalle", id=h.id),
            "tab_destino": "avanzada",
        })

    # 7. Cirugías
    for cir in cirugias:
        eventos.append({
            "tipo": "cirugia",
            "categoria": "Cirugía",
            "badge_color": "danger",
            "icono": "bi-scissors",
            "fecha": cir.fecha,
            "titulo": f"Cirugía: {cir.tipo_procedimiento}",
            "descripcion": f"Estado: {cir.estado.capitalize()}" + (f" • Anestesia: {cir.tipo_anestesia}" if getattr(cir, "tipo_anestesia", None) else ""),
            "profesional": f"Dr/a. {cir.cirujano.nombre}" if getattr(cir, "cirujano", None) else "",
            "objeto": cir,
            "url_detalle": url_for("historias.cirugia_detalle", id=cir.id),
            "tab_destino": "avanzada",
        })

    # 8. Consentimientos
    for cs in getattr(mascota, "consentimientos", []):
        eventos.append({
            "tipo": "consentimiento",
            "categoria": "Consentimiento",
            "badge_color": "dark",
            "icono": "bi-file-earmark-medical",
            "fecha": cs.creado_en,
            "titulo": f"Consentimiento: {cs.plantilla.titulo if getattr(cs, 'plantilla', None) else 'Documento Clínico'}",
            "descripcion": f"Estado: {cs.estado_etiqueta} • Consecutivo #{cs.id}",
            "profesional": f"Dr/a. {cs.veterinario.nombre}" if getattr(cs, "veterinario", None) else "",
            "objeto": cs,
            "url_detalle": cs.url_documento() if hasattr(cs, "url_documento") else url_for("consentimientos.documento_publico", id=cs.id),
            "url_pdf": url_for("consentimientos.consentimiento_pdf", id=cs.id),
            "url_whatsapp": cs.enlace_whatsapp() if hasattr(cs, "enlace_whatsapp") else None,
            "tab_destino": "consentimientos",
        })

    # 9. Certificados de Salud
    for cert in getattr(mascota, "certificados_salud", []):
        eventos.append({
            "tipo": "certificado",
            "categoria": "Certificado de Salud",
            "badge_color": "danger",
            "icono": "bi-award-fill",
            "fecha": cert.fecha_emision,
            "titulo": f"Certificado de Salud #{cert.consecutivo}",
            "descripcion": f"Finalidad: {cert.finalidad_etiqueta if hasattr(cert, 'finalidad_etiqueta') else 'General'} • Vigencia: {getattr(cert, 'dias_vigencia', 5)} días",
            "profesional": f"Dr/a. {cert.veterinario.nombre}" if getattr(cert, "veterinario", None) else "",
            "objeto": cert,
            "url_detalle": cert.url_verificacion_publica() if hasattr(cert, "url_verificacion_publica") else url_for("certificados.vista_verificacion_publica", token=cert.token_verificacion),
            "url_pdf": cert.url_pdf() if hasattr(cert, "url_pdf") else url_for("certificados.certificado_pdf", id=cert.id),
            "url_whatsapp": cert.enlace_whatsapp() if hasattr(cert, "enlace_whatsapp") else None,
            "tab_destino": "certificados",
        })

    # 10. Remisiones
    for rem in remisiones:
        centro = f" ({rem.centro_medico_destino})" if getattr(rem, "centro_medico_destino", None) else ""
        eventos.append({
            "tipo": "remision",
            "categoria": "Remisión Médica",
            "badge_color": "info",
            "icono": "bi-send-check-fill",
            "fecha": rem.fecha_remision,
            "titulo": f"Remisión: {getattr(rem, 'especialidad_destino', 'Interconsulta')}{centro}",
            "descripcion": f"Motivo: {rem.motivo_remision}" if getattr(rem, "motivo_remision", None) else "",
            "profesional": f"Dr/a. {rem.veterinario.nombre}" if getattr(rem, "veterinario", None) else "",
            "objeto": rem,
            "url_detalle": None,
            "url_pdf": url_for("historias.remision_pdf", id=rem.id),
            "url_whatsapp": getattr(rem, "enlace_whatsapp", None),
            "tab_destino": "remisiones",
        })

    # 11. Registros de peso
    for p in getattr(mascota, "registros_peso", []):
        eventos.append({
            "tipo": "peso",
            "categoria": "Control de Peso",
            "badge_color": "secondary",
            "icono": "bi-graph-up",
            "fecha": p.fecha,
            "titulo": f"Registro de Peso: {p.peso_kg} kg",
            "descripcion": f"Registrado por: {p.registrado_por.nombre if getattr(p, 'registrado_por', None) else 'Clínica'}",
            "profesional": p.registrado_por.nombre if getattr(p, "registrado_por", None) else "",
            "objeto": p,
            "tab_destino": "peso",
        })

    # 12. Notas y Novedades Clínicas
    for n in getattr(mascota, "notas_clinicas", []):
        eventos.append({
            "tipo": "nota",
            "categoria": n.categoria_etiqueta,
            "badge_color": n.badge_color,
            "icono": n.icono,
            "fecha": n.fecha,
            "titulo": f"Novedad Clínica: {n.categoria_etiqueta}",
            "descripcion": n.texto,
            "profesional": f"Registrado por: {n.autor.nombre}" if getattr(n, "autor", None) else "",
            "objeto": n,
            "tab_destino": "general",
        })

    eventos.sort(key=lambda ev: _normalizar_para_orden(ev.get("fecha")), reverse=True)
    return eventos


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
            selectinload(Mascota.controles).selectinload(ControlMedico.veterinario),
            selectinload(Mascota.controles).selectinload(ControlMedico.consulta_origen),
            selectinload(Mascota.vacunas),
            selectinload(Mascota.desparasitaciones),
            selectinload(Mascota.registros_peso),
            selectinload(Mascota.consentimientos),
            selectinload(Mascota.certificados_salud),
            selectinload(Mascota.notas_clinicas).selectinload(NotaClinica.autor),
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

    eventos_generales = _construir_eventos_generales(
        mascota=mascota,
        hospitalizaciones=hospitalizaciones,
        cirugias=cirugias,
        examenes=examenes,
        remisiones=remisiones,
    )

    tab_activa = request.args.get("tab", "general")

    return render_template(
        "historias/ficha_medica.html",
        mascota=mascota,
        hospitalizaciones=hospitalizaciones,
        cirugias=cirugias,
        examenes=examenes,
        remisiones=remisiones,
        form_remision=form_remision,
        datos_peso=datos_peso,
        eventos_generales=eventos_generales,
        tab_activa=tab_activa,
        form_csrf=SoloCsrfForm(),
    )


SISTEMAS_MEDICOS_CATALOGO = [
    {
        "id": "musculo_esqueletico",
        "nombre": "Músculo esquelético",
        "icono": "bi-activity",
        "badge_color": "primary",
        "descripcion": "Huesos, articulaciones, tono muscular, marcha y simetría",
        "sugerencias": [
            "Sin dolor a la palpación",
            "Tono muscular adecuado",
            "Claudicación en extremidad",
            "Dolor articular leve",
            "Crepitación articular",
            "Reflejo panicular positivo",
        ],
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
            "Caspas / Seborrea",
            "Lesiones circunscritas",
            "Descamación / Escamación cutánea",
            "Prurito moderado / Lesiones por rascado",
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
        "sugerencias": [
            "Palpación abdominal no dolorosa",
            "Abdomen blando y depresible",
            "Dolor a la palpación abdominal",
            "Histórico de diarreas y vómitos",
            "Sensibilidad epigástrica",
            "Gases / Timpanismo",
            "Tártaro dental moderado",
        ],
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
    mascota = db.session.execute(
        select(Mascota)
        .filter_by(id=mascota_id)
        .options(
            selectinload(Mascota.tutor),
            selectinload(Mascota.raza),
            selectinload(Mascota.vacunas),
            selectinload(Mascota.desparasitaciones),
            selectinload(Mascota.registros_peso),
        )
    ).scalar_one_or_none()
    if not mascota:
        flash("La mascota no existe.", "danger")
        return redirect(url_for("historias.lista"))

    form = ConsultaMedicaForm()
    if not form.is_submitted():
        # Prellenar peso actual si existe
        if mascota.peso_actual:
            form.peso_kg.data = mascota.peso_actual.peso_kg
        # Prellenar alimentación actual si existe
        if mascota.alimentacion:
            form.alimentacion.data = mascota.alimentacion
        # Prellenar última desparasitación
        if mascota.desparasitaciones:
            d = mascota.desparasitaciones[0]
            form.desparasitacion_producto.data = f"{d.producto} ({d.tipo.capitalize()})"
            form.desparasitacion_fecha.data = d.fecha_aplicacion
        # Prellenar última vacuna
        if mascota.vacunas:
            v = mascota.vacunas[0]
            form.vacunacion_producto.data = v.nombre_vacuna
            form.vacunacion_fecha.data = v.fecha_aplicacion

    if form.validate_on_submit():
        # Procesar examen de sistemas en formato JSON si fue provisto
        examen_raw = form.examen_sistemas.data.strip() if form.examen_sistemas.data else ""
        if examen_raw.startswith("{"):
            try:
                s_data = json.loads(examen_raw)
                s_dict = s_data.get("sistemas", {}) if isinstance(s_data, dict) else {}
                # Completar cualquier sistema no evaluado como normal para no bloquear el guardado clínico
                for sist in SISTEMAS_MEDICOS_CATALOGO:
                    if sist["id"] not in s_dict or s_dict[sist["id"]].get("estado") not in ("normal", "anormal"):
                        s_dict[sist["id"]] = {"estado": "normal", "observacion": ""}
                s_data["sistemas"] = s_dict
                form.examen_sistemas.data = json.dumps(s_data)
            except json.JSONDecodeError:
                pass

        try:
            fecha_consulta = form.fecha_hora.data if form.fecha_hora.data else obtener_hora_bogota()
            consulta = ConsultaMedica(
                mascota_id=mascota.id,
                tutor_id=mascota.tutor_id,
                veterinario_id=current_user.id,
                fecha_hora=fecha_consulta,
                motivo_consulta=form.motivo_consulta.data.strip(),
                anamnesis=form.anamnesis.data.strip() if form.anamnesis.data else None,
                alimentacion=(form.alimentacion.data or "").strip() or None,
                desparasitacion_producto=(form.desparasitacion_producto.data or "").strip() or None,
                desparasitacion_fecha=form.desparasitacion_fecha.data,
                vacunacion_producto=(form.vacunacion_producto.data or "").strip() or None,
                vacunacion_fecha=form.vacunacion_fecha.data,
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
            db.session.flush()

            # Actualizar peso de la mascota si se registró uno nuevo
            if form.peso_kg.data and (not mascota.peso_actual or form.peso_kg.data != mascota.peso_actual.peso_kg):
                mascota.peso_actual = form.peso_kg.data

            # Actualizar alimentación en el perfil si se modificó en la consulta
            if form.alimentacion.data and form.alimentacion.data.strip():
                mascota.alimentacion = form.alimentacion.data.strip()

            # Agendar próximo control si fue seleccionado
            control_creado = None
            if form.agendar_control.data and form.fecha_proximo_control.data:
                motivo_ctl = form.motivo_control.data.strip() if form.motivo_control.data else f"Control de {consulta.diagnostico}"
                control_creado = ControlMedico(
                    mascota_id=mascota.id,
                    tutor_id=mascota.tutor_id,
                    veterinario_id=current_user.id,
                    consulta_origen_id=consulta.id,
                    motivo=motivo_ctl,
                    fecha_hora=form.fecha_proximo_control.data,
                    peso_kg=form.peso_kg.data,
                    temperatura_c=form.temperatura_c.data,
                    avances=f"Programado desde consulta médica SOAP del {consulta.fecha_hora.strftime('%d/%m/%Y')}",
                    diagnostico=f"Seguimiento: {consulta.diagnostico}",
                    plan_terapeutico=consulta.plan_tratamiento,
                    medicamento=consulta.receta_medica,
                    fecha_proximo_control=form.fecha_proximo_control.data,
                    observaciones=f"Control agendado al finalizar consulta SOAP. Motivo: {motivo_ctl}",
                    creado_por_id=current_user.id,
                )
                db.session.add(control_creado)

            db.session.commit()
            if control_creado:
                flash(f"Consulta médica guardada y Próximo Control agendado para el {control_creado.fecha_proximo_control.strftime('%d/%m/%Y %I:%M %p')}.", "success")
            else:
                flash("Consulta médica (SOAP) guardada correctamente.", "success")
            return redirect(url_for("historias.consulta_detalle", id=consulta.id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al guardar consulta médica")
            flash("Ocurrió un error al guardar la consulta.", "danger")
    elif request.method == "POST":
        # Formulario enviado pero falló validación
        errores_campos = []
        for field_name, errors in form.errors.items():
            field_label = getattr(form, field_name).label.text if hasattr(getattr(form, field_name), "label") else field_name
            errores_campos.append(f"<strong>{field_label}</strong>: {', '.join(errors)}")
        if errores_campos:
            flash(f"⚠️ No se pudo guardar la consulta. Por favor revisa los siguientes campos obligatorios:<br>• " + "<br>• ".join(errores_campos), "danger")

    return render_template(
        "historias/form_consulta.html",
        form=form,
        mascota=mascota,
        catalogo_sistemas=SISTEMAS_MEDICOS_CATALOGO,
    )


@bp.route("/consulta/<int:id>/editar", methods=["GET", "POST"])
@login_required
@clinico_required
def consulta_editar(id: int):
    consulta = db.session.execute(
        select(ConsultaMedica)
        .filter_by(id=id)
        .options(
            selectinload(ConsultaMedica.mascota).selectinload(Mascota.tutor),
            selectinload(ConsultaMedica.mascota).selectinload(Mascota.raza),
            selectinload(ConsultaMedica.mascota).selectinload(Mascota.registros_peso),
            selectinload(ConsultaMedica.tutor),
            selectinload(ConsultaMedica.veterinario),
            selectinload(ConsultaMedica.controles_asociados),
        )
    ).scalar_one_or_none()
    if not consulta:
        flash("La consulta médica no existe.", "danger")
        return redirect(url_for("historias.lista"))

    mascota = consulta.mascota
    form = ConsultaMedicaForm(obj=consulta)

    if not form.is_submitted():
        if consulta.controles_asociados:
            ultimo_control = consulta.controles_asociados[0]
            form.agendar_control.data = True
            form.motivo_control.data = ultimo_control.motivo
            form.fecha_proximo_control.data = ultimo_control.fecha_proximo_control or ultimo_control.fecha_hora

    if form.validate_on_submit():
        # Procesar examen de sistemas en formato JSON al editar
        examen_raw = form.examen_sistemas.data.strip() if form.examen_sistemas.data else ""
        if examen_raw.startswith("{"):
            try:
                s_data = json.loads(examen_raw)
                s_dict = s_data.get("sistemas", {}) if isinstance(s_data, dict) else {}
                for sist in SISTEMAS_MEDICOS_CATALOGO:
                    if sist["id"] not in s_dict or s_dict[sist["id"]].get("estado") not in ("normal", "anormal"):
                        s_dict[sist["id"]] = {"estado": "normal", "observacion": ""}
                s_data["sistemas"] = s_dict
                form.examen_sistemas.data = json.dumps(s_data)
            except json.JSONDecodeError:
                pass

        try:
            if form.fecha_hora.data:
                consulta.fecha_hora = form.fecha_hora.data
            consulta.motivo_consulta = form.motivo_consulta.data.strip()
            consulta.anamnesis = form.anamnesis.data.strip() if form.anamnesis.data else None
            consulta.alimentacion = (form.alimentacion.data or "").strip() or None
            consulta.desparasitacion_producto = (form.desparasitacion_producto.data or "").strip() or None
            consulta.desparasitacion_fecha = form.desparasitacion_fecha.data
            consulta.vacunacion_producto = (form.vacunacion_producto.data or "").strip() or None
            consulta.vacunacion_fecha = form.vacunacion_fecha.data
            consulta.peso_kg = form.peso_kg.data
            consulta.temperatura_c = form.temperatura_c.data
            consulta.frecuencia_cardiaca = form.frecuencia_cardiaca.data
            consulta.frecuencia_respiratoria = (form.frecuencia_respiratoria.data or "").strip() or None
            consulta.tllc_segundos = form.tllc_segundos.data
            consulta.mucosas = form.mucosas.data or None
            consulta.condicion_corporal = form.condicion_corporal.data or None
            consulta.examen_sistemas = form.examen_sistemas.data.strip() if form.examen_sistemas.data else None
            consulta.diagnostico = form.diagnostico.data.strip()
            consulta.plan_tratamiento = form.plan_tratamiento.data.strip()
            consulta.receta_medica = form.receta_medica.data.strip() if form.receta_medica.data else None
            consulta.observaciones = form.observaciones.data.strip() if form.observaciones.data else None

            # Actualizar alimentación en el perfil si cambió
            if form.alimentacion.data and form.alimentacion.data.strip():
                mascota.alimentacion = form.alimentacion.data.strip()

            # Actualizar o crear control médico si fue seleccionado
            if form.agendar_control.data and form.fecha_proximo_control.data:
                motivo_ctl = form.motivo_control.data.strip() if form.motivo_control.data else f"Control de {consulta.diagnostico}"
                if consulta.controles_asociados:
                    ctl = consulta.controles_asociados[0]
                    ctl.motivo = motivo_ctl
                    ctl.fecha_proximo_control = form.fecha_proximo_control.data
                    ctl.fecha_hora = form.fecha_proximo_control.data
                    ctl.diagnostico = f"Seguimiento: {consulta.diagnostico}"
                    ctl.plan_terapeutico = consulta.plan_tratamiento
                    ctl.medicamento = consulta.receta_medica
                else:
                    nuevo_ctl = ControlMedico(
                        mascota_id=mascota.id,
                        tutor_id=mascota.tutor_id,
                        veterinario_id=current_user.id,
                        consulta_origen_id=consulta.id,
                        motivo=motivo_ctl,
                        fecha_hora=form.fecha_proximo_control.data,
                        peso_kg=form.peso_kg.data,
                        temperatura_c=form.temperatura_c.data,
                        avances=f"Programado desde consulta médica SOAP del {consulta.fecha_hora.strftime('%d/%m/%Y')}",
                        diagnostico=f"Seguimiento: {consulta.diagnostico}",
                        plan_terapeutico=consulta.plan_tratamiento,
                        medicamento=consulta.receta_medica,
                        fecha_proximo_control=form.fecha_proximo_control.data,
                        observaciones=f"Control agendado al editar consulta SOAP. Motivo: {motivo_ctl}",
                        creado_por_id=current_user.id,
                    )
                    db.session.add(nuevo_ctl)

            db.session.commit()
            flash("Consulta médica actualizada correctamente.", "success")
            return redirect(url_for("historias.consulta_detalle", id=consulta.id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al actualizar consulta médica")
            flash("Ocurrió un error al actualizar la consulta.", "danger")
    elif request.method == "POST":
        errores_campos = []
        for field_name, errors in form.errors.items():
            field_label = getattr(form, field_name).label.text if hasattr(getattr(form, field_name), "label") else field_name
            errores_campos.append(f"<strong>{field_label}</strong>: {', '.join(errors)}")
        if errores_campos:
            flash(f"⚠️ No se pudo guardar la consulta. Por favor revisa los siguientes campos obligatorios:<br>• " + "<br>• ".join(errores_campos), "danger")

    return render_template(
        "historias/form_consulta.html",
        form=form,
        mascota=mascota,
        consulta=consulta,
        catalogo_sistemas=SISTEMAS_MEDICOS_CATALOGO,
    )


@bp.route("/consulta/<int:id>/eliminar", methods=["POST"])
@login_required
@clinico_required
def consulta_eliminar(id: int):
    consulta = db.session.get(ConsultaMedica, id)
    if not consulta:
        flash("La consulta médica no existe o ya fue eliminada.", "danger")
        next_url = request.form.get("next")
        return redirect(next_url or url_for("historias.lista"))

    form = SoloCsrfForm()
    if not form.validate_on_submit():
        flash("Error de validación de seguridad (CSRF).", "danger")
        next_url = request.form.get("next")
        return redirect(next_url or url_for("historias.ficha_medica", mascota_id=consulta.mascota_id, tab="general"))

    mascota_id = consulta.mascota_id
    try:
        db.session.delete(consulta)
        db.session.commit()
        flash(f"Consulta médica SOAP #{id} eliminada correctamente.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error al eliminar consulta médica %d", id)
        flash("Error interno al eliminar la consulta médica.", "danger")

    next_url = request.form.get("next")
    return redirect(next_url or url_for("historias.ficha_medica", mascota_id=mascota_id, tab="general"))


@bp.route("/mascota/<int:mascota_id>/control/nuevo", methods=["GET", "POST"])
@login_required
@clinico_required
def control_nuevo(mascota_id: int):
    mascota = db.session.execute(
        select(Mascota)
        .filter_by(id=mascota_id)
        .options(
            selectinload(Mascota.tutor),
            selectinload(Mascota.raza),
            selectinload(Mascota.consultas).selectinload(ConsultaMedica.veterinario),
            selectinload(Mascota.registros_peso),
        )
    ).scalar_one_or_none()
    if not mascota:
        flash("La mascota no existe.", "danger")
        return redirect(url_for("historias.lista"))

    # Obtener última consulta SOAP si existe
    consulta_previa = mascota.consultas[0] if mascota.consultas else None

    form = ControlMedicoForm()
    if not form.is_submitted():
        # Pre-llenar fecha_hora actual
        form.fecha_hora.data = obtener_hora_bogota()
        # Prellenar peso actual si existe
        if mascota.peso_actual:
            form.peso_kg.data = mascota.peso_actual.peso_kg
        if consulta_previa:
            form.consulta_origen_id.data = str(consulta_previa.id)
            if not form.motivo.data:
                if consulta_previa.diagnostico:
                    form.motivo.data = f"Control de {consulta_previa.diagnostico}"
                elif consulta_previa.motivo_consulta:
                    form.motivo.data = f"Control de {consulta_previa.motivo_consulta}"
            if consulta_previa.diagnostico and not form.diagnostico.data:
                form.diagnostico.data = f"Seguimiento: {consulta_previa.diagnostico}"
            if consulta_previa.receta_medica and not form.medicamento.data:
                form.medicamento.data = consulta_previa.receta_medica

    if form.validate_on_submit():
        try:
            consulta_origen_id = None
            if form.consulta_origen_id.data and str(form.consulta_origen_id.data).isdigit():
                consulta_origen_id = int(form.consulta_origen_id.data)

            control = ControlMedico(
                mascota_id=mascota.id,
                tutor_id=mascota.tutor_id,
                veterinario_id=current_user.id,
                consulta_origen_id=consulta_origen_id,
                motivo=form.motivo.data.strip() if form.motivo.data else None,
                fecha_hora=form.fecha_hora.data or obtener_hora_bogota(),
                peso_kg=form.peso_kg.data,
                temperatura_c=form.temperatura_c.data,
                avances=form.avances.data.strip(),
                diagnostico=form.diagnostico.data.strip() if form.diagnostico.data else None,
                plan_terapeutico=form.plan_terapeutico.data.strip(),
                medicamento=form.medicamento.data.strip() if form.medicamento.data else None,
                fecha_proximo_control=form.fecha_proximo_control.data,
                observaciones=form.observaciones.data.strip() if form.observaciones.data else None,
                creado_por_id=current_user.id,
            )
            db.session.add(control)

            # Actualizar peso de la mascota si se registró uno nuevo
            if form.peso_kg.data and (not mascota.peso_actual or form.peso_kg.data != mascota.peso_actual.peso_kg):
                mascota.peso_actual = form.peso_kg.data

            db.session.commit()
            flash("Control médico guardado correctamente.", "success")
            return redirect(url_for("historias.ficha_medica", mascota_id=mascota.id, tab="controles"))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al guardar control médico")
            flash("Ocurrió un error al guardar el control médico.", "danger")

    return render_template(
        "historias/form_control.html",
        form=form,
        mascota=mascota,
        consulta_previa=consulta_previa,
    )


@bp.route("/control/<int:id>/editar", methods=["GET", "POST"])
@login_required
@clinico_required
def control_editar(id: int):
    control = db.session.execute(
        select(ControlMedico)
        .filter_by(id=id)
        .options(
            selectinload(ControlMedico.mascota).selectinload(Mascota.tutor),
            selectinload(ControlMedico.mascota).selectinload(Mascota.raza),
            selectinload(ControlMedico.mascota).selectinload(Mascota.registros_peso),
            selectinload(ControlMedico.consulta_origen).selectinload(ConsultaMedica.veterinario),
            selectinload(ControlMedico.veterinario),
        )
    ).scalar_one_or_none()
    if not control:
        flash("El control médico no existe.", "danger")
        return redirect(url_for("historias.lista"))

    mascota = control.mascota
    consulta_previa = control.consulta_origen
    form = ControlMedicoForm(obj=control)

    if form.validate_on_submit():
        try:
            control.motivo = form.motivo.data.strip() if form.motivo.data else None
            control.fecha_hora = form.fecha_hora.data or control.fecha_hora
            control.peso_kg = form.peso_kg.data
            control.temperatura_c = form.temperatura_c.data
            control.avances = form.avances.data.strip()
            control.diagnostico = form.diagnostico.data.strip() if form.diagnostico.data else None
            control.plan_terapeutico = form.plan_terapeutico.data.strip()
            control.medicamento = form.medicamento.data.strip() if form.medicamento.data else None
            control.fecha_proximo_control = form.fecha_proximo_control.data
            control.observaciones = form.observaciones.data.strip() if form.observaciones.data else None

            # Actualizar peso de la mascota si se registró uno nuevo
            if form.peso_kg.data and (not mascota.peso_actual or form.peso_kg.data != mascota.peso_actual.peso_kg):
                mascota.peso_actual = form.peso_kg.data

            db.session.commit()
            flash("Control médico actualizado correctamente.", "success")
            return redirect(url_for("historias.ficha_medica", mascota_id=mascota.id, tab="controles"))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al actualizar control médico")
            flash("Ocurrió un error al actualizar el control médico.", "danger")

    return render_template(
        "historias/form_control.html",
        form=form,
        mascota=mascota,
        control=control,
        consulta_previa=consulta_previa,
    )


@bp.route("/control/<int:id>/calendario.ics", methods=["GET"])
def control_ics(id: int):
    control = db.session.execute(
        select(ControlMedico)
        .filter_by(id=id)
        .options(
            selectinload(ControlMedico.mascota),
            selectinload(ControlMedico.tutor),
        )
    ).scalar_one_or_none()
    if not control or not control.fecha_proximo_control:
        flash("No hay fecha de próximo control programada.", "warning")
        return redirect(url_for("historias.lista"))

    clinica_nombre = ConfiguracionSistema.obtener("clinica_nombre", "Sandía · Medicina & Spa Veterinario")
    clinica_dir = ConfiguracionSistema.obtener("clinica_direccion", "Clínica Veterinaria")
    titulo = f"🐾 Control Veterinario: {control.mascota.nombre if control.mascota else 'Mascota'}"
    desc = f"Control de seguimiento médico en {clinica_nombre}.\nPaciente: {control.mascota.nombre if control.mascota else ''}\nPlan / Recomendaciones: {control.plan_terapeutico}"

    ics_data = generar_archivo_ics(
        titulo=titulo,
        fecha_inicio=control.fecha_proximo_control,
        duracion_minutos=30,
        descripcion=desc,
        ubicacion=clinica_dir,
        uid=f"control-{control.id}-{control.mascota_id}@sandiavet.com",
    )

    filename = f"Control_{control.mascota.nombre if control.mascota else 'Paciente'}_{control.id}.ics"
    return Response(
        ics_data,
        mimetype="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/calendar; charset=utf-8",
        },
    )


@bp.route("/control/<int:id>/eliminar", methods=["POST"])
@login_required
@clinico_required
def control_eliminar(id: int):
    control = db.session.get(ControlMedico, id)
    if not control:
        flash("El control médico no existe o ya fue eliminado.", "danger")
        next_url = request.form.get("next")
        return redirect(next_url or url_for("historias.lista"))

    form = SoloCsrfForm()
    if not form.validate_on_submit():
        flash("Error de validación de seguridad (CSRF).", "danger")
        next_url = request.form.get("next")
        return redirect(next_url or url_for("historias.ficha_medica", mascota_id=control.mascota_id, tab="controles"))

    mascota_id = control.mascota_id
    try:
        db.session.delete(control)
        db.session.commit()
        flash("Control médico eliminado correctamente.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error al eliminar control médico %d", id)
        flash("Error interno al eliminar el control médico.", "danger")

    next_url = request.form.get("next")
    return redirect(next_url or url_for("historias.ficha_medica", mascota_id=mascota_id, tab="controles"))


@bp.route("/controles-semana", methods=["GET"])
@login_required
@clinico_required
def controles_semana():
    """Vista especializada para visualizar y auditar las consultas SOAP y controles médicos realizados en un periodo."""
    dias = request.args.get("dias", 7, type=int)
    if dias not in (7, 15, 30, 90):
        dias = 7

    tipo = request.args.get("tipo", "todos").strip().lower()
    if tipo not in ("todos", "consultas", "controles"):
        tipo = "todos"

    ahora = obtener_hora_bogota()
    fecha_inicio = ahora - timedelta(days=dias)
    q = (request.args.get("q") or "").strip()
    normalizado = normalizar_texto(q)

    items_unificados = []

    # 1. Controles Médicos
    if tipo in ("todos", "controles"):
        stmt_ctrl = (
            select(ControlMedico)
            .options(
                selectinload(ControlMedico.mascota).selectinload(Mascota.tutor),
                selectinload(ControlMedico.mascota).selectinload(Mascota.raza),
                selectinload(ControlMedico.tutor),
                selectinload(ControlMedico.veterinario),
                selectinload(ControlMedico.consulta_origen),
            )
            .filter(ControlMedico.fecha_hora >= fecha_inicio)
            .order_by(ControlMedico.fecha_hora.desc())
        )

        if normalizado:
            stmt_ctrl = stmt_ctrl.join(Mascota, ControlMedico.mascota_id == Mascota.id).outerjoin(Tutor, Mascota.tutor_id == Tutor.id).filter(
                or_(
                    Mascota.nombre.ilike(f"%{normalizado}%"),
                    Tutor.nombre.ilike(f"%{normalizado}%"),
                    Tutor.apellido.ilike(f"%{normalizado}%"),
                    Tutor.documento.ilike(f"%{normalizado}%"),
                    ControlMedico.motivo.ilike(f"%{normalizado}%"),
                    ControlMedico.diagnostico.ilike(f"%{normalizado}%"),
                    ControlMedico.avances.ilike(f"%{normalizado}%"),
                )
            )

        controles_db = db.session.execute(stmt_ctrl).scalars().all()
        for ctrl in controles_db:
            items_unificados.append({
                "id": ctrl.id,
                "tipo": "control",
                "tipo_etiqueta": "Control",
                "badge_color": "info",
                "fecha_hora": ctrl.fecha_hora,
                "mascota_id": ctrl.mascota_id,
                "mascota": ctrl.mascota,
                "tutor": ctrl.tutor,
                "motivo": ctrl.motivo or "Revisión médica de evolución",
                "detalle_secundario": ctrl.avances,
                "diagnostico": ctrl.diagnostico,
                "peso_kg": ctrl.peso_kg,
                "temperatura_c": ctrl.temperatura_c,
                "veterinario": ctrl.veterinario,
                "fecha_proximo_control": ctrl.fecha_proximo_control,
                "url_ver": url_for("historias.ficha_medica", mascota_id=ctrl.mascota_id, tab="controles"),
                "url_pdf": url_for("historias.control_pdf", id=ctrl.id),
                "url_whatsapp": getattr(ctrl, "enlace_whatsapp", None),
                "url_editar": url_for("historias.control_editar", id=ctrl.id),
                "url_eliminar": url_for("historias.control_eliminar", id=ctrl.id),
            })

    # 2. Consultas SOAP
    if tipo in ("todos", "consultas"):
        stmt_c = (
            select(ConsultaMedica)
            .options(
                selectinload(ConsultaMedica.mascota).selectinload(Mascota.tutor),
                selectinload(ConsultaMedica.mascota).selectinload(Mascota.raza),
                selectinload(ConsultaMedica.tutor),
                selectinload(ConsultaMedica.veterinario),
            )
            .filter(ConsultaMedica.fecha_hora >= fecha_inicio)
            .order_by(ConsultaMedica.fecha_hora.desc())
        )

        if normalizado:
            stmt_c = stmt_c.join(Mascota, ConsultaMedica.mascota_id == Mascota.id).outerjoin(Tutor, Mascota.tutor_id == Tutor.id).filter(
                or_(
                    Mascota.nombre.ilike(f"%{normalizado}%"),
                    Tutor.nombre.ilike(f"%{normalizado}%"),
                    Tutor.apellido.ilike(f"%{normalizado}%"),
                    Tutor.documento.ilike(f"%{normalizado}%"),
                    ConsultaMedica.motivo_consulta.ilike(f"%{normalizado}%"),
                    ConsultaMedica.diagnostico.ilike(f"%{normalizado}%"),
                    ConsultaMedica.plan_tratamiento.ilike(f"%{normalizado}%"),
                )
            )

        consultas_db = db.session.execute(stmt_c).scalars().all()
        for c in consultas_db:
            items_unificados.append({
                "id": c.id,
                "tipo": "soap",
                "tipo_etiqueta": "Consulta SOAP",
                "badge_color": "danger",
                "fecha_hora": c.fecha_hora,
                "mascota_id": c.mascota_id,
                "mascota": c.mascota,
                "tutor": c.tutor,
                "motivo": c.motivo_consulta,
                "detalle_secundario": c.plan_tratamiento,
                "diagnostico": c.diagnostico,
                "peso_kg": c.peso_kg,
                "temperatura_c": c.temperatura_c,
                "veterinario": c.veterinario,
                "fecha_proximo_control": None,
                "url_ver": url_for("historias.consulta_detalle", id=c.id),
                "url_pdf": url_for("historias.consulta_pdf", id=c.id),
                "url_whatsapp": getattr(c, "enlace_whatsapp", None),
                "url_editar": url_for("historias.consulta_editar", id=c.id),
                "url_eliminar": url_for("historias.consulta_eliminar", id=c.id),
            })

    # Ordenar unificados por fecha_hora desc
    items_unificados.sort(key=lambda x: _normalizar_para_orden(x["fecha_hora"]), reverse=True)

    # Contadores y métricas rápidas
    total_periodo = len(items_unificados)
    con_proximo = sum(1 for item in items_unificados if item.get("fecha_proximo_control") is not None)
    total_consultas = sum(1 for item in items_unificados if item["tipo"] == "soap")
    total_controles = sum(1 for item in items_unificados if item["tipo"] == "control")

    # Próximos controles programados para los próximos 7 días a partir de hoy
    fecha_limite_prox = ahora + timedelta(days=7)
    proximos_controles = db.session.execute(
        select(ControlMedico)
        .options(
            selectinload(ControlMedico.mascota),
            selectinload(ControlMedico.tutor),
            selectinload(ControlMedico.veterinario),
        )
        .filter(
            ControlMedico.fecha_proximo_control.is_not(None),
            ControlMedico.fecha_proximo_control >= ahora - timedelta(hours=2),
            ControlMedico.fecha_proximo_control <= fecha_limite_prox,
        )
        .order_by(ControlMedico.fecha_proximo_control.asc())
        .limit(10)
    ).scalars().all()

    form_csrf = SoloCsrfForm()

    return render_template(
        "historias/controles_semana.html",
        items=items_unificados,
        tipo=tipo,
        dias=dias,
        q=q,
        total_periodo=total_periodo,
        con_proximo=con_proximo,
        total_consultas=total_consultas,
        total_controles=total_controles,
        proximos_controles=proximos_controles,
        form_csrf=form_csrf,
    )


@bp.route("/control/<int:id>/pdf", methods=["GET"])
def control_pdf(id: int):
    """Genera y sirve el documento PDF oficial del control médico."""
    control = db.session.execute(
        select(ControlMedico)
        .filter_by(id=id)
        .options(
            selectinload(ControlMedico.mascota).selectinload(Mascota.raza),
            selectinload(ControlMedico.tutor),
            selectinload(ControlMedico.veterinario),
        )
    ).scalar_one_or_none()
    if not control:
        flash("El control médico no existe.", "danger")
        return redirect(url_for("historias.lista"))

    pdf_buffer = generar_pdf_control(control, db.session)
    nombre_archivo = f"Control_{control.mascota.nombre if control.mascota else 'Paciente'}_{control.id:04d}.pdf"
    response = send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=nombre_archivo,
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@bp.route("/consulta/<int:id>", methods=["GET"])
@login_required
@clinico_required
def consulta_detalle(id: int):
    consulta = db.session.execute(
        select(ConsultaMedica)
        .filter_by(id=id)
        .options(
            selectinload(ConsultaMedica.mascota).selectinload(Mascota.raza),
            selectinload(ConsultaMedica.mascota).selectinload(Mascota.tutor),
            selectinload(ConsultaMedica.tutor),
            selectinload(ConsultaMedica.veterinario),
            selectinload(ConsultaMedica.enmiendas).selectinload(EnmiendaConsulta.autor),
            selectinload(ConsultaMedica.controles_asociados).selectinload(ControlMedico.veterinario),
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
    response = send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=nombre_archivo,
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@bp.route("/consulta/<int:id>/receta/pdf", methods=["GET"])
def receta_pdf(id: int):
    """Visor interactivo de Fórmula Médica en PDF con botón directo para enviar a WhatsApp del tutor."""
    if request.args.get("raw") or request.args.get("descargar"):
        return receta_pdf_raw(id)

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

    clinica_datos = ConfiguracionSistema.datos_clinica()
    return render_template("historias/visor_receta_pdf.html", consulta=consulta, clinica=clinica_datos)


@bp.route("/consulta/<int:id>/receta/pdf/raw", methods=["GET"])
def receta_pdf_raw(id: int):
    """Genera y sirve el archivo binario PDF de la fórmula médica."""
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

    descargar = bool(request.args.get("descargar"))
    pdf_buffer = generar_pdf_receta(consulta, db.session)
    nombre_archivo = f"Formula_Medica_{consulta.mascota.nombre if consulta.mascota else 'Paciente'}_{consulta.id:04d}.pdf"
    response = send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=descargar,
        download_name=nombre_archivo,
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@bp.route("/mascota/<int:mascota_id>/expediente/pdf", methods=["GET"])
@login_required
@clinico_required
def expediente_pdf(mascota_id: int):
    """Genera y descarga el documento oficial en PDF con el expediente médico integral de la mascota."""
    mascota = db.session.execute(
        select(Mascota)
        .filter_by(id=mascota_id)
        .options(
            selectinload(Mascota.tutor),
            selectinload(Mascota.raza),
            selectinload(Mascota.consultas).selectinload(ConsultaMedica.veterinario),
            selectinload(Mascota.controles).selectinload(ControlMedico.veterinario),
            selectinload(Mascota.vacunas),
            selectinload(Mascota.desparasitaciones),
            selectinload(Mascota.registros_peso),
        )
    ).scalar_one_or_none()

    if not mascota:
        flash("La mascota no existe.", "danger")
        return redirect(url_for("historias.lista"))

    hospitalizaciones = db.session.execute(
        select(Hospitalizacion)
        .filter_by(mascota_id=mascota.id)
        .order_by(Hospitalizacion.fecha_ingreso.desc())
    ).scalars().all()

    cirugias = db.session.execute(
        select(Cirugia)
        .filter_by(mascota_id=mascota.id)
        .options(selectinload(Cirugia.veterinario))
        .order_by(Cirugia.fecha.desc())
    ).scalars().all()

    examenes = db.session.execute(
        select(ExamenLaboratorio)
        .filter_by(mascota_id=mascota.id)
        .order_by(ExamenLaboratorio.fecha_toma.desc())
    ).scalars().all()

    remisiones = db.session.execute(
        select(RemisionInterna)
        .filter_by(mascota_id=mascota.id)
        .options(selectinload(RemisionInterna.veterinario))
        .order_by(RemisionInterna.fecha_remision.desc())
    ).scalars().all()

    descargar = bool(request.args.get("descargar"))
    pdf_buffer = generar_pdf_expediente_completo(
        mascota,
        db_session=db.session,
        hospitalizaciones=hospitalizaciones,
        cirugias=cirugias,
        examenes=examenes,
        remisiones=remisiones,
    )

    nombre_archivo = f"Expediente_Clinico_{mascota.nombre}_{mascota.id:04d}.pdf"
    response = send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=descargar,
        download_name=nombre_archivo,
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response



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


@bp.route("/consulta/<int:id>/receta/documento", methods=["GET"])
@bp.route("/receta/<int:id>", methods=["GET"])
def receta_documento_publico(id: int):
    """Vista web oficial e interactiva de la fórmula médica / recetario para compartir con el tutor por WhatsApp o imprimir."""
    consulta = db.session.execute(
        select(ConsultaMedica)
        .filter_by(id=id)
        .options(
            selectinload(ConsultaMedica.mascota).selectinload(Mascota.raza),
            selectinload(ConsultaMedica.tutor),
            selectinload(ConsultaMedica.veterinario),
            selectinload(ConsultaMedica.controles_asociados),
        )
    ).scalar_one_or_none()
    if not consulta:
        flash("La fórmula médica solicitada no está disponible o no existe.", "danger")
        return redirect(url_for("auth.login"))

    clinica_datos = ConfiguracionSistema.datos_clinica()
    return render_template("historias/documento_receta.html", consulta=consulta, clinica=clinica_datos)



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


@bp.route("/vacuna/<int:id>/eliminar", methods=["POST"])
@login_required
@clinico_required
def vacuna_eliminar(id: int):
    vacuna = db.session.get(VacunaMascota, id)
    if not vacuna:
        flash("El registro de vacuna no existe o ya fue eliminado.", "danger")
        next_url = request.form.get("next")
        return redirect(next_url or url_for("historias.lista"))

    form = SoloCsrfForm()
    if not form.validate_on_submit():
        flash("Error de validación de seguridad (CSRF).", "danger")
        next_url = request.form.get("next")
        return redirect(next_url or url_for("historias.ficha_medica", mascota_id=vacuna.mascota_id, tab="vacunas"))

    mascota_id = vacuna.mascota_id
    nombre_v = vacuna.nombre_vacuna
    try:
        db.session.delete(vacuna)
        db.session.commit()
        flash(f"Registro de vacuna '{nombre_v}' eliminado correctamente.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error al eliminar vacuna %d", id)
        flash("Error interno al eliminar la vacuna.", "danger")

    next_url = request.form.get("next")
    return redirect(next_url or url_for("historias.ficha_medica", mascota_id=mascota_id, tab="vacunas"))


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


@bp.route("/desparasitacion/<int:id>/eliminar", methods=["POST"])
@login_required
@clinico_required
def desparasitacion_eliminar(id: int):
    desparasitacion = db.session.get(DesparasitacionMascota, id)
    if not desparasitacion:
        flash("El registro de desparasitación no existe o ya fue eliminado.", "danger")
        next_url = request.form.get("next")
        return redirect(next_url or url_for("historias.lista"))

    form = SoloCsrfForm()
    if not form.validate_on_submit():
        flash("Error de validación de seguridad (CSRF).", "danger")
        next_url = request.form.get("next")
        return redirect(next_url or url_for("historias.ficha_medica", mascota_id=desparasitacion.mascota_id, tab="desparasitaciones"))

    mascota_id = desparasitacion.mascota_id
    producto = desparasitacion.producto
    try:
        db.session.delete(desparasitacion)
        db.session.commit()
        flash(f"Registro de desparasitación '{producto}' eliminado correctamente.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error al eliminar desparasitación %d", id)
        flash("Error interno al eliminar la desparasitación.", "danger")

    next_url = request.form.get("next")
    return redirect(next_url or url_for("historias.ficha_medica", mascota_id=mascota_id, tab="desparasitaciones"))



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

            ahora = obtener_hora_bogota()
            hora_actual = ahora.time()
            fecha_toma_dt = datetime.combine(form.fecha_toma.data, hora_actual, tzinfo=ZONA_BOGOTA) if form.fecha_toma.data else ahora

            examen = ExamenLaboratorio(
                mascota_id=mascota.id,
                solicitado_por_id=current_user.id,
                categoria=form.categoria.data or "laboratorio",
                tipo_examen=form.tipo_examen.data,
                fecha_toma=fecha_toma_dt,
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

    fecha_toma_val = examen.fecha_toma.date() if hasattr(examen.fecha_toma, 'date') else examen.fecha_toma
    form_resultado = ResultadoExamenForm(
        categoria=examen.categoria,
        tipo_examen=examen.tipo_examen,
        fecha_toma=fecha_toma_val,
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
            if form.fecha_toma.data:
                # Preservar la hora original si existe o fijar hora en Bogotá
                f_date = form.fecha_toma.data
                hora_orig = examen.fecha_toma.time() if hasattr(examen.fecha_toma, 'time') else datetime.now().time()
                examen.fecha_toma = datetime.combine(f_date, hora_orig).replace(tzinfo=ZONA_BOGOTA)
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
                flash("Estudio y fecha actualizados exitosamente.", "success")

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


@bp.route("/examen/<int:id>/actualizar-fecha", methods=["POST"])
@login_required
@clinico_required
def examen_actualizar_fecha(id: int):
    """Actualiza la fecha de realización de un examen rápidamente desde la ficha médica."""
    examen = db.session.get(ExamenLaboratorio, id)
    if not examen:
        flash("El examen no existe.", "danger")
        return redirect(url_for("historias.lista"))

    fecha_str = (request.form.get("fecha_toma") or "").strip()
    next_url = request.form.get("next") or url_for("historias.ficha_medica", mascota_id=examen.mascota_id, tab="examenes")

    if not fecha_str:
        flash("Debes seleccionar una fecha válida.", "warning")
        return redirect(next_url)

    try:
        f_date = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        hora_orig = examen.fecha_toma.time() if hasattr(examen.fecha_toma, 'time') else datetime.now().time()
        examen.fecha_toma = datetime.combine(f_date, hora_orig).replace(tzinfo=ZONA_BOGOTA)
        db.session.commit()
        flash(f"Fecha del examen '{examen.tipo_examen}' actualizada a {f_date.strftime('%d/%m/%Y')}.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error al actualizar fecha del examen %d", id)
        flash("Ocurrió un error al actualizar la fecha del examen.", "danger")

@bp.route("/consulta/<int:id>/actualizar-fecha", methods=["POST"])
@login_required
@clinico_required
def consulta_actualizar_fecha(id: int):
    """Actualiza la fecha y hora de una consulta médica SOAP rápidamente desde la ficha médica."""
    consulta = db.session.get(ConsultaMedica, id)
    if not consulta:
        flash("La consulta médica no existe.", "danger")
        return redirect(url_for("historias.lista"))

    fecha_hora_str = (request.form.get("fecha_hora") or "").strip()
    next_url = request.form.get("next") or url_for("historias.ficha_medica", mascota_id=consulta.mascota_id, tab="soap")

    if not fecha_hora_str:
        flash("Debes seleccionar una fecha y hora válida.", "warning")
        return redirect(next_url)

    try:
        if len(fecha_hora_str) == 16:  # Formato YYYY-MM-DDTHH:MM
            dt = datetime.strptime(fecha_hora_str, "%Y-%m-%dT%H:%M")
        elif len(fecha_hora_str) == 10:  # Formato YYYY-MM-DD
            d = datetime.strptime(fecha_hora_str, "%Y-%m-%d").date()
            h = consulta.fecha_hora.time() if hasattr(consulta.fecha_hora, 'time') else datetime.now().time()
            dt = datetime.combine(d, h)
        else:
            dt = datetime.fromisoformat(fecha_hora_str)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZONA_BOGOTA)

        consulta.fecha_hora = dt
        db.session.commit()
        flash(f"Fecha y hora de la consulta médica #{consulta.id} actualizada correctamente.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error al actualizar fecha de la consulta %d", id)
        flash("Ocurrió un error al actualizar la fecha y hora de la consulta.", "danger")

    return redirect(next_url)


# ---------------------------------------------------------------------------
# Notas y Novedades Clínicas Rápidas
# ---------------------------------------------------------------------------


@bp.route("/mascota/<int:mascota_id>/nota/nueva", methods=["POST"])
@login_required
@clinico_required
def nota_clinica_nueva(mascota_id: int):
    """Registra una novedad o nota médica rápida para la mascota con hora exacta."""
    mascota = db.session.get(Mascota, mascota_id)
    if not mascota:
        flash("La mascota no existe.", "danger")
        return redirect(url_for("historias.lista"))

    categoria = (request.form.get("categoria") or "seguimiento").strip()
    texto = (request.form.get("texto") or "").strip()
    next_url = request.form.get("next") or url_for("historias.ficha_medica", mascota_id=mascota.id, tab="general")

    if not texto:
        flash("El contenido de la nota clínica no puede estar vacío.", "warning")
        return redirect(next_url)

    if categoria not in CATEGORIAS_NOTA_CLINICA:
        categoria = "seguimiento"

    try:
        nota = NotaClinica(
            mascota_id=mascota.id,
            autor_id=current_user.id,
            categoria=categoria,
            texto=texto,
            fecha=obtener_hora_bogota(),
        )
        db.session.add(nota)
        db.session.commit()
        flash(f"Novedad clínica ({nota.categoria_etiqueta}) registrada con éxito.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error al crear nota clínica para mascota %d", mascota_id)
        flash("No se pudo registrar la nota clínica.", "danger")

    return redirect(next_url)


@bp.route("/nota/<int:id>/eliminar", methods=["POST"])
@login_required
@clinico_required
def nota_clinica_eliminar(id: int):
    """Elimina una nota clínica si fue creada por el usuario actual o si es administrador."""
    nota = db.session.get(NotaClinica, id)
    if not nota:
        flash("La nota clínica no existe.", "danger")
        return redirect(url_for("historias.lista"))

    mascota_id = nota.mascota_id
    next_url = request.form.get("next") or url_for("historias.ficha_medica", mascota_id=mascota_id, tab="general")

    # Autorización: creador o admin
    if current_user.rol != "admin" and nota.autor_id != current_user.id:
        flash("Solo quien redactó la nota o un administrador pueden eliminarla.", "danger")
        return redirect(next_url)

    try:
        db.session.delete(nota)
        db.session.commit()
        flash("Nota clínica eliminada correctamente.", "info")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error al eliminar nota clínica %d", id)
        flash("No se pudo eliminar la nota clínica.", "danger")

    return redirect(next_url)


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
            telefono_destino=(form.telefono_destino.data or "").strip() or None,
            direccion_destino=(form.direccion_destino.data or "").strip() or None,
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


@bp.route("/remisiones/<int:id>/eliminar", methods=["POST"])
@login_required
@clinico_required
def remision_eliminar(id: int):
    remision = db.session.get(RemisionInterna, id)
    if not remision:
        flash("La remisión no existe o ya fue eliminada.", "danger")
        next_url = request.form.get("next")
        return redirect(next_url or url_for("historias.lista"))

    form = SoloCsrfForm()
    if not form.validate_on_submit():
        flash("Error de validación de seguridad (CSRF).", "danger")
        next_url = request.form.get("next")
        return redirect(next_url or url_for("historias.ficha_medica", mascota_id=remision.mascota_id, tab="remisiones"))

    mascota_id = remision.mascota_id
    try:
        db.session.delete(remision)
        db.session.commit()
        flash("Remisión clínica eliminada correctamente.", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error al eliminar remisión clínica %d", id)
        flash("Error interno al eliminar la remisión clínica.", "danger")

    next_url = request.form.get("next")
    return redirect(next_url or url_for("historias.ficha_medica", mascota_id=mascota_id, tab="remisiones"))


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


@bp.route("/remisiones/<int:id>/pdf", methods=["GET"])
def remision_pdf(id: int):
    """Genera y descarga la orden oficial de remisión médica en PDF."""
    remision = db.session.execute(
        select(RemisionInterna)
        .filter_by(id=id)
        .options(
            selectinload(RemisionInterna.veterinario),
            selectinload(RemisionInterna.mascota).selectinload(Mascota.raza),
            selectinload(RemisionInterna.tutor),
        )
    ).scalar_one_or_none()

    if not remision:
        flash("La orden de remisión clínica no existe.", "danger")
        return redirect(url_for("historias.lista"))

    pdf_buffer = generar_pdf_remision(remision, db.session)
    nombre_archivo = f"Remision_{remision.mascota.nombre if remision.mascota else 'Paciente'}_{remision.id:04d}.pdf"
    response = send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=nombre_archivo,
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@bp.route("/mascota/<int:mascota_id>/carnet/pdf", methods=["GET"])
def carnet_vacunacion_pdf(mascota_id: int):
    """Genera y descarga el carnet oficial de vacunación y desparasitación en PDF."""
    mascota = db.session.execute(
        select(Mascota)
        .filter_by(id=mascota_id)
        .options(
            selectinload(Mascota.raza),
            selectinload(Mascota.tutor),
            selectinload(Mascota.vacunas).selectinload(VacunaMascota.veterinario),
            selectinload(Mascota.desparasitaciones).selectinload(DesparasitacionMascota.veterinario),
        )
    ).scalar_one_or_none()

    if not mascota:
        flash("La mascota no existe.", "danger")
        return redirect(url_for("historias.lista"))

    pdf_buffer = generar_pdf_carnet_vacunacion(mascota, db.session)
    nombre_archivo = f"Carnet_Vacunacion_{mascota.nombre}_{mascota.id:04d}.pdf"
    response = send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=nombre_archivo,
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@bp.route("/mascota/<int:mascota_id>/dieta/actualizar", methods=["POST"])
@login_required
@clinico_required
def actualizar_dieta(mascota_id: int):
    mascota = db.session.get(Mascota, mascota_id)
    if not mascota:
        abort(404)
    nueva_dieta = (request.form.get("alimentacion") or "").strip()
    mascota.alimentacion = nueva_dieta if nueva_dieta else None
    db.session.commit()
    flash(f"Alimentación y dieta de {mascota.nombre} actualizada correctamente.", "success")
    return redirect(url_for("historias.ficha_medica", mascota_id=mascota.id))


# ---------------------------------------------------------------------------
# Importación masiva de Historias Clínicas / Consultas desde Excel
# ---------------------------------------------------------------------------


@bp.route("/plantilla-excel")
@login_required
@clinico_required
def plantilla_excel():
    """Descarga la plantilla oficial en Excel (.xlsx) para importar historias clínicas / consultas."""
    columnas = [
        "ID_Historia",
        "Fecha",
        "Mascota",
        "Especie",
        "Raza",
        "Propietario",
        "Doc_Propietario",
        "Veterinario",
        "Motivo_Consulta",
        "Anamnesis",
        "Antecedentes",
        "Peso",
        "Temperatura",
        "Frec_Cardiaca",
        "Frec_Respiratoria",
        "Examen_General",
        "Diag_Presuntivo",
        "Diag_Final",
        "Diag_Definitivo",
        "Plan_Terapeutico",
        "Tratamiento",
        "Medicamentos",
        "Pronostico",
        "Observaciones",
    ]
    ejemplos = [
        {
            "ID_Historia": 360,
            "Fecha": "5/09/2026 16:43",
            "Mascota": "ROMA CUBIDES",
            "Especie": "Canino",
            "Raza": "Mestizo",
            "Propietario": "LAURA CUBIDES",
            "Doc_Propietario": "1015454709",
            "Veterinario": "Sandia medicina y spa veterinario",
            "Motivo_Consulta": "LE MOLESTA EL OJO",
            "Anamnesis": "LE HA LAGRIMEADO EL OJO MUCHO Y SE RRASCA CON LA MANO",
            "Antecedentes": "",
            "Peso": "",
            "Temperatura": 38.9,
            "Frec_Cardiaca": 68,
            "Frec_Respiratoria": 40,
            "Examen_General": "EPIFORA, IRRITACION A NIVEL OCULAR",
            "Diag_Presuntivo": "",
            "Diag_Final": "",
            "Diag_Definitivo": "",
            "Plan_Terapeutico": "",
            "Tratamiento": "",
            "Medicamentos": "",
            "Pronostico": "",
            "Observaciones": "",
        },
        {
            "ID_Historia": 359,
            "Fecha": "5/09/2026 15:16",
            "Mascota": "COCO MENDEZ",
            "Especie": "Canino",
            "Raza": "Yorkshire",
            "Propietario": "JOSHUA MENDEZ",
            "Doc_Propietario": "1031131493",
            "Veterinario": "Sandia medicina y spa veterinario",
            "Motivo_Consulta": "LO MORDIERON EN EL OJO",
            "Anamnesis": "LO MORDIO EL HERMANO EN EL OJO",
            "Antecedentes": "",
            "Peso": 4.10,
            "Temperatura": 39.1,
            "Frec_Cardiaca": 68,
            "Frec_Respiratoria": "JADEO",
            "Examen_General": "",
            "Diag_Presuntivo": "",
            "Diag_Final": "",
            "Diag_Definitivo": "",
            "Plan_Terapeutico": "",
            "Tratamiento": "",
            "Medicamentos": "MELOXICAM GOTAS 0.16ML UNTIRAL 0.3 ML",
            "Pronostico": "",
            "Observaciones": "",
        },
    ]

    df = pd.DataFrame(ejemplos, columns=columnas)
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="HistoriasClinicas")
    out.seek(0)

    return send_file(
        out,
        as_attachment=True,
        download_name="plantilla_historias_clinicas_sandia.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _convertir_examen_general_a_json(texto_general: str) -> str:
    """Convierte texto plano de Examen_General a la estructura JSON esperada por examen_sistemas."""
    if not texto_general or not texto_general.strip():
        sistemas_dict = {}
        for s in SISTEMAS_MEDICOS_CATALOGO:
            sistemas_dict[s["id"]] = {"estado": "normal", "observacion": "", "nombre": s["nombre"]}
        return json.dumps({"sistemas": sistemas_dict}, ensure_ascii=False)

    txt = texto_general.strip()
    norm = normalizar_texto(txt)

    # Detección de sistemas afectados por palabras clave
    anormales = set()
    # Órganos de los sentidos: ojo, ocular, otico, oido, cornea, pupila, etc.
    if any(k in norm for k in ("ojo", "ocular", "otico", "oido", "pupil", "cornea", "epifora", "blefaro", "conjuntiv", "vision", "olfato")):
        anormales.add("organos_sentidos")

    # Gastrointestinal: vomito, diarrea, abdomen, estomago, heces, palpa, etc.
    if any(k in norm for k in ("vomit", "diarre", "abdomen", "abdom", "epigastr", "gastr", "timpan", "heces", "tartaro", "dental")):
        anormales.add("gastrointestinal")

    # Tegumentario: piel, lesion, pelo, rasca, cara, cola, eritema, pulga, prurito, etc.
    if any(k in norm for k in ("piel", "lesion", "pelo", "pelaje", "rasca", "cara", "cola", "eritem", "prurit", "pulga", "alopeci", "caspa", "pioderm", "ectoparasit", "seborre")):
        anormales.add("tegumentario")

    # Músculo-esquelético: apoyo, tren posterior, temblores, claudica, cojera, pata, etc.
    if any(k in norm for k in ("apoyo", "tren posterior", "temblor", "claudic", "cojer", "articul", "panicular", "extremidad", "marcha", "pata")):
        anormales.add("musculo_esqueletico")

    # Ganglios linfáticos: ganglio, linfonodulo, submandibular, etc.
    if any(k in norm for k in ("ganglio", "linfaden", "linfonod")):
        anormales.add("ganglio_linfatico")

    # Sistema respiratorio (opcional si menciona pulmón, sibilancias, etc.)
    if any(k in norm for k in ("pulmon", "estertor", "roncus", "sibilan", "tos", "traquea")):
        anormales.add("respiratorio")

    # Sistema cardíaco
    if any(k in norm for k in ("soplo", "arritmi", "cardiac")):
        anormales.add("cardiaco")

    # Sistema nervioso
    if any(k in norm for k in ("ataxia", "convuls", "reflejo espinal", "nervios")):
        anormales.add("nervioso")

    # Urinario
    if any(k in norm for k in ("vejiga", "renal", "rinon", "hematuria", "disuria")):
        anormales.add("urinario")

    # Reproductivo
    if any(k in norm for k in ("vulv", "prepuc", "testicul", "mamar", "utero")):
        anormales.add("reproductivo")

    sistemas_dict = {}
    for s in SISTEMAS_MEDICOS_CATALOGO:
        s_id = s["id"]
        if s_id in anormales:
            sistemas_dict[s_id] = {
                "estado": "anormal",
                "observacion": txt,
                "nombre": s["nombre"],
            }
        else:
            sistemas_dict[s_id] = {
                "estado": "normal",
                "observacion": "",
                "nombre": s["nombre"],
            }

    return json.dumps({"sistemas": sistemas_dict}, ensure_ascii=False)


@bp.route("/importar-excel", methods=["GET", "POST"])
@login_required
@clinico_required
def importar_excel():
    """Importación masiva de historias clínicas / consultas médicas desde Excel (.xlsx) o CSV (.csv)."""
    form = ImportarExcelForm()
    form_csrf = SoloCsrfForm()
    reporte = None

    if form.validate_on_submit():
        archivo = form.archivo.data
        try:
            df = leer_archivo_tabular(archivo)
        except Exception as exc:
            current_app.logger.exception("Error al procesar archivo de historias clínicas")
            flash(f"No se pudo procesar el archivo: {exc}", "danger")
            return redirect(url_for("historias.importar_excel"))

        # Limpiar nombres de columnas
        df.columns = [str(c).strip() for c in df.columns]

        col_paciente = next((c for c in df.columns if c.lower() in ("paciente", "id_paciente", "id_mascota", "codigo_paciente")), None)
        col_mascota = next((c for c in df.columns if c.lower() in ("mascota", "nombre_mascota", "nombre")), None)

        if not col_paciente and not col_mascota:
            flash("Falta la columna para identificar al paciente ('paciente' o 'Mascota') en el archivo.", "danger")
            return redirect(url_for("historias.importar_excel"))

        col_motivo = next((c for c in df.columns if c.lower() in ("motivo_consulta", "motivo", "razon_consulta")), None)
        col_doc_prop = next((c for c in df.columns if c.lower() in ("doc_propietario", "documento", "doc", "cedula")), None)
        col_nom_prop = next((c for c in df.columns if c.lower() in ("propietario", "tutor", "dueno", "dueño")), None)
        col_anamnesis = next((c for c in df.columns if c.lower() in ("anamnesis", "subjetivo", "historia")), None)
        col_antecedentes = next((c for c in df.columns if c.lower() in ("antecedentes", "previos")), None)
        col_peso = next((c for c in df.columns if c.lower() in ("peso", "peso_kg")), None)
        col_temp = next((c for c in df.columns if c.lower() in ("temperatura", "temperatura_c", "temp")), None)
        col_fc = next((c for c in df.columns if c.lower() in ("frec_cardiaca", "fc", "frecuencia_cardiaca")), None)
        col_fr = next((c for c in df.columns if c.lower() in ("frec_respiratoria", "fr", "frecuencia_respiratoria")), None)
        col_examen = next((c for c in df.columns if c.lower() in ("examen_general", "examen_fisico", "examen_sistemas", "hallazgos")), None)
        col_diag_def = next((c for c in df.columns if c.lower() in ("diag_definitivo", "diagnostico_definitivo")), None)
        col_diag_fin = next((c for c in df.columns if c.lower() in ("diag_final", "diagnostico_final", "diagnostico", "diag")), None)
        col_diag_pres = next((c for c in df.columns if c.lower() in ("diag_presuntivo", "diagnostico_presuntivo")), None)
        col_plan = next((c for c in df.columns if c.lower() in ("plan_terapeutico", "plan", "plan_tratamiento")), None)
        col_trat = next((c for c in df.columns if c.lower() in ("tratamiento", "terapia")), None)
        col_med = next((c for c in df.columns if c.lower() in ("medicamentos", "medicamento", "receta", "receta_medica", "formula")), None)
        col_pronostico = next((c for c in df.columns if c.lower() in ("pronostico", "pronóstico")), None)
        col_obs = next((c for c in df.columns if c.lower() in ("observaciones", "notas")), None)
        col_vet = next((c for c in df.columns if c.lower() in ("veterinario", "medico", "doctor", "atendido_por")), None)
        col_fecha = next((c for c in df.columns if c.lower() in ("fecha", "fecha_hora", "fecha_consulta")), None)
        col_especie = next((c for c in df.columns if c.lower() in ("especie", "tipo_animal")), None)
        col_raza = next((c for c in df.columns if c.lower() in ("raza",)), None)

        creados = 0
        errores = []
        lote_uuid = str(uuid.uuid4())

        def _limpiar(val):
            if val is None or pd.isna(val):
                return ""
            s = str(val).strip()
            return "" if s.lower() in ("nan", "none", "null") else s

        def _parsear_fecha(texto):
            if not texto:
                return None
            formatos = [
                "%d/%m/%Y %H:%M:%S",
                "%d/%m/%Y %H:%M",
                "%d/%m/%Y",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d %H:%M",
                "%Y-%m-%d",
                "%d-%m-%Y %H:%M",
                "%d-%m-%Y",
            ]
            for fmt in formatos:
                try:
                    return datetime.strptime(texto, fmt)
                except ValueError:
                    continue
            return None

        # Ordenar DataFrame de forma ASCENDENTE por fecha antes de iterar
        if col_fecha and col_fecha in df.columns:
            try:
                fechas_parseadas = df[col_fecha].apply(lambda x: _parsear_fecha(_limpiar(x)) or datetime.min)
                df["__fecha_sort"] = fechas_parseadas
                df = df.sort_values(by="__fecha_sort", ascending=True).reset_index(drop=True)
            except Exception as e_sort:
                current_app.logger.warning("No se pudo pre-ordenar df por fecha: %s", e_sort)

        # Buscar usuario veterinario por defecto (Dra. Daniela Pulido o veterinario principal activo)
        vet_default = db.session.execute(
            select(Usuario).where(
                or_(
                    Usuario.nombre.ilike("%Daniela%"),
                    Usuario.email == "veterinaria@sandiavet.com",
                    Usuario.email == "veterinario@sandia.com",
                    Usuario.rol == "veterinario",
                ),
                Usuario.activo.is_(True),
            )
        ).scalars().first()
        if not vet_default:
            vet_default = db.session.execute(
                select(Usuario).where(Usuario.rol == "admin", Usuario.activo.is_(True))
            ).scalars().first() or current_user

        try:
            for indice, fila in df.iterrows():
                num_fila = indice + 2

                paciente_val = _limpiar(fila.get(col_paciente)) if col_paciente else ""
                nombre_mascota = _limpiar(fila.get(col_mascota)) if col_mascota else ""

                if not paciente_val and not nombre_mascota:
                    errores.append(f"Fila {num_fila}: No se especificó el paciente ni la mascota.")
                    continue

                # REGLA TÉCNICA: Vinculación inteligente y segura de Mascota.
                mascota = None
                doc_prop = _limpiar(fila.get(col_doc_prop)) if col_doc_prop else ""
                nom_prop = _limpiar(fila.get(col_nom_prop)) if col_nom_prop else ""

                # 1) Buscar primero por ID legado (id_externo) que provino de pacientes
                if paciente_val:
                    mascota = db.session.execute(
                        select(Mascota).where(Mascota.id_externo == paciente_val)
                    ).scalar_one_or_none()

                # 2) Si no se encontró por ID legado, buscar por Tutor + Nombre de Mascota
                norm_mascota = normalizar_texto(nombre_mascota) if nombre_mascota else ""
                tutor = None

                if doc_prop:
                    tutor = db.session.execute(
                        select(Tutor).where(Tutor.numero_documento == doc_prop)
                    ).scalar_one_or_none()
                if not tutor and nom_prop:
                    norm_nom = normalizar_texto(nom_prop)
                    tutor = db.session.execute(
                        select(Tutor).where(Tutor.nombre_busqueda == norm_nom)
                    ).scalars().first()

                if not mascota and tutor and norm_mascota:
                    # a) Coincidencia exacta con Mascota.nombre_busqueda == norm_mascota
                    mascota = db.session.execute(
                        select(Mascota).where(
                            Mascota.tutor_id == tutor.id,
                            Mascota.nombre_busqueda == norm_mascota,
                        )
                    ).scalar_one_or_none()

                    # b) Quitar palabras del nombre/apellido del propietario o tomar primera palabra
                    if not mascota:
                        palabras_tutor = set(normalizar_texto(tutor.nombre_completo or nom_prop).split())
                        palabras_mascota = norm_mascota.split()
                        palabras_filtradas = [p for p in palabras_mascota if p not in palabras_tutor]
                        primer_nombre = palabras_filtradas[0] if palabras_filtradas else (palabras_mascota[0] if palabras_mascota else "")

                        mascotas_tutor = db.session.execute(
                            select(Mascota).where(Mascota.tutor_id == tutor.id)
                        ).scalars().all()

                        for m in mascotas_tutor:
                            m_norm = m.nombre_busqueda or normalizar_texto(m.nombre)
                            m_primer = m_norm.split()[0] if m_norm.split() else ""
                            if (primer_nombre and (m_norm == primer_nombre or m_norm.startswith(primer_nombre) or m_primer == primer_nombre)) or (norm_mascota and m_norm in norm_mascota):
                                mascota = m
                                break

                # Si no hay tutor explícito y no se encontró mascota, buscar coincidencia por nombre de mascota activa
                if not mascota and norm_mascota:
                    coincidencias = db.session.execute(
                        select(Mascota).where(
                            Mascota.nombre_busqueda == norm_mascota,
                            Mascota.activo.is_(True),
                        )
                    ).scalars().all()
                    if len(coincidencias) == 1:
                        mascota = coincidencias[0]

                # c) Auto-crear tutor y mascota si aún no existen para no perder filas del CSV
                if not mascota:
                    if not tutor:
                        nom_tutor_crear = nom_prop or f"Tutor de {nombre_mascota or 'Paciente'}"
                        tutor = Tutor(
                            nombre_completo=nom_tutor_crear,
                            tipo_documento="CC" if doc_prop else None,
                            numero_documento=doc_prop or None,
                            creado_por_id=current_user.id,
                        )
                        db.session.add(tutor)
                        db.session.flush()

                    # Limpiar nombre para la nueva mascota: quitar apellido del propietario si está pegado
                    palabras_tutor = set(normalizar_texto(tutor.nombre_completo or nom_prop).split())
                    partes_nom = nombre_mascota.split()
                    partes_limpias = [p for p in partes_nom if normalizar_texto(p) not in palabras_tutor]
                    nombre_final_mascota = " ".join(partes_limpias) if partes_limpias else (partes_nom[0] if partes_nom else (nombre_mascota or "Paciente"))

                    esp_val = (_limpiar(fila.get(col_especie)) if col_especie else "").lower()
                    especie_final = "canino"
                    if "felin" in esp_val or "gato" in esp_val:
                        especie_final = "felino"
                    elif "ave" in esp_val:
                        especie_final = "ave"
                    elif "roedor" in esp_val or "conejo" in esp_val:
                        especie_final = "roedor"

                    mascota = Mascota(
                        tutor_id=tutor.id,
                        nombre=nombre_final_mascota,
                        especie=especie_final,
                        id_externo=paciente_val or None,
                        creado_por_id=current_user.id,
                    )
                    db.session.add(mascota)
                    db.session.flush()

                # Veterinario asignado
                vet_nom = _limpiar(fila.get(col_vet)) if col_vet else ""
                vet_user = None
                norm_vet = normalizar_texto(vet_nom) if vet_nom else ""

                if "sandia" in norm_vet:
                    vet_user = vet_default
                elif norm_vet:
                    vet_user = db.session.execute(
                        select(Usuario).where(
                            Usuario.rol.in_(("veterinario", "admin")),
                            Usuario.nombre.ilike(f"%{norm_vet}%"),
                        )
                    ).scalars().first()

                if not vet_user:
                    vet_user = vet_default or current_user

                # Fecha de la consulta
                f_dt = _parsear_fecha(_limpiar(fila.get(col_fecha))) if col_fecha else None
                fecha_hora = f_dt.replace(tzinfo=ZONA_BOGOTA) if f_dt else obtener_hora_bogota()

                # Constantes vitales con limpieza de errores de digitación
                def _a_decimal(val):
                    txt = _limpiar(val).replace(",", ".")
                    if not txt:
                        return None
                    try:
                        return Decimal(txt)
                    except (InvalidOperation, ValueError):
                        return None

                def _a_int(val):
                    txt = _limpiar(val)
                    if not txt:
                        return None
                    digs = "".join([c for c in txt if c.isdigit()])
                    return int(digs) if digs else None

                peso_kg = _a_decimal(fila.get(col_peso)) if col_peso else None
                temp_c = _a_decimal(fila.get(col_temp)) if col_temp else None
                fc = _a_int(fila.get(col_fc)) if col_fc else None
                fr_raw = (_limpiar(fila.get(col_fr)) if col_fr else "") or None
                examen_gral = (_limpiar(fila.get(col_examen)) if col_examen else "") or None

                # Limpiezas específicas según especificación
                # 1) Si peso_kg > 100, dividirlo entre 10
                if peso_kg is not None and peso_kg > 100:
                    peso_kg = (peso_kg / Decimal(10)).quantize(Decimal("0.01"))

                # 2) Si temp_c < 32.0 o > 43.0, None
                if temp_c is not None and (temp_c < Decimal("32.0") or temp_c > Decimal("43.0")):
                    temp_c = None

                # 3) Si fc > 350, dividirlo entre 10; si fc < 20, None
                if fc is not None:
                    if fc > 350:
                        fc = fc // 10
                    if fc < 20:
                        fc = None

                # 4) fr_raw: "JAEO" -> "JADEO", "E" -> None
                if fr_raw:
                    fr_limpio = fr_raw.strip().upper()
                    if fr_limpio == "JAEO":
                        fr_raw = "JADEO"
                    elif fr_limpio == "E":
                        fr_raw = None

                # Examen de sistemas JSON interactivo
                examen_sistemas_json = _convertir_examen_general_a_json(examen_gral)

                # Motivo, Diagnóstico y Tratamiento
                motivo = (_limpiar(fila.get(col_motivo)) if col_motivo else "") or "Consulta médica veterinaria"

                anamnesis_txt = _limpiar(fila.get(col_anamnesis)) if col_anamnesis else ""
                antecedentes_txt = _limpiar(fila.get(col_antecedentes)) if col_antecedentes else ""
                if antecedentes_txt:
                    anamnesis_txt = f"{anamnesis_txt}\n[Antecedentes]: {antecedentes_txt}".strip()

                diag_def = _limpiar(fila.get(col_diag_def)) if col_diag_def else ""
                diag_fin = _limpiar(fila.get(col_diag_fin)) if col_diag_fin else ""
                diag_pres = _limpiar(fila.get(col_diag_pres)) if col_diag_pres else ""
                diagnostico_final = diag_def or diag_fin or diag_pres or "Evaluación clínica general"

                plan_ter = _limpiar(fila.get(col_plan)) if col_plan else ""
                tratamiento = _limpiar(fila.get(col_trat)) if col_trat else ""
                medicamentos = _limpiar(fila.get(col_med)) if col_med else ""
                pronostico = _limpiar(fila.get(col_pronostico)) if col_pronostico else ""
                observaciones = _limpiar(fila.get(col_obs)) if col_obs else ""

                # Si medicamentos está vacío y plan_ter contiene fármacos/dosis, copiar plan_ter a receta_medica
                if not medicamentos and plan_ter:
                    norm_plan = normalizar_texto(plan_ter).upper()
                    palabras_clave_rx = (
                        "ML", "MG", "GOTAS", "TABLETAS", "CADA", "MELOXICAM",
                        "DIPIRONA", "OMEPRAZOL", "ONDASETRON", "LACTATO",
                        "CLORHEXIDINA", "DEXAMETASONA",
                    )
                    if any(pk in norm_plan for pk in palabras_clave_rx):
                        medicamentos = plan_ter

                partes_plan = []
                if plan_ter:
                    partes_plan.append(plan_ter)
                if tratamiento:
                    partes_plan.append(f"Tratamiento: {tratamiento}")
                plan_completo = "\n".join(partes_plan) if partes_plan else (diagnostico_final or "Manejo médico según evolución")

                obs_lista = []
                if observaciones:
                    obs_lista.append(observaciones)
                if pronostico:
                    obs_lista.append(f"Pronóstico: {pronostico}")
                observaciones_completas = "\n".join(obs_lista) if obs_lista else None

                nueva_consulta = ConsultaMedica(
                    mascota_id=mascota.id,
                    tutor_id=mascota.tutor_id,
                    veterinario_id=vet_user.id,
                    fecha_hora=fecha_hora,
                    motivo_consulta=motivo,
                    anamnesis=anamnesis_txt or None,
                    peso_kg=peso_kg,
                    temperatura_c=temp_c,
                    frecuencia_cardiaca=fc,
                    frecuencia_respiratoria=fr_raw,
                    examen_sistemas=examen_sistemas_json,
                    diagnostico=diagnostico_final,
                    plan_tratamiento=plan_completo,
                    receta_medica=medicamentos or None,
                    observaciones=observaciones_completas,
                    creado_por_id=current_user.id,
                    lote_importacion=lote_uuid,
                )
                db.session.add(nueva_consulta)

                # Proteger mascota.peso_actual de datos viejos
                if peso_kg is not None:
                    debe_actualizar_peso = False
                    if not mascota.peso_actual:
                        debe_actualizar_peso = True
                    else:
                        ultima_consulta = db.session.execute(
                            select(ConsultaMedica.fecha_hora)
                            .where(ConsultaMedica.mascota_id == mascota.id)
                            .order_by(ConsultaMedica.fecha_hora.desc())
                        ).scalars().first()
                        if not ultima_consulta or fecha_hora >= ultima_consulta:
                            debe_actualizar_peso = True

                    if debe_actualizar_peso:
                        mascota.peso_actual = peso_kg

                creados += 1

            # Registrar lote de importación
            lote_registro = LoteImportacion(
                uuid=lote_uuid,
                tipo="historias",
                nombre_archivo=getattr(archivo, "filename", "historias_clinicas.xlsx"),
                creados=creados,
                actualizados=0,
                usuario_id=current_user.id,
            )
            db.session.add(lote_registro)

            # Transacción atómica
            db.session.commit()

            reporte = {
                "lote_uuid": lote_uuid,
                "creados": creados,
                "actualizados": 0,
                "errores": errores,
                "total_procesados": creados,
            }
            flash(
                f"Importación de historias finalizada. Creadas: {creados}, Con observaciones: {len(errores)}.",
                "success" if not errores else "warning",
            )
        except Exception as exc:
            db.session.rollback()
            current_app.logger.exception("Error general al importar lote de historias clínicas")
            flash(f"Ocurrió un error y se canceló la importación (Rollback preventivo): {exc}", "danger")

    lotes_recientes = db.session.execute(
        select(LoteImportacion).where(LoteImportacion.tipo == "historias").order_by(LoteImportacion.fecha.desc()).limit(5)
    ).scalars().all()

    return render_template(
        "historias/importar.html",
        form=form,
        form_csrf=form_csrf,
        reporte=reporte,
        lotes_recientes=lotes_recientes,
    )


@bp.route("/revertir-lote/<uuid_lote>", methods=["POST"])
@login_required
@admin_required
def revertir_lote(uuid_lote):
    """Elimina de forma segura únicamente las consultas médicas creadas en el lote indicado."""
    form_csrf = SoloCsrfForm()
    if not form_csrf.validate_on_submit():
        flash("Error de validación de seguridad (CSRF).", "danger")
        return redirect(url_for("historias.importar_excel"))

    lote = db.session.execute(
        select(LoteImportacion).where(LoteImportacion.uuid == uuid_lote, LoteImportacion.tipo == "historias")
    ).scalar_one_or_none()

    if not lote:
        flash("El lote de historias clínicas no existe.", "danger")
        return redirect(url_for("historias.importar_excel"))

    if lote.revertido:
        flash("Este lote ya fue revertido previamente.", "warning")
        return redirect(url_for("historias.importar_excel"))

    consultas = db.session.execute(
        select(ConsultaMedica).where(ConsultaMedica.lote_importacion == uuid_lote)
    ).scalars().all()

    eliminadas = 0
    no_eliminables = 0
    try:
        for c in consultas:
            if c.enmiendas or c.controles_asociados or c.venta_id:
                no_eliminables += 1
                continue
            db.session.delete(c)
            eliminadas += 1

        lote.revertido = True
        lote.fecha_reversion = obtener_hora_bogota()
        lote.usuario_reversion_id = current_user.id
        db.session.commit()

        msg = f"Reversión finalizada: Se eliminaron {eliminadas} consultas del lote."
        if no_eliminables > 0:
            msg += f" {no_eliminables} consultas se conservaron porque ya cuentan con enmiendas, controles o ventas asociadas."
        flash(msg, "info")
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Error al revertir lote %s de historias", uuid_lote)
        flash(f"Error al revertir lote: {exc}", "danger")

    return redirect(url_for("historias.importar_excel"))


@bp.route("/revertir-ultimo-lote", methods=["POST"])
@login_required
@admin_required
def revertir_ultimo_lote():
    """Botón de pánico: Busca el último lote de historias, elimina sus consultas y el lote."""
    form_csrf = SoloCsrfForm()
    if not form_csrf.validate_on_submit():
        flash("Error de validación de seguridad (CSRF).", "danger")
        return redirect(url_for("historias.importar_excel"))

    ultimo_lote = db.session.execute(
        select(LoteImportacion)
        .where(LoteImportacion.tipo == "historias")
        .order_by(LoteImportacion.fecha.desc(), LoteImportacion.id.desc())
    ).scalars().first()

    if not ultimo_lote:
        flash("No hay ningún lote de importación masiva de historias para revertir.", "warning")
        return redirect(url_for("historias.importar_excel"))

    try:
        # Eliminar únicamente las consultas médicas pertenecientes a este lote_uuid
        # NUNCA tocar las que tienen lote_importacion == None
        consultas = db.session.execute(
            select(ConsultaMedica).where(ConsultaMedica.lote_importacion == ultimo_lote.uuid)
        ).scalars().all()

        eliminadas = 0
        for c in consultas:
            db.session.delete(c)
            eliminadas += 1

        # Eliminar el registro del lote
        db.session.delete(ultimo_lote)
        db.session.commit()

        flash(
            f"¡Reversión de pánico exitosa! Se eliminó el lote '{ultimo_lote.nombre_archivo or ultimo_lote.uuid}' y {eliminadas} consultas médicas asociadas. Los datos previos del sistema permanecen intactos.",
            "success",
        )
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Error al revertir último lote de historias")
        flash(f"Error al revertir el último lote: {exc}", "danger")

    return redirect(url_for("historias.importar_excel"))
