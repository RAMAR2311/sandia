"""Rutas y controladores para el módulo de Consentimientos Informados Digitales."""

import re
from datetime import datetime
from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import selectinload

from decorators import clinico_required
from models import (
    CLASIFICACIONES_ASA,
    CONFIGURACION_INICIAL,
    DESTINOS_CUERPO,
    ESTADOS_CONSENTIMIENTO,
    TIPOS_CONSENTIMIENTO,
    ConfiguracionSistema,
    ConsentimientoEmitido,
    ConsultaMedica,
    FirmaConsentimiento,
    Mascota,
    PlantillaConsentimiento,
    Tutor,
    Usuario,
    db,
)
from utils import enlace_whatsapp, obtener_hora_bogota

bp_consentimientos = Blueprint("consentimientos", __name__, url_prefix="/consentimientos")


def renderizar_variables_consentimiento(
    texto_template: str,
    mascota: Mascota,
    tutor: Tutor,
    vet: Usuario,
    diagnostico: str = "",
    rcp_texto: str = "",
    asa_texto: str = "",
    destino_texto: str = "",
) -> str:
    """Inyecta de forma segura los datos de la mascota, tutor y veterinario en la plantilla."""
    ahora_str = obtener_hora_bogota().strftime("%d/%m/%Y %I:%M %p")
    clinica_nombre = ConfiguracionSistema.obtener("clinica_nombre") or "Sandía · Medicina y Spa Veterinario"
    
    # Documento del tutor
    doc_tutor = tutor.documento_texto if hasattr(tutor, "documento_texto") and tutor.documento_texto else (tutor.numero_documento or "No registrado")
    tel_tutor = tutor.whatsapp_efectivo or tutor.telefono or "No registrado"
    dir_tutor = tutor.direccion or "No registrada"
    email_tutor = tutor.email or "No registrado"

    # Datos de la mascota
    nombre_mascota = mascota.nombre
    especie_mascota = mascota.especie_etiqueta if hasattr(mascota, "especie_etiqueta") else mascota.especie
    raza_mascota = mascota.raza.nombre if mascota.raza else "Mestizo"
    edad_mascota = mascota.edad if hasattr(mascota, "edad") and mascota.edad else "No determinada"
    sexo_mascota = mascota.sexo_etiqueta if hasattr(mascota, "sexo_etiqueta") else mascota.sexo
    peso_mascota = str(mascota.peso_actual.peso_kg) if (hasattr(mascota, "peso_actual") and mascota.peso_actual) else "--"
    microchip_mascota = mascota.microchip or "Sin microchip registrado"

    # Datos del veterinario
    nombre_vet = vet.nombre if vet else "Médico Veterinario de Turno"
    tp_vet = getattr(vet, "tarjeta_profesional", None) or "En trámite"

    mapa_reemplazo = {
        "nombre_tutor": tutor.nombre_completo,
        "documento_tutor": doc_tutor,
        "telefono_tutor": tel_tutor,
        "direccion_tutor": dir_tutor,
        "email_tutor": email_tutor,
        "nombre_paciente": nombre_mascota,
        "especie": especie_mascota,
        "raza": raza_mascota,
        "edad": edad_mascota,
        "sexo": sexo_mascota,
        "peso": peso_mascota,
        "id_microchip": microchip_mascota,
        "nombre_veterinario": nombre_vet,
        "tarjeta_profesional": tp_vet,
        "nombre_clinica": clinica_nombre,
        "fecha_hora": ahora_str,
        "diagnostico_motivo": diagnostico or "Procedimiento clínico según criterio e indicación médica",
        "rcp_directiva": rcp_texto,
        "clasificacion_asa": asa_texto,
        "destino_cuerpo": destino_texto,
    }

    def _sustituir(match):
        clave = match.group(1).strip()
        return mapa_reemplazo.get(clave, f"{{{{{clave}}}}}")

    return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", _sustituir, texto_template or "")


# ---------------------------------------------------------------------------
# Vistas Principales y Gestión
# ---------------------------------------------------------------------------


@bp_consentimientos.route("/", methods=["GET"])
@login_required
@clinico_required
def lista():
    """Listado general de consentimientos emitidos y administración de plantillas."""
    q = request.args.get("q", "").strip()
    tipo = request.args.get("tipo", "").strip()
    estado = request.args.get("estado", "").strip()

    stmt = (
        select(ConsentimientoEmitido)
        .options(
            selectinload(ConsentimientoEmitido.mascota).selectinload(Mascota.raza),
            selectinload(ConsentimientoEmitido.tutor),
            selectinload(ConsentimientoEmitido.veterinario),
            selectinload(ConsentimientoEmitido.firma),
        )
        .order_by(desc(ConsentimientoEmitido.creado_en))
    )

    if tipo and tipo in TIPOS_CONSENTIMIENTO:
        stmt = stmt.where(ConsentimientoEmitido.tipo == tipo)
    if estado and estado in ESTADOS_CONSENTIMIENTO:
        stmt = stmt.where(ConsentimientoEmitido.estado == estado)
    if q:
        termino = f"%{q}%"
        stmt = stmt.join(ConsentimientoEmitido.mascota).join(ConsentimientoEmitido.tutor).where(
            or_(
                Mascota.nombre.ilike(termino),
                Tutor.nombre_completo.ilike(termino),
                Tutor.numero_documento.ilike(termino),
                ConsentimientoEmitido.titulo.ilike(termino),
            )
        )

    consentimientos = db.session.execute(stmt).scalars().all()
    plantillas = db.session.execute(
        select(PlantillaConsentimiento).where(PlantillaConsentimiento.activo.is_(True)).order_by(PlantillaConsentimiento.tipo)
    ).scalars().all()

    return render_template(
        "consentimientos/lista.html",
        consentimientos=consentimientos,
        plantillas=plantillas,
        tipos=TIPOS_CONSENTIMIENTO,
        estados=ESTADOS_CONSENTIMIENTO,
        q=q,
        tipo_filtro=tipo,
        estado_filtro=estado,
    )


# ---------------------------------------------------------------------------
# API / AJAX para Emisión Médica
# ---------------------------------------------------------------------------


@bp_consentimientos.route("/preparar", methods=["POST"])
@login_required
@clinico_required
def preparar():
    """Genera el borrador inicial reemplazando variables dinámicas."""
    data = request.get_json() or {}
    mascota_id = data.get("mascota_id")
    codigo_plantilla = data.get("codigo_plantilla")
    diagnostico = (data.get("diagnostico_motivo") or "").strip()
    rcp_opt = data.get("autoriza_rcp")
    asa_opt = data.get("clasificacion_asa")
    destino_opt = data.get("destino_cuerpo")

    if not mascota_id:
        return jsonify({"success": False, "error": "Falta especificar la mascota"}), 400

    mascota = db.session.execute(
        select(Mascota).where(Mascota.id == mascota_id).options(selectinload(Mascota.raza), selectinload(Mascota.tutor))
    ).scalar_one_or_none()
    if not mascota:
        return jsonify({"success": False, "error": "Mascota no encontrada"}), 404

    plantilla = None
    if codigo_plantilla:
        plantilla = db.session.execute(
            select(PlantillaConsentimiento).where(PlantillaConsentimiento.codigo == codigo_plantilla, PlantillaConsentimiento.activo.is_(True))
        ).scalar_one_or_none()

    if not plantilla:
        plantilla = db.session.execute(
            select(PlantillaConsentimiento).where(PlantillaConsentimiento.activo.is_(True)).order_by(PlantillaConsentimiento.id)
        ).scalar_one_or_none()

    if not plantilla:
        return jsonify({"success": False, "error": "No hay plantillas disponibles en el sistema"}), 404

    rcp_texto = "SÍ AUTORIZA Reanimación Cardiopulmonar (RCP)" if rcp_opt is True else ("NO AUTORIZA Reanimación (DNR / Orden de No Reanimar)" if rcp_opt is False else "")
    asa_texto = CLASIFICACIONES_ASA.get(asa_opt, "") if asa_opt else ""
    destino_texto = DESTINOS_CUERPO.get(destino_opt, "") if destino_opt else ""

    contenido_renderizado = renderizar_variables_consentimiento(
        texto_template=plantilla.contenido_template,
        mascota=mascota,
        tutor=mascota.tutor,
        vet=current_user,
        diagnostico=diagnostico,
        rcp_texto=rcp_texto,
        asa_texto=asa_texto,
        destino_texto=destino_texto,
    )

    return jsonify({
        "success": True,
        "plantilla_id": plantilla.id,
        "codigo": plantilla.codigo,
        "tipo": plantilla.tipo,
        "tipo_etiqueta": plantilla.tipo_etiqueta,
        "titulo": plantilla.titulo,
        "contenido": contenido_renderizado,
        "tutor_nombre": mascota.tutor.nombre_completo,
        "tutor_documento": mascota.tutor.documento_texto or mascota.tutor.numero_documento or "",
        "tutor_telefono": mascota.tutor.whatsapp_efectivo or mascota.tutor.telefono or "",
        "mascota_nombre": mascota.nombre,
    })


@bp_consentimientos.route("/emitir", methods=["POST"])
@login_required
@clinico_required
def emitir():
    """Guarda el consentimiento final editado por el médico y genera el token único para firma."""
    data = request.get_json() or {}
    mascota_id = data.get("mascota_id")
    plantilla_id = data.get("plantilla_id")
    tipo = data.get("tipo") or "personalizado"
    titulo = (data.get("titulo") or "").strip()
    contenido_final = (data.get("contenido_final") or "").strip()

    if not mascota_id or not contenido_final:
        return jsonify({"success": False, "error": "Datos incompletos para emitir el consentimiento"}), 400

    mascota = db.session.execute(
        select(Mascota).where(Mascota.id == mascota_id).options(selectinload(Mascota.tutor))
    ).scalar_one_or_none()
    if not mascota:
        return jsonify({"success": False, "error": "Mascota no encontrada"}), 404

    if not titulo:
        titulo = TIPOS_CONSENTIMIENTO.get(tipo, "Consentimiento Informado")

    consentimiento = ConsentimientoEmitido(
        plantilla_id=plantilla_id,
        mascota_id=mascota.id,
        tutor_id=mascota.tutor_id,
        veterinario_id=current_user.id,
        consulta_id=data.get("consulta_id"),
        tipo=tipo,
        titulo=titulo,
        contenido_final=contenido_final,
        diagnostico_motivo=data.get("diagnostico_motivo"),
        procedimiento_propuesto=data.get("procedimiento_propuesto"),
        clasificacion_asa=data.get("clasificacion_asa"),
        autoriza_rcp=data.get("autoriza_rcp"),
        destino_cuerpo=data.get("destino_cuerpo"),
        estado="pendiente_firma",
    )

    db.session.add(consentimiento)
    db.session.commit()

    return jsonify({
        "success": True,
        "consentimiento_id": consentimiento.id,
        "token_publico": consentimiento.token_publico,
        "url_firma": consentimiento.url_firma_publica(),
        "url_documento": consentimiento.url_documento(),
        "enlace_whatsapp": consentimiento.enlace_whatsapp(),
        "mensaje": "Consentimiento emitido correctamente. Listo para firmar o enviar.",
    })


# ---------------------------------------------------------------------------
# Flujo de Firma Pública (Mobile-First / Tablet / WhatsApp)
# ---------------------------------------------------------------------------


@bp_consentimientos.route("/firmar/<token>", methods=["GET"])
def vista_firma_publica(token: str):
    """Página web pública para que el tutor lea y firme el consentimiento."""
    doc = db.session.execute(
        select(ConsentimientoEmitido)
        .where(ConsentimientoEmitido.token_publico == token)
        .options(
            selectinload(ConsentimientoEmitido.mascota).selectinload(Mascota.raza),
            selectinload(ConsentimientoEmitido.tutor),
            selectinload(ConsentimientoEmitido.veterinario),
            selectinload(ConsentimientoEmitido.firma),
        )
    ).scalar_one_or_none()

    if not doc:
        abort(404)

    clinica_datos = ConfiguracionSistema.datos_clinica()

    return render_template(
        "consentimientos/firma_publica.html",
        doc=doc,
        clinica=clinica_datos,
    )


@bp_consentimientos.route("/firmar/<token>/guardar", methods=["POST"])
def guardar_firma_publica(token: str):
    """Recibe la firma táctil/canvas, calcula el hash SHA-256 de integridad y sella el documento."""
    doc = db.session.execute(
        select(ConsentimientoEmitido)
        .where(ConsentimientoEmitido.token_publico == token)
        .options(selectinload(ConsentimientoEmitido.tutor), selectinload(ConsentimientoEmitido.firma))
    ).scalar_one_or_none()

    if not doc:
        return jsonify({"success": False, "error": "Documento no encontrado"}), 404

    if doc.estado == "firmado" and doc.firma:
        return jsonify({"success": False, "error": "Este documento ya fue firmado previamente."}), 400

    data = request.get_json() or {}
    trazo_png = data.get("firma_png")
    if not trazo_png or not trazo_png.startswith("data:image/png;base64,"):
        return jsonify({"success": False, "error": "El trazo de la firma digital es requerido."}), 400

    nombre_firmante = (data.get("nombre_firmante") or doc.tutor.nombre_completo).strip()
    doc_firmante = (data.get("documento_firmante") or doc.tutor.documento_texto or doc.tutor.numero_documento or "No registrado").strip()
    parentesco = (data.get("parentesco_o_calidad") or "Propietario / Tutor Legal").strip()
    canal = (data.get("canal_firma") or "remoto_web").strip()

    # Cálculo del Hash SHA-256 de integridad del documento firmado
    hash_sha256 = doc.calcular_hash_integridad()

    firma = FirmaConsentimiento(
        consentimiento_id=doc.id,
        nombre_firmante=nombre_firmante,
        documento_firmante=doc_firmante,
        parentesco_o_calidad=parentesco,
        trazo_firma_png=trazo_png,
        ip_origen=request.headers.get("X-Forwarded-For", request.remote_addr),
        user_agent=(request.headers.get("User-Agent") or "")[:250],
        canal_firma=canal,
        hash_documento_sha256=hash_sha256,
        firmado_en=obtener_hora_bogota(),
    )

    doc.estado = "firmado"
    db.session.add(firma)
    db.session.commit()

    return jsonify({
        "success": True,
        "mensaje": "¡Consentimiento firmado y certificado exitosamente!",
        "url_documento": doc.url_documento(),
    })


# ---------------------------------------------------------------------------
# Vista Oficial Membretada (Impresión / Consulta)
# ---------------------------------------------------------------------------


@bp_consentimientos.route("/<int:id>/documento", methods=["GET"])
def documento_publico(id: int):
    """Vista web oficial membretada para ver, descargar o imprimir el consentimiento."""
    doc = db.session.execute(
        select(ConsentimientoEmitido)
        .where(ConsentimientoEmitido.id == id)
        .options(
            selectinload(ConsentimientoEmitido.mascota).selectinload(Mascota.raza),
            selectinload(ConsentimientoEmitido.tutor),
            selectinload(ConsentimientoEmitido.veterinario),
            selectinload(ConsentimientoEmitido.firma),
        )
    ).scalar_one_or_none()

    if not doc:
        flash("El documento solicitado no existe o fue retirado.", "danger")
        return redirect(url_for("consentimientos.lista"))

    clinica_datos = ConfiguracionSistema.datos_clinica()

    return render_template(
        "consentimientos/documento.html",
        doc=doc,
        clinica=clinica_datos,
    )


@bp_consentimientos.route("/<int:id>/anular", methods=["POST"])
@login_required
@clinico_required
def anular(id: int):
    """Anula un consentimiento emitido por error o cambio de indicación clínica."""
    doc = db.session.execute(select(ConsentimientoEmitido).where(ConsentimientoEmitido.id == id)).scalar_one_or_none()
    if not doc:
        flash("Consentimiento no encontrado.", "danger")
        return redirect(url_for("consentimientos.lista"))

    doc.estado = "anulado"
    db.session.commit()
    flash(f"Consentimiento #{doc.id} anulado.", "warning")
    return redirect(request.referrer or url_for("consentimientos.lista"))
