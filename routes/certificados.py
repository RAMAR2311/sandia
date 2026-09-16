"""Rutas y controladores para el Certificado Nacional de Salud Animal / Viajes."""

import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import selectinload

from decorators import clinico_required
from models import (
    ESTADOS_CERTIFICADO,
    FINALIDADES_CERTIFICADO,
    CertificadoSaludAnimal,
    ConfiguracionSistema,
    ConsultaMedica,
    DesparasitacionMascota,
    Mascota,
    Tutor,
    Usuario,
    VacunaMascota,
    db,
)
from pdf_generator import generar_pdf_certificado_salud
from utils import hoy_bogota, obtener_hora_bogota

bp_certificados = Blueprint("certificados", __name__, url_prefix="/certificados")


DICTAMEN_PREDETERMINADO = (
    "Certifico que en la fecha he examinado clínicamente al ejemplar arriba descrito, "
    "encontrándolo en estado de salud aparente satisfactorio, sin signos clínicos de enfermedades infectocontagiosas, "
    "zoonóticas ni parasitarias transmisibles, con su plan de inmunización y desparasitación vigente "
    "y en condiciones fisiológicas adecuadas para su movilización y convivencia."
)


# ---------------------------------------------------------------------------
# Listado y Dashboard de Certificados
# ---------------------------------------------------------------------------


@bp_certificados.route("/", methods=["GET"])
@login_required
def lista():
    """Listado general de certificados emitidos con búsqueda y filtros."""
    q = request.args.get("q", "").strip()
    finalidad = request.args.get("finalidad", "").strip()
    estado = request.args.get("estado", "").strip()

    stmt = (
        select(CertificadoSaludAnimal)
        .options(
            selectinload(CertificadoSaludAnimal.mascota).selectinload(Mascota.raza),
            selectinload(CertificadoSaludAnimal.tutor),
            selectinload(CertificadoSaludAnimal.veterinario),
        )
        .order_by(desc(CertificadoSaludAnimal.fecha_emision))
    )

    if finalidad and finalidad in FINALIDADES_CERTIFICADO:
        stmt = stmt.where(CertificadoSaludAnimal.finalidad == finalidad)
    if estado and estado in ESTADOS_CERTIFICADO:
        stmt = stmt.where(CertificadoSaludAnimal.estado == estado)
    if q:
        termino = f"%{q}%"
        stmt = stmt.join(CertificadoSaludAnimal.mascota).join(CertificadoSaludAnimal.tutor).where(
            or_(
                CertificadoSaludAnimal.consecutivo.ilike(termino),
                Mascota.nombre.ilike(termino),
                Tutor.nombre_completo.ilike(termino),
                Tutor.numero_documento.ilike(termino),
                CertificadoSaludAnimal.ciudad_destino.ilike(termino),
            )
        )

    certificados = db.session.execute(stmt).scalars().all()

    return render_template(
        "certificados/lista.html",
        certificados=certificados,
        finalidades=FINALIDADES_CERTIFICADO,
        estados=ESTADOS_CERTIFICADO,
        q=q,
        finalidad_filtro=finalidad,
        estado_filtro=estado,
    )


# ---------------------------------------------------------------------------
# Formulario de Emisión Clínica
# ---------------------------------------------------------------------------


@bp_certificados.route("/emitir/<int:mascota_id>", methods=["GET"])
@login_required
@clinico_required
def form_emision(mascota_id: int):
    """Carga el formulario inteligente de emisión pre-poblando historial y constantes."""
    mascota = db.session.execute(
        select(Mascota)
        .where(Mascota.id == mascota_id)
        .options(
            selectinload(Mascota.tutor),
            selectinload(Mascota.raza),
            selectinload(Mascota.registros_peso),
            selectinload(Mascota.vacunas),
            selectinload(Mascota.desparasitaciones),
            selectinload(Mascota.consultas),
        )
    ).scalar_one_or_none()

    if not mascota:
        flash("Mascota no encontrada.", "danger")
        return redirect(url_for("mascotas.lista"))

    # Constantes vitales recientes de la última consulta si existen
    ultima_consulta = mascota.consultas[0] if mascota.consultas else None
    temp_sugerida = ultima_consulta.temperatura_c if ultima_consulta and ultima_consulta.temperatura_c else "38.5"
    fc_sugerida = ultima_consulta.frecuencia_cardiaca if ultima_consulta and ultima_consulta.frecuencia_cardiaca else "110"
    fr_sugerida = ultima_consulta.frecuencia_respiratoria if ultima_consulta and ultima_consulta.frecuencia_respiratoria else "24"
    peso_sugerido = mascota.peso_actual.peso_kg if mascota.peso_actual else (ultima_consulta.peso_kg if ultima_consulta and ultima_consulta.peso_kg else "0.0")

    # Historial de Vacunación: estructurar para el formulario
    vacunas_sugeridas = []
    vacunas_mascota = mascota.vacunas or []
    for v in vacunas_mascota[:5]:  # Tomar hasta 5 más recientes
        vacunas_sugeridas.append({
            "nombre": v.nombre_vacuna,
            "laboratorio": v.laboratorio or "Zoetis / MSD / Boehringer",
            "lote": v.lote or "LT-" + obtener_hora_bogota().strftime("%y%m"),
            "fecha_aplicacion": v.fecha_aplicacion.strftime("%Y-%m-%d") if v.fecha_aplicacion else "",
            "fecha_proxima": v.fecha_proxima.strftime("%Y-%m-%d") if v.fecha_proxima else "",
        })

    # Si no hay vacunas, pre-cargar estructura básica incluyendo Antirrábica
    if not vacunas_sugeridas:
        hoy_str = hoy_bogota().strftime("%Y-%m-%d")
        prox_str = (hoy_bogota() + timedelta(days=365)).strftime("%Y-%m-%d")
        vacunas_sugeridas = [
            {
                "nombre": "Antirrábica (Rabia)",
                "laboratorio": "Defensor 3 / Rabisin",
                "lote": "LT-" + obtener_hora_bogota().strftime("%y%m"),
                "fecha_aplicacion": hoy_str,
                "fecha_proxima": prox_str,
            },
            {
                "nombre": "Hexavalente Canina (DHPPiL)" if mascota.especie == "canino" else "Triple Felina (FVRCP)",
                "laboratorio": "Vanguard Plus / Nobivac",
                "lote": "LT-" + obtener_hora_bogota().strftime("%y%m"),
                "fecha_aplicacion": hoy_str,
                "fecha_proxima": prox_str,
            },
        ]

    # Desparasitaciones recientes
    desp_interna_sug = {}
    desp_externa_sug = {}
    for d in (mascota.desparasitaciones or []):
        if d.tipo == "interna" and not desp_interna_sug:
            desp_interna_sug = {
                "producto": d.producto,
                "principio_activo": "Febantel / Pirantel / Praziquantel",
                "lote": "L-" + obtener_hora_bogota().strftime("%y%m"),
                "fecha": d.fecha_aplicacion.strftime("%Y-%m-%d") if d.fecha_aplicacion else "",
            }
        elif d.tipo in ("externa", "mixta") and not desp_externa_sug:
            desp_externa_sug = {
                "producto": d.producto,
                "principio_activo": "Fluralaner / Sarolaner / Afoxolaner",
                "lote": "L-" + obtener_hora_bogota().strftime("%y%m"),
                "fecha": d.fecha_aplicacion.strftime("%Y-%m-%d") if d.fecha_aplicacion else "",
            }

    if not desp_interna_sug:
        desp_interna_sug = {
            "producto": "Drontal Plus / Total F",
            "principio_activo": "Praziquantel + Pirantel + Febantel",
            "lote": "L-" + obtener_hora_bogota().strftime("%y%m"),
            "fecha": hoy_bogota().strftime("%Y-%m-%d"),
        }
    if not desp_externa_sug:
        desp_externa_sug = {
            "producto": "Bravecto / Nexgard Spectra / Simparica",
            "principio_activo": "Fluralaner / Sarolaner / Afoxolaner",
            "lote": "L-" + obtener_hora_bogota().strftime("%y%m"),
            "fecha": hoy_bogota().strftime("%Y-%m-%d"),
        }

    clinica = ConfiguracionSistema.datos_clinica()

    return render_template(
        "certificados/form_emision.html",
        mascota=mascota,
        tutor=mascota.tutor,
        clinica=clinica,
        finalidades=FINALIDADES_CERTIFICADO,
        temp_sugerida=temp_sugerida,
        fc_sugerida=fc_sugerida,
        fr_sugerida=fr_sugerida,
        peso_sugerido=peso_sugerido,
        vacunas_sugeridas=vacunas_sugeridas,
        desp_interna_sug=desp_interna_sug,
        desp_externa_sug=desp_externa_sug,
        dictamen_predeterminado=DICTAMEN_PREDETERMINADO,
    )


@bp_certificados.route("/emitir/<int:mascota_id>", methods=["POST"])
@login_required
@clinico_required
def procesar_emision(mascota_id: int):
    """Procesa y almacena el Certificado de Salud Animal con consecutivo y SHA-256."""
    mascota = db.session.execute(
        select(Mascota).where(Mascota.id == mascota_id).options(selectinload(Mascota.tutor))
    ).scalar_one_or_none()

    if not mascota:
        flash("Mascota no encontrada.", "danger")
        return redirect(url_for("mascotas.lista"))

    # Si la petición es JSON
    es_json = request.is_json
    datos = request.get_json() if es_json else request.form

    finalidad = (datos.get("finalidad") or "viaje_nacional").strip()
    ciudad_origen = (datos.get("ciudad_origen") or "Bogotá D.C.").strip()
    ciudad_destino = (datos.get("ciudad_destino") or "").strip()
    pais_destino = (datos.get("pais_destino") or "Colombia").strip()

    try:
        peso_kg = Decimal(str(datos.get("peso_kg") or "0.0").replace(",", "."))
        if peso_kg <= Decimal("0.0"):
            raise ValueError("El peso debe ser mayor a 0 kg")
    except (InvalidOperation, ValueError):
        msg = "Por favor ingresa un peso válido (mayor a 0 kg)."
        if es_json:
            return jsonify({"success": False, "error": msg}), 400
        flash(msg, "danger")
        return redirect(url_for("certificados.form_emision", mascota_id=mascota.id))

    try:
        temp_val = datos.get("temperatura_c")
        temperatura_c = Decimal(str(temp_val).replace(",", ".")) if temp_val else None
    except Exception:
        temperatura_c = None

    try:
        fc_val = datos.get("frecuencia_cardiaca")
        frecuencia_cardiaca = int(fc_val) if fc_val else None
    except Exception:
        frecuencia_cardiaca = None

    try:
        fr_val = datos.get("frecuencia_respiratoria")
        frecuencia_respiratoria = int(fr_val) if fr_val else None
    except Exception:
        frecuencia_respiratoria = None

    try:
        dias_vigencia = int(datos.get("dias_vigencia") or 5)
        dias_vigencia = max(1, min(dias_vigencia, 30))
    except Exception:
        dias_vigencia = 5

    dictamen_texto = (datos.get("dictamen_texto") or DICTAMEN_PREDETERMINADO).strip()
    observaciones = (datos.get("observaciones") or "").strip()
    apto_para_viajar = True if str(datos.get("apto_para_viajar", "true")).lower() in ("true", "1", "on", "si", "sí") else False

    # Procesar lista de vacunas
    vacunas_raw = datos.get("datos_vacunacion")
    if isinstance(vacunas_raw, str):
        try:
            datos_vacunacion = json.loads(vacunas_raw)
        except Exception:
            datos_vacunacion = []
    elif isinstance(vacunas_raw, list):
        datos_vacunacion = vacunas_raw
    else:
        datos_vacunacion = []

    # Procesar desparasitación
    desp_raw = datos.get("datos_desparasitacion")
    if isinstance(desp_raw, str):
        try:
            datos_desparasitacion = json.loads(desp_raw)
        except Exception:
            datos_desparasitacion = {}
    elif isinstance(desp_raw, dict):
        datos_desparasitacion = desp_raw
    else:
        datos_desparasitacion = {
            "interna": {
                "producto": (datos.get("desp_interna_producto") or "Drontal Plus").strip(),
                "principio_activo": (datos.get("desp_interna_principio") or "Febantel / Pirantel / Praziquantel").strip(),
                "lote": (datos.get("desp_interna_lote") or "LT-01").strip(),
                "fecha": (datos.get("desp_interna_fecha") or hoy_bogota().strftime("%Y-%m-%d")).strip(),
            },
            "externa": {
                "producto": (datos.get("desp_externa_producto") or "Bravecto / Simparica").strip(),
                "principio_activo": (datos.get("desp_externa_principio") or "Fluralaner / Sarolaner").strip(),
                "lote": (datos.get("desp_externa_lote") or "LT-01").strip(),
                "fecha": (datos.get("desp_externa_fecha") or hoy_bogota().strftime("%Y-%m-%d")).strip(),
            },
        }

    # Generación de consecutivo único con año y número secuencial
    anio_actual = obtener_hora_bogota().year
    conteo_total = db.session.execute(select(func.count(CertificadoSaludAnimal.id))).scalar_one() or 0
    consecutivo = f"CERT-{anio_actual}-{(conteo_total + 1):04d}"

    # Fechas
    fecha_emision = obtener_hora_bogota()
    fecha_vencimiento = hoy_bogota() + timedelta(days=dias_vigencia)

    certificado = CertificadoSaludAnimal(
        consecutivo=consecutivo,
        mascota_id=mascota.id,
        tutor_id=mascota.tutor_id,
        veterinario_id=current_user.id,
        finalidad=finalidad,
        ciudad_origen=ciudad_origen,
        ciudad_destino=ciudad_destino,
        pais_destino=pais_destino,
        peso_kg=peso_kg,
        temperatura_c=temperatura_c,
        frecuencia_cardiaca=frecuencia_cardiaca,
        frecuencia_respiratoria=frecuencia_respiratoria,
        dictamen_texto=dictamen_texto,
        apto_para_viajar=apto_para_viajar,
        observaciones=observaciones,
        datos_vacunacion=datos_vacunacion,
        datos_desparasitacion=datos_desparasitacion,
        estado="vigente",
        dias_vigencia=dias_vigencia,
        fecha_emision=fecha_emision,
        fecha_vencimiento=fecha_vencimiento,
        hash_integridad_sha256="",
    )

    db.session.add(certificado)
    db.session.flush()

    # Cálculo y asignación del hash SHA-256
    certificado.hash_integridad_sha256 = certificado.calcular_hash_integridad()
    db.session.commit()

    if es_json:
        return jsonify({
            "success": True,
            "id": certificado.id,
            "consecutivo": certificado.consecutivo,
            "url_pdf": certificado.url_pdf(),
            "url_verificacion": certificado.url_verificacion_publica(),
            "enlace_whatsapp": certificado.enlace_whatsapp(),
            "mensaje": f"Certificado {certificado.consecutivo} emitido exitosamente.",
        })

    flash(f"¡Certificado {certificado.consecutivo} emitido y certificado con éxito!", "success")
    return redirect(url_for("certificados.lista"))


# ---------------------------------------------------------------------------
# Descarga / Visualización de PDF Oficial
# ---------------------------------------------------------------------------


@bp_certificados.route("/<int:id>/pdf", methods=["GET"])
def certificado_pdf(id: int):
    """Genera y descarga en streaming el PDF Oficial del Certificado."""
    cert = db.session.execute(
        select(CertificadoSaludAnimal)
        .where(CertificadoSaludAnimal.id == id)
        .options(
            selectinload(CertificadoSaludAnimal.mascota).selectinload(Mascota.raza),
            selectinload(CertificadoSaludAnimal.tutor),
            selectinload(CertificadoSaludAnimal.veterinario),
        )
    ).scalar_one_or_none()

    if not cert:
        abort(404)

    pdf_buffer = generar_pdf_certificado_salud(cert, db.session)
    nombre_archivo = f"Certificado_Salud_{cert.consecutivo}_{cert.mascota.nombre}.pdf"

    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=nombre_archivo,
    )


# ---------------------------------------------------------------------------
# Vista Pública de Verificación (Mobile-First / QR para Aerolíneas e ICA)
# ---------------------------------------------------------------------------


@bp_certificados.route("/verificar/<token>", methods=["GET"])
def vista_verificacion_publica(token: str):
    """Pantalla pública de validación rápida anti-fraude para aerolíneas y autoridades."""
    cert = db.session.execute(
        select(CertificadoSaludAnimal)
        .where(CertificadoSaludAnimal.token_verificacion == token)
        .options(
            selectinload(CertificadoSaludAnimal.mascota).selectinload(Mascota.raza),
            selectinload(CertificadoSaludAnimal.tutor),
            selectinload(CertificadoSaludAnimal.veterinario),
        )
    ).scalar_one_or_none()

    if not cert:
        abort(404)

    clinica = ConfiguracionSistema.datos_clinica()

    return render_template(
        "certificados/verificar_publico.html",
        cert=cert,
        clinica=clinica,
    )


# ---------------------------------------------------------------------------
# Anulación de Certificado
# ---------------------------------------------------------------------------


@bp_certificados.route("/<int:id>/anular", methods=["POST"])
@login_required
@clinico_required
def anular(id: int):
    """Anula un certificado emitido."""
    cert = db.session.execute(
        select(CertificadoSaludAnimal).where(CertificadoSaludAnimal.id == id)
    ).scalar_one_or_none()

    if not cert:
        flash("Certificado no encontrado.", "danger")
        return redirect(url_for("certificados.lista"))

    cert.estado = "anulado"
    db.session.commit()
    flash(f"Certificado {cert.consecutivo} ha sido anulado.", "warning")
    return redirect(request.referrer or url_for("certificados.lista"))
