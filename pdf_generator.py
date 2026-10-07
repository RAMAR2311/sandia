"""Generador de documentos PDF oficiales para Sandía VetCare con ReportLab.

Incluye:
- Informe Clínico de Consulta Médica (SOAP) y Examen por Sistemas
- Fórmula Médica / Prescripción (Rx)
- Comprobante / Factura de Venta POS
- Certificado y Resumen de Spa & Peluquería
"""

import io
import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm

# Paleta de colores oficial de Sandía VetCare
COLOR_PRIMARIO = colors.HexColor("#E53935")      # Rojo Sandía
COLOR_PRIMARIO_OSCURO = colors.HexColor("#B71C1C")
COLOR_SECUNDARIO = colors.HexColor("#2E7D32")    # Verde Follaje
COLOR_OSCURO = colors.HexColor("#1E293B")        # Slate oscuro
COLOR_GRIS_FONDO = colors.HexColor("#F8FAFC")
COLOR_GRIS_BORDE = colors.HexColor("#E2E8F0")
COLOR_TEXTO = colors.HexColor("#334155")
COLOR_ALERTA = colors.HexColor("#EF4444")
COLOR_EXITO = colors.HexColor("#10B981")


def _obtener_datos_clinica(db_session=None):
    """Recupera la configuración de la clínica y doctora principal o valores por defecto."""
    datos = {
        "nombre": "Sandía",
        "subtitulo": "Medicina y Spa Veterinario",
        "nit": "901.554.892-1",
        "direccion": "Cra. 15 # 104-32, Usaquén",
        "ciudad": "Bogotá D.C., Colombia",
        "telefono": "312 456 7890",
        "whatsapp": "+57 312 456 7890",
        "email": "contacto@sandiavetcare.com",
        "doctora_nombre": "Dra. Daniela Pulido",
        "doctora_titulo": "Médica veterinaria",
        "doctora_tp": "53214",
        "doctora_especialidad": "Dpl. Dermatología de pequeñas especies",
        "doctora_firma": "",
    }
    if db_session:
        try:
            from models import ConfiguracionSistema
            from sqlalchemy import select
            configs = db_session.execute(select(ConfiguracionSistema)).scalars().all()
            for c in configs:
                if c.clave == "clinica_nombre" and c.valor: datos["nombre"] = c.valor
                elif c.clave == "clinica_subtitulo" and c.valor: datos["subtitulo"] = c.valor
                elif c.clave == "clinica_nit" and c.valor: datos["nit"] = c.valor
                elif c.clave == "clinica_direccion" and c.valor: datos["direccion"] = c.valor
                elif c.clave == "clinica_ciudad" and c.valor: datos["ciudad"] = c.valor
                elif c.clave == "clinica_telefono" and c.valor: datos["telefono"] = c.valor
                elif c.clave == "clinica_whatsapp" and c.valor: datos["whatsapp"] = c.valor
                elif c.clave == "clinica_email" and c.valor: datos["email"] = c.valor
                elif c.clave == "medico_principal_nombre" and c.valor: datos["doctora_nombre"] = c.valor
                elif c.clave == "medico_principal_titulo" and c.valor: datos["doctora_titulo"] = c.valor
                elif c.clave == "medico_principal_tp" and c.valor: datos["doctora_tp"] = c.valor
                elif c.clave == "medico_principal_especialidad" and c.valor: datos["doctora_especialidad"] = c.valor
                elif c.clave == "medico_principal_firma" and c.valor: datos["doctora_firma"] = c.valor
        except Exception:
            pass
    return datos


def _obtener_logo_img(width=18*mm, height=17*mm):
    """Retorna el elemento Image de ReportLab para el logo oficial de Sandía Spa si existe."""
    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "img", "dog_icon.png")
    if os.path.exists(logo_path):
        try:
            return RLImage(logo_path, width=width, height=height)
        except Exception:
            return None
    return None


def _obtener_firma_flowable(nombre_o_base64: str, width=46 * mm, height=18 * mm):
    """Retorna un elemento Image de ReportLab para la firma digital si existe."""
    if not nombre_o_base64:
        return None
    try:
        img = None
        if str(nombre_o_base64).startswith("data:image"):
            import base64
            _, b64 = nombre_o_base64.split(",", 1)
            raw = base64.b64decode(b64)
            img = RLImage(io.BytesIO(raw), width=width, height=height)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            rutas = [
                os.path.join(base_dir, "static", "uploads", "firmas", str(nombre_o_base64)),
                os.path.join(base_dir, "static", "uploads", str(nombre_o_base64)),
            ]
            for r in rutas:
                if os.path.exists(r):
                    img = RLImage(r, width=width, height=height)
                    break
        if img:
            img.hAlign = 'CENTER'
        return img
    except Exception:
        pass
    return None


def _obtener_foto_spa_flowable(nombre: str, width=50 * mm, height=45 * mm):
    """Retorna un elemento Image de ReportLab para fotos de spa (ingreso/salida) si existe."""
    if not nombre:
        return None
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        rutas = [
            os.path.join(base_dir, "static", "uploads", "spa", str(nombre)),
            os.path.join(base_dir, "static", "uploads", str(nombre)),
        ]
        for r in rutas:
            if os.path.exists(r):
                return RLImage(r, width=width, height=height)
    except Exception:
        pass
    return None


def _formatear_medicamentos_html(texto: str) -> str:
    """Convierte texto de medicamentos o fórmulas en HTML estilizado para párrafos de ReportLab."""
    if not texto:
        return "Sin medicamentos prescritos."
    lineas = [l.strip() for l in texto.split("\n") if l.strip()]
    html_out = []
    for l in lineas:
        if l.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.", "•", "-")):
            html_out.append(f"<font color='#0F172A' size=9><b>{l}</b></font>")
        elif l.upper().startswith("USO:") or l.upper().startswith("POSOLOGIA:") or l.upper().startswith("DOSIS:") or l.upper().startswith("INDICACIONES:"):
            partes = l.split(":", 1)
            etiqueta = partes[0].strip()
            valor = partes[1].strip() if len(partes) > 1 else ""
            html_out.append(f"&nbsp;&nbsp;<font color='#BE123C' size=8><b>{etiqueta}:</b></font> <font color='#334155' size=8.5>{valor}</font>")
        else:
            html_out.append(f"&nbsp;&nbsp;<font color='#475569' size=8.5>{l}</font>")
    return "<br/>".join(html_out)


def _crear_bloque_firma_medica(vet, clinica, estilos, ancho_bloque=75 * mm):
    """Crea un bloque de firma digital y sello profesional perfectamente alineado y centrado."""
    nombre_vet = vet.nombre if vet else clinica.get("doctora_nombre", "Dra. Daniela Pulido")
    titulo_vet = getattr(vet, "titulo_profesional", None) or clinica.get("doctora_titulo", "Médica veterinaria")
    tp_vet = getattr(vet, "tarjeta_profesional", None) or clinica.get("doctora_tp", "53214")
    esp_vet = getattr(vet, "especialidad", None) or clinica.get("doctora_especialidad", "Dpl. Dermatología de pequeñas especies")
    firma_vet = getattr(vet, "firma_digital", None) or clinica.get("doctora_firma", "")

    firma_img = _obtener_firma_flowable(firma_vet, width=46 * mm, height=18 * mm)

    lineas = [
        f"<b>{nombre_vet}</b>",
        f"<font color='#334155'>{titulo_vet} · T.P. {tp_vet}</font>",
    ]
    if esp_vet:
        lineas.append(f"<font color='#BE123C' size=7><b>{esp_vet}</b></font>")
    lineas.append(f"<font size=6.5 color='#64748B'>{clinica['nombre']} · {clinica['subtitulo']}</font>")

    p_sello = Paragraph("<br/>".join(lineas), estilos['PiePagina'])

    filas = []
    if firma_img:
        filas.append([firma_img])
    else:
        filas.append([Spacer(1, 14 * mm)])
    
    filas.append([p_sello])

    t_sello = Table(filas, colWidths=[ancho_bloque])
    t_sello.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEABOVE', (0, 1), (0, 1), 1, colors.HexColor("#334155")),  # Línea nítida centrada encima del sello
        ('TOPPADDING', (0, 1), (0, 1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))

    t_wrap = Table([["", t_sello]], colWidths=[188 * mm - ancho_bloque, ancho_bloque])
    t_wrap.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'BOTTOM'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return KeepTogether(t_wrap)


def _crear_estilos():
    estilos = getSampleStyleSheet()

    estilos.add(ParagraphStyle(
        'TituloClinica',
        parent=estilos['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=17,
        textColor=COLOR_PRIMARIO,
    ))

    estilos.add(ParagraphStyle(
        'SubtituloClinica',
        parent=estilos['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor("#64748B"),
    ))

    estilos.add(ParagraphStyle(
        'DocumentoFolio',
        parent=estilos['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=13.5,
        textColor=COLOR_OSCURO,
        alignment=2,  # Derecha
    ))

    estilos.add(ParagraphStyle(
        'SeccionHeader',
        parent=estilos['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=12.5,
        textColor=COLOR_OSCURO,
    ))

    estilos.add(ParagraphStyle(
        'SeccionCabecera',
        parent=estilos['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9.5,
        textColor=COLOR_OSCURO,
    ))

    estilos.add(ParagraphStyle(
        'TextoNormal',
        parent=estilos['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12,
        textColor=COLOR_TEXTO,
    ))

    estilos.add(ParagraphStyle(
        'TextoNegrita',
        parent=estilos['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=12,
        textColor=COLOR_OSCURO,
    ))

    estilos.add(ParagraphStyle(
        'TextoReceta',
        parent=estilos['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=12.5,
        textColor=COLOR_OSCURO,
    ))

    estilos.add(ParagraphStyle(
        'TextoPequeno',
        parent=estilos['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=10,
        textColor=COLOR_TEXTO,
    ))

    estilos.add(ParagraphStyle(
        'TextoCentrado',
        parent=estilos['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11.5,
        textColor=COLOR_OSCURO,
        alignment=1,  # Centro
    ))

    estilos.add(ParagraphStyle(
        'PiePagina',
        parent=estilos['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#475569"),
        alignment=1,  # Centro
    ))

    return estilos


def generar_pdf_consulta(consulta, db_session=None) -> io.BytesIO:
    """Genera el Informe Oficial de Consulta Médica SOAP con formato Sandía VetCare."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    
    estilos = _crear_estilos()
    historia = []
    clinica = _obtener_datos_clinica(db_session)
    mascota = consulta.mascota
    tutor = consulta.tutor or (mascota.tutor if mascota else None)
    vet = consulta.veterinario

    # =========================================================================
    # 1. ENCABEZADO DE IDENTIDAD CLÍNICA
    # =========================================================================
    fecha_str = consulta.fecha_hora.strftime("%d/%m/%Y %H:%M") if hasattr(consulta.fecha_hora, "strftime") else str(consulta.fecha_hora)
    
    logo_img = _obtener_logo_img(width=18 * mm, height=17 * mm)
    if logo_img:
        header_data = [
            [
                logo_img,
                Paragraph(f"<b>{clinica['nombre'].upper()}</b><br/><font size=8>{clinica['subtitulo']}</font><br/><font size=7 color='#64748B'>NIT: {clinica['nit']} · Tel: {clinica['telefono']}<br/>{clinica['direccion']} · {clinica['ciudad']}</font>", estilos['TituloClinica']),
                Paragraph(f"<b>INFORME CLÍNICO OFICIAL</b><br/><font color='#E53935' size=10><b>CONSULTA SOAP #{consulta.id:04d}</b></font><br/><font size=8 color='#64748B'>Fecha: {fecha_str}</font>", estilos['DocumentoFolio'])
            ]
        ]
        t_header = Table(header_data, colWidths=[20 * mm, 90 * mm, 78 * mm])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (0,0), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
        ]))
    else:
        header_data = [
            [
                Paragraph(f"<b>{clinica['nombre'].upper()}</b><br/><font size=8>{clinica['subtitulo']}</font><br/><font size=7 color='#64748B'>NIT: {clinica['nit']} · Tel: {clinica['telefono']}<br/>{clinica['direccion']} · {clinica['ciudad']}</font>", estilos['TituloClinica']),
                Paragraph(f"<b>INFORME CLÍNICO OFICIAL</b><br/><font color='#E53935' size=10><b>CONSULTA SOAP #{consulta.id:04d}</b></font><br/><font size=8 color='#64748B'>Fecha: {fecha_str}</font>", estilos['DocumentoFolio'])
            ]
        ]
        t_header = Table(header_data, colWidths=[110 * mm, 78 * mm])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
    historia.append(t_header)
    historia.append(HRFlowable(width="100%", thickness=1.5, color=COLOR_PRIMARIO, spaceAfter=8))

    # =========================================================================
    # 2. CUADRO DE INFORMACIÓN DE PACIENTE, TUTOR Y MÉDICO
    # =========================================================================
    nombre_mascota = mascota.nombre if mascota else "Paciente"
    especie_raza = f"{mascota.especie.capitalize() if mascota else ''} · {mascota.raza.nombre if mascota and mascota.raza else 'Mestizo'}"
    sexo_edad = f"{mascota.sexo.capitalize() if mascota and mascota.sexo else 'N/R'} · {mascota.edad_formateada if mascota and hasattr(mascota, 'edad_formateada') else 'N/R'}"
    microchip = f"Microchip: {mascota.microchip}" if mascota and mascota.microchip else ""
    nombre_tutor = tutor.nombre_completo if tutor else "N/A"
    tel_tutor = tutor.telefono or (tutor.whatsapp or "N/A") if tutor else "N/A"
    doc_tutor = f"Doc: {tutor.documento_texto}" if tutor and hasattr(tutor, "documento_texto") else ""
    nombre_vet = vet.nombre if vet else clinica.get("doctora_nombre", "Dra. Daniela Pulido")
    titulo_vet = getattr(vet, "titulo_profesional", None) or clinica.get("doctora_titulo", "Médica veterinaria")
    tp_vet = getattr(vet, "tarjeta_profesional", None) or clinica.get("doctora_tp", "53214")
    esp_vet = getattr(vet, "especialidad", None) or clinica.get("doctora_especialidad", "Dpl. Dermatología de pequeñas especies")
    firma_vet = getattr(vet, "firma_digital", None) or clinica.get("doctora_firma", "")

    info_data = [
        [
            Paragraph(f"<b>PACIENTE:</b> <font color='#E53935'><b>{nombre_mascota}</b></font>", estilos['TextoNormal']),
            Paragraph(f"<b>TUTOR:</b> <b>{nombre_tutor}</b>", estilos['TextoNormal']),
        ],
        [
            Paragraph(f"<b>Especie/Raza:</b> {especie_raza}", estilos['TextoNormal']),
            Paragraph(f"<b>Contacto:</b> {tel_tutor} {doc_tutor}", estilos['TextoNormal']),
        ],
        [
            Paragraph(f"<b>Sexo/Edad:</b> {sexo_edad} {microchip}", estilos['TextoNormal']),
            Paragraph(f"<b>Médico Tratante:</b> {nombre_vet}", estilos['TextoNormal']),
        ]
    ]
    t_info = Table(info_data, colWidths=[94 * mm, 94 * mm])
    t_info.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), COLOR_GRIS_FONDO),
        ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
        ('INNERGRID', (0,0), (-1,-1), 0.5, COLOR_GRIS_BORDE),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    historia.append(t_info)
    historia.append(Spacer(1, 8))

    # =========================================================================
    # 3. SECCIÓN S: SUBJETIVO (Motivo & Anamnesis)
    # =========================================================================
    historia.append(Paragraph("<b>S · SUBJETIVO (Motivo de Consulta & Anamnesis)</b>", estilos['SeccionHeader']))
    historia.append(Spacer(1, 2))
    
    anamnesis_texto = consulta.anamnesis or "Sin antecedentes previos reportados por el tutor."
    subjetivo_data = [
        [Paragraph(f"<b>Motivo de Consulta:</b> {consulta.motivo_consulta}", estilos['TextoNormal'])],
        [Paragraph(f"<b>Anamnesis / Historia Previa:</b> {anamnesis_texto}", estilos['TextoNormal'])],
    ]

    preventivo_items = []
    if consulta.alimentacion:
        preventivo_items.append(f"<b>Dieta/Alimentación:</b> {consulta.alimentacion}")
    if consulta.desparasitacion_producto or consulta.desparasitacion_fecha:
        f_desp = consulta.desparasitacion_fecha.strftime("%d/%m/%Y") if consulta.desparasitacion_fecha else ""
        preventivo_items.append(f"<b>Última Desparasitación:</b> {consulta.desparasitacion_producto or ''} {'(' + f_desp + ')' if f_desp else ''}".strip())
    if consulta.vacunacion_producto or consulta.vacunacion_fecha:
        f_vac = consulta.vacunacion_fecha.strftime("%d/%m/%Y") if consulta.vacunacion_fecha else ""
        preventivo_items.append(f"<b>Última Vacuna:</b> {consulta.vacunacion_producto or ''} {'(' + f_vac + ')' if f_vac else ''}".strip())
    
    if preventivo_items:
        subjetivo_data.append([Paragraph(" · ".join(preventivo_items), estilos['TextoPequeno'])])

    t_subjetivo = Table(subjetivo_data, colWidths=[188 * mm])
    t_subjetivo.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F0F9FF")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#BAE6FD")),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    historia.append(t_subjetivo)
    historia.append(Spacer(1, 8))

    # =========================================================================
    # 4. SECCIÓN O: OBJETIVO (Constantes Vitales + Examen por Sistemas)
    # =========================================================================
    historia.append(Paragraph("<b>O · OBJETIVO (Constantes Fisiológicas & Examen Físico)</b>", estilos['SeccionHeader']))
    historia.append(Spacer(1, 2))

    # Constantes vitales en barra horizontal
    v_peso = f"{consulta.peso_kg} kg" if consulta.peso_kg else "—"
    v_temp = f"{consulta.temperatura_c} °C" if consulta.temperatura_c else "—"
    v_fc = f"{consulta.frecuencia_cardiaca} lpm" if consulta.frecuencia_cardiaca else "—"
    if consulta.frecuencia_respiratoria:
        fr_str = str(consulta.frecuencia_respiratoria).strip()
        v_fr = f"{fr_str} rpm" if fr_str.isdigit() else fr_str
    else:
        v_fr = "—"
    v_tllc = f"{consulta.tllc_segundos} seg" if consulta.tllc_segundos else "—"
    v_muc = f"{consulta.mucosas.capitalize()}" if consulta.mucosas else "—"
    v_cc = f"{consulta.condicion_corporal}" if consulta.condicion_corporal else "—"

    vitales_data = [
        ["Peso", "Temp", "FC", "FR", "TLLC", "Mucosas", "Cond. Corp."],
        [v_peso, v_temp, v_fc, v_fr, v_tllc, v_muc, v_cc]
    ]
    t_vitales = Table(vitales_data, colWidths=[26 * mm, 26 * mm, 26 * mm, 26 * mm, 26 * mm, 30 * mm, 28 * mm])
    t_vitales.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), COLOR_OSCURO),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 7.5),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('BACKGROUND', (0,1), (-1,1), COLOR_GRIS_FONDO),
        ('FONTNAME', (0,1), (-1,1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,1), (-1,1), 8),
        ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
        ('INNERGRID', (0,0), (-1,-1), 0.5, COLOR_GRIS_BORDE),
        ('PADDING', (0,0), (-1,-1), 3),
    ]))
    historia.append(t_vitales)
    historia.append(Spacer(1, 4))

    # Examen por Sistemas (9 Sistemas)
    sistemas = consulta.sistemas_evaluados
    if sistemas and isinstance(sistemas, dict):
        sist_rows = [["Sistema Evaluado", "Estado", "Hallazgos / Observaciones Clínicas"]]
        for k, v in sistemas.items():
            if isinstance(v, dict):
                nom = v.get("nombre") or str(k).replace("_", " ").capitalize()
                est = str(v.get("estado", "normal")).upper()
                obs = v.get("observacion") or "Sin alteraciones aparentes."
            else:
                nom = str(k).replace("_", " ").capitalize()
                est = str(v).upper() if v else "NORMAL"
                obs = "Sin alteraciones aparentes."
            color_est = "<font color='#166534'><b>NORMAL</b></font>" if est == "NORMAL" else "<font color='#B91C1C'><b>ANORMAL</b></font>"
            sist_rows.append([
                Paragraph(f"<b>{nom}</b>", estilos['TextoNormal']),
                Paragraph(color_est, estilos['TextoNormal']),
                Paragraph(obs, estilos['TextoNormal'])
            ])
        
        t_sistemas = Table(sist_rows, colWidths=[48 * mm, 26 * mm, 114 * mm])
        t_sistemas.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#E2E8F0")),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 7.5),
            ('BOX', (0,0), (-1,-1), 0.5, COLOR_GRIS_BORDE),
            ('INNERGRID', (0,0), (-1,-1), 0.5, COLOR_GRIS_BORDE),
            ('PADDING', (0,0), (-1,-1), 2.5),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        historia.append(t_sistemas)
    elif consulta.examen_sistemas:
        historia.append(Paragraph(f"<b>Hallazgos por sistemas:</b> {consulta.examen_sistemas}", estilos['TextoNormal']))
    
    historia.append(Spacer(1, 8))

    # =========================================================================
    # 5. SECCIÓN A: AVALÚO (Diagnóstico)
    # =========================================================================
    historia.append(Paragraph("<b>A · AVALÚO (Diagnóstico Presuntivo)</b>", estilos['SeccionHeader']))
    historia.append(Spacer(1, 2))
    diag_txt = consulta.diagnostico or "Sin diagnóstico presuntivo registrado."
    diag_data = [[Paragraph(f"<b>DIAGNÓSTICO:</b> {diag_txt}", estilos['TextoNormal'])]]
    t_diag = Table(diag_data, colWidths=[188 * mm])
    t_diag.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FEF3C7")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#FCD34D")),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    historia.append(t_diag)
    historia.append(Spacer(1, 8))

    # =========================================================================
    # 6. SECCIÓN P: PLAN & FÓRMULA MÉDICA (Rx)
    # =========================================================================
    historia.append(Paragraph("<b>P · PLAN TERAPÉUTICO & PRESCRIPCIÓN MÉDICA</b>", estilos['SeccionHeader']))
    historia.append(Spacer(1, 2))
    
    plan_txt = (consulta.plan_tratamiento or "Sin plan de tratamiento registrado.").replace("\n", "<br/>")
    plan_data = [
        [Paragraph(f"<b>Indicaciones Clínicas & Procedimientos:</b><br/>{plan_txt}", estilos['TextoNormal'])]
    ]
    t_plan = Table(plan_data, colWidths=[188 * mm])
    t_plan.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), COLOR_GRIS_FONDO),
        ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    historia.append(t_plan)
    historia.append(Spacer(1, 6))

    # Receta Médica formal si existe
    if consulta.receta_medica:
        receta_txt = consulta.receta_medica.replace("\n", "<br/>")
        receta_data = [
            [
                Paragraph("<b><font color='#E53935' size=11>Rx</font> FÓRMULA MÉDICA & PRESCRIPCIÓN AL TUTOR</b>", estilos['TextoNegrita'])
            ],
            [
                Paragraph(receta_txt, estilos['TextoReceta'])
            ]
        ]
        t_receta = Table(receta_data, colWidths=[188 * mm])
        t_receta.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#FEE2E2")),
            ('BACKGROUND', (0,1), (-1,1), colors.HexColor("#FFF1F2")),
            ('BOX', (0,0), (-1,-1), 1.5, COLOR_PRIMARIO),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#FECACA")),
            ('PADDING', (0,0), (-1,-1), 5),
        ]))
        historia.append(t_receta)
        historia.append(Spacer(1, 6))

    if consulta.observaciones:
        historia.append(Paragraph(f"<b>Observaciones / Próximo Recontrol:</b> {consulta.observaciones}", estilos['TextoNormal']))
        historia.append(Spacer(1, 6))

    # =========================================================================
    # 7. FIRMA MÉDICA & PIE DE PÁGINA
    # =========================================================================
    historia.append(Spacer(1, 10))
    historia.append(_crear_bloque_firma_medica(vet, clinica, estilos, ancho_bloque=75 * mm))

    # Construir PDF
    doc.build(historia)
    buffer.seek(0)
    return buffer


def generar_pdf_factura(venta, db_session=None) -> io.BytesIO:
    """Genera la Factura / Comprobante de Venta Oficial de Sandía VetCare en PDF."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )
    
    estilos = _crear_estilos()
    historia = []
    clinica = _obtener_datos_clinica(db_session)
    tutor = venta.tutor
    usuario_vendedor = venta.usuario

    fecha_dt = venta.fecha_venta if hasattr(venta, 'fecha_venta') and venta.fecha_venta else datetime.now()
    fecha_str = fecha_dt.strftime("%d/%m/%Y %H:%M") if hasattr(fecha_dt, "strftime") else str(fecha_dt)

    # 1. Header
    logo_img = _obtener_logo_img(width=18 * mm, height=17 * mm)
    if logo_img:
        header_data = [
            [
                logo_img,
                Paragraph(f"<b>{clinica['nombre'].upper()}</b><br/><font size=8>{clinica['subtitulo']}</font><br/><font size=7 color='#64748B'>NIT: {clinica['nit']} · Tel: {clinica['telefono']}<br/>{clinica['direccion']} · {clinica['ciudad']}</font>", estilos['TituloClinica']),
                Paragraph(f"<b>COMPROBANTE DE PAGO</b><br/><font color='#E53935' size=11><b>{venta.numero_factura}</b></font><br/><font size=8 color='#64748B'>Fecha: {fecha_str}</font>", estilos['DocumentoFolio'])
            ]
        ]
        t_header = Table(header_data, colWidths=[20 * mm, 90 * mm, 78 * mm])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (0,0), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
        ]))
    else:
        header_data = [
            [
                Paragraph(f"<b>{clinica['nombre'].upper()}</b><br/><font size=8>{clinica['subtitulo']}</font><br/><font size=7 color='#64748B'>NIT: {clinica['nit']} · Tel: {clinica['telefono']}<br/>{clinica['direccion']} · {clinica['ciudad']}</font>", estilos['TituloClinica']),
                Paragraph(f"<b>COMPROBANTE DE PAGO</b><br/><font color='#E53935' size=11><b>{venta.numero_factura}</b></font><br/><font size=8 color='#64748B'>Fecha: {fecha_str}</font>", estilos['DocumentoFolio'])
            ]
        ]
        t_header = Table(header_data, colWidths=[110 * mm, 78 * mm])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
    historia.append(t_header)
    historia.append(HRFlowable(width="100%", thickness=1.5, color=COLOR_PRIMARIO, spaceAfter=8))

    # 2. Cliente y Vendedor
    cliente_nom = tutor.nombre_completo if tutor else "Cliente General / Consumidor Final"
    cliente_doc = f"NIT/CC: {tutor.documento_texto}" if tutor and hasattr(tutor, "documento_texto") and tutor.documento_texto else "NIT/CC: 222222222222"
    cliente_tel = f"Tel: {tutor.telefono}" if tutor and tutor.telefono else ""
    cajero_nom = usuario_vendedor.nombre if usuario_vendedor else "Caja Principal"
    mascota_nom = f" · Mascota: <strong>{venta.mascota.nombre}</strong>" if getattr(venta, "mascota", None) and venta.mascota.nombre else ""
    estado_venta = str(getattr(venta, "estado", "PAGADO")).upper()

    info_data = [
        [
            Paragraph(f"<b>CLIENTE:</b> {cliente_nom}{mascota_nom}", estilos['TextoNormal']),
            Paragraph(f"<b>ATENDIDO POR:</b> {cajero_nom}", estilos['TextoNormal']),
        ],
        [
            Paragraph(f"<b>Documento:</b> {cliente_doc} · {cliente_tel}", estilos['TextoNormal']),
            Paragraph(f"<b>Estado:</b> <font color='#166534'><b>{estado_venta}</b></font>", estilos['TextoNormal']),
        ]
    ]
    t_info = Table(info_data, colWidths=[100 * mm, 88 * mm])
    t_info.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), COLOR_GRIS_FONDO),
        ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    historia.append(t_info)
    historia.append(Spacer(1, 10))

    # 3. Detalle de Ítems
    items_table = [["Cant", "Descripción / Producto o Servicio", "V. Unitario", "Desc.", "Total"]]
    detalles_lista = getattr(venta, 'detalles', []) or []
    for item in detalles_lista:
        desc = getattr(item, 'descripcion', 'Ítem') or 'Ítem'
        cant_val = getattr(item, "cantidad", 1)
        cant = f"{cant_val:g}" if isinstance(cant_val, (int, float)) else str(cant_val or 1)
        p_unit = getattr(item, 'precio_unitario', 0) or 0
        unit = f"${p_unit:,.2f}"
        desc_val = getattr(item, "descuento", 0) or 0
        desc_txt = f"-${desc_val:,.2f}" if desc_val else "$0.00"
        t_linea = getattr(item, 'total_linea', 0) or 0
        total_it = f"${t_linea:,.2f}"
        items_table.append([cant, Paragraph(desc, estilos['TextoNormal']), unit, desc_txt, total_it])

    if len(items_table) == 1:
        items_table.append(["1", Paragraph("Venta general", estilos['TextoNormal']), f"${getattr(venta, 'total', 0) or 0:,.2f}", "$0.00", f"${getattr(venta, 'total', 0) or 0:,.2f}"])

    t_items = Table(items_table, colWidths=[16 * mm, 98 * mm, 26 * mm, 18 * mm, 30 * mm])
    t_items.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), COLOR_OSCURO),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 8),
        ('ALIGN', (0,0), (0,-1), 'CENTER'),
        ('ALIGN', (2,0), (-1,-1), 'RIGHT'),
        ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
        ('INNERGRID', (0,0), (-1,-1), 0.5, COLOR_GRIS_BORDE),
        ('PADDING', (0,0), (-1,-1), 4),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    historia.append(t_items)
    historia.append(Spacer(1, 8))

    # 4. Totales
    subt_val = getattr(venta, "subtotal", None)
    tot_val = getattr(venta, "total", 0) or 0
    desc_monto = getattr(venta, "descuento_monto", 0) or 0
    imp_monto = getattr(venta, "impuesto_monto", 0) or 0

    subtotal_str = f"${subt_val:,.2f}" if subt_val is not None else f"${tot_val:,.2f}"
    descuento_str = f"-${desc_monto:,.2f}" if desc_monto else "$0.00"
    iva_str = f"${imp_monto:,.2f}" if imp_monto else "$0.00"
    total_str = f"${tot_val:,.2f}"

    totales_data = [
        ["Subtotal:", subtotal_str],
        ["Descuento:", descuento_str],
        ["Impuesto / IVA:", iva_str],
        ["TOTAL PAGADO:", total_str],
    ]
    t_totales = Table(totales_data, colWidths=[40 * mm, 36 * mm])
    t_totales.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
        ('FONTNAME', (0,0), (-1,-2), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-2), 8.5),
        ('FONTNAME', (0,-1), (-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,-1), (-1,-1), 10.5),
        ('TEXTCOLOR', (0,-1), (-1,-1), COLOR_PRIMARIO),
        ('PADDING', (0,0), (-1,-1), 2.5),
    ]))
    
    t_totales_wrap = Table([["", t_totales]], colWidths=[112 * mm, 76 * mm])
    t_totales_wrap.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    historia.append(t_totales_wrap)
    historia.append(Spacer(1, 14))

    # 5. Formas de Pago
    pagos_lista = getattr(venta, 'pagos', []) or []
    pagos_str = ", ".join([f"{getattr(p, 'metodo_etiqueta', 'Pago')}: ${getattr(p, 'monto', 0) or 0:,.2f}" for p in pagos_lista]) if pagos_lista else "Pago registrado"
    historia.append(Paragraph(f"<b>Medio(s) de Pago:</b> {pagos_str}", estilos['TextoNormal']))
    historia.append(Spacer(1, 6))
    historia.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_GRIS_BORDE, spaceAfter=8))
    historia.append(Paragraph("¡Gracias por confiar en Sandía Medicina & Spa Veterinario! 🐾🍉", estilos['PiePagina']))

    doc.build(historia)
    buffer.seek(0)
    return buffer


def generar_pdf_receta(consulta, db_session=None) -> io.BytesIO:
    """Genera exclusivamente la Fórmula Médica / Recetario Oficial (Rx)."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    
    estilos = _crear_estilos()
    historia = []
    clinica = _obtener_datos_clinica(db_session)
    mascota = consulta.mascota
    tutor = consulta.tutor or (mascota.tutor if mascota else None)
    vet = consulta.veterinario

    fecha_str = consulta.fecha_hora.strftime("%d/%m/%Y") if hasattr(consulta.fecha_hora, "strftime") else str(consulta.fecha_hora)

    # 1. Header Recetario
    logo_img = _obtener_logo_img(width=18 * mm, height=17 * mm)
    if logo_img:
        header_data = [
            [
                logo_img,
                Paragraph(f"<b>{clinica['nombre'].upper()}</b><br/><font size=8>{clinica['subtitulo']}</font><br/><font size=7 color='#64748B'>NIT: {clinica['nit']} · Tel: {clinica['telefono']}<br/>{clinica['direccion']} · {clinica['ciudad']}</font>", estilos['TituloClinica']),
                Paragraph(f"<b>RECETARIO MÉDICO</b><br/><font color='#E53935' size=10><b>FÓRMULA #{consulta.id:04d}</b></font><br/><font size=8 color='#64748B'>Fecha: {fecha_str}</font>", estilos['DocumentoFolio'])
            ]
        ]
        t_header = Table(header_data, colWidths=[20 * mm, 90 * mm, 74 * mm])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (0,0), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
        ]))
    else:
        header_data = [
            [
                Paragraph(f"<b>{clinica['nombre'].upper()}</b><br/><font size=8>{clinica['subtitulo']}</font><br/><font size=7 color='#64748B'>NIT: {clinica['nit']} · Tel: {clinica['telefono']}<br/>{clinica['direccion']} · {clinica['ciudad']}</font>", estilos['TituloClinica']),
                Paragraph(f"<b>RECETARIO MÉDICO</b><br/><font color='#E53935' size=10><b>FÓRMULA #{consulta.id:04d}</b></font><br/><font size=8 color='#64748B'>Fecha: {fecha_str}</font>", estilos['DocumentoFolio'])
            ]
        ]
        t_header = Table(header_data, colWidths=[110 * mm, 74 * mm])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
    historia.append(t_header)
    historia.append(HRFlowable(width="100%", thickness=1.5, color=COLOR_PRIMARIO, spaceAfter=8))

    # 2. Datos Paciente y Tutor
    nombre_mascota = mascota.nombre if mascota else "Paciente"
    especie_raza = f"{mascota.especie.capitalize() if mascota else ''} · {mascota.raza.nombre if mascota and mascota.raza else 'Mestizo'}"
    peso_str = f"Peso: {consulta.peso_kg} kg" if consulta.peso_kg else ""
    nombre_tutor = tutor.nombre_completo if tutor else "N/A"
    nombre_vet = vet.nombre if vet else clinica.get("doctora_nombre", "Dra. Daniela Pulido")
    titulo_vet = getattr(vet, "titulo_profesional", None) or clinica.get("doctora_titulo", "Médica veterinaria")
    tp_vet = getattr(vet, "tarjeta_profesional", None) or clinica.get("doctora_tp", "53214")
    esp_vet = getattr(vet, "especialidad", None) or clinica.get("doctora_especialidad", "Dpl. Dermatología de pequeñas especies")
    firma_vet = getattr(vet, "firma_digital", None) or clinica.get("doctora_firma", "")

    info_data = [
        [
            Paragraph(f"<b>PACIENTE:</b> <font color='#E53935'><b>{nombre_mascota}</b></font> ({especie_raza}) · {peso_str}", estilos['TextoNormal']),
            Paragraph(f"<b>TUTOR:</b> <b>{nombre_tutor}</b>", estilos['TextoNormal']),
        ],
        [
            Paragraph(f"<b>Diagnóstico:</b> {consulta.diagnostico or 'Evaluación médica'}", estilos['TextoNormal']),
            Paragraph(f"<b>Médico:</b> {nombre_vet}", estilos['TextoNormal']),
        ]
    ]
    t_info = Table(info_data, colWidths=[92 * mm, 92 * mm])
    t_info.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), COLOR_GRIS_FONDO),
        ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    historia.append(t_info)
    historia.append(Spacer(1, 12))

    # 3. Prescripción Rx
    receta_txt = (consulta.receta_medica or consulta.plan_tratamiento or "Sin medicamentos prescritos.").replace("\n", "<br/>")
    receta_data = [
        [
            Paragraph("<b><font color='#E53935' size=14>Rx</font> MEDICAMENTOS, DOSIS & INSTRUCCIONES DE USO</b>", estilos['TextoNegrita'])
        ],
        [
            Paragraph(receta_txt, estilos['TextoReceta'])
        ]
    ]
    t_receta = Table(receta_data, colWidths=[184 * mm])
    t_receta.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#FEE2E2")),
        ('BACKGROUND', (0,1), (-1,1), colors.HexColor("#FFFFFF")),
        ('BOX', (0,0), (-1,-1), 1.5, COLOR_PRIMARIO),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#FECACA")),
        ('PADDING', (0,0), (-1,-1), 8),
    ]))
    historia.append(t_receta)
    historia.append(Spacer(1, 10))

    if consulta.observaciones:
        historia.append(Paragraph(f"<b>Recomendaciones de cuidado / Recontrol:</b> {consulta.observaciones}", estilos['TextoNormal']))
        historia.append(Spacer(1, 10))

    # 4. Firma
    historia.append(Spacer(1, 12))
    historia.append(_crear_bloque_firma_medica(vet, clinica, estilos, ancho_bloque=75 * mm))

    doc.build(historia)
    buffer.seek(0)
    return buffer


def generar_pdf_spa(cita_spa, db_session=None) -> io.BytesIO:
    """Genera el Reporte Oficial de Atención de Spa & Peluquería Canina/Felina."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    
    estilos = _crear_estilos()
    historia = []
    clinica = _obtener_datos_clinica(db_session)
    mascota = cita_spa.mascota
    tutor = cita_spa.tutor or (mascota.tutor if mascota else None)
    groomer = cita_spa.groomer

    fecha_str = cita_spa.fecha_hora.strftime("%d/%m/%Y %H:%M") if hasattr(cita_spa.fecha_hora, "strftime") else str(cita_spa.fecha_hora)

    # 1. Header
    logo_img = _obtener_logo_img(width=18 * mm, height=17 * mm)
    if logo_img:
        header_data = [
            [
                logo_img,
                Paragraph(f"<b>{clinica['nombre'].upper()}</b><br/><font size=8>{clinica['subtitulo']}</font><br/><font size=7 color='#64748B'>NIT: {clinica['nit']} · Tel: {clinica['telefono']}<br/>{clinica['direccion']} · {clinica['ciudad']}</font>", estilos['TituloClinica']),
                Paragraph(f"<b>CERTIFICADO DE SPA & GROOMING</b><br/><font color='#E53935' size=10><b>SERVICIO #{cita_spa.id:04d}</b></font><br/><font size=8 color='#64748B'>Fecha: {fecha_str}</font>", estilos['DocumentoFolio'])
            ]
        ]
        t_header = Table(header_data, colWidths=[20 * mm, 90 * mm, 74 * mm])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (0,0), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
        ]))
    else:
        header_data = [
            [
                Paragraph(f"<b>{clinica['nombre'].upper()}</b><br/><font size=8>{clinica['subtitulo']}</font><br/><font size=7 color='#64748B'>NIT: {clinica['nit']} · Tel: {clinica['telefono']}<br/>{clinica['direccion']} · {clinica['ciudad']}</font>", estilos['TituloClinica']),
                Paragraph(f"<b>CERTIFICADO DE SPA & GROOMING</b><br/><font color='#E53935' size=10><b>SERVICIO #{cita_spa.id:04d}</b></font><br/><font size=8 color='#64748B'>Fecha: {fecha_str}</font>", estilos['DocumentoFolio'])
            ]
        ]
        t_header = Table(header_data, colWidths=[110 * mm, 74 * mm])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ]))
    historia.append(t_header)
    historia.append(HRFlowable(width="100%", thickness=1.5, color=COLOR_PRIMARIO, spaceAfter=8))

    # 2. Paciente y Servicio
    nombre_mascota = mascota.nombre if mascota else "Paciente"
    especie_raza = f"{mascota.especie.capitalize() if mascota else ''} · {mascota.raza.nombre if mascota and mascota.raza else 'Mestizo'}"
    servicio_nom = cita_spa.servicio_spa.nombre if cita_spa.servicio_spa else "Servicio de Peluquería / Baño"
    if hasattr(cita_spa, "lista_adicionales") and cita_spa.lista_adicionales:
        adic_text = ", ".join([f"{a['nombre']} (${float(a.get('precio', 0)):,.0f})" for a in cita_spa.lista_adicionales])
        servicio_nom += f"<br/><font size=7 color='#64748B'>+ Adicionales: {adic_text}</font>"
    groomer_nom = groomer.nombre if groomer else "Estilista Canino/Felino"

    info_data = [
        [
            Paragraph(f"<b>PACIENTE:</b> <font color='#E53935'><b>{nombre_mascota}</b></font> ({especie_raza})", estilos['TextoNormal']),
            Paragraph(f"<b>TUTOR:</b> <b>{tutor.nombre_completo if tutor else 'N/A'}</b>", estilos['TextoNormal']),
        ],
        [
            Paragraph(f"<b>Servicio Realizado:</b> <b>{servicio_nom}</b>", estilos['TextoNormal']),
            Paragraph(f"<b>Estilista a Cargo:</b> {groomer_nom}", estilos['TextoNormal']),
        ],
        [
            Paragraph(f"<b>Estado del Servicio:</b> <font color='#166534'><b>{cita_spa.estado.upper()}</b></font>", estilos['TextoNormal']),
            Paragraph(f"<b>Fecha de Listo:</b> {cita_spa.fecha_listo.strftime('%d/%m/%Y %H:%M') if cita_spa.fecha_listo else 'Completado'}", estilos['TextoNormal']),
        ]
    ]
    t_info = Table(info_data, colWidths=[92 * mm, 92 * mm])
    t_info.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), COLOR_GRIS_FONDO),
        ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    historia.append(t_info)
    historia.append(Spacer(1, 10))

    # 3. Observaciones de Ingreso y Entrega
    if cita_spa.notas_ingreso:
        t_ingreso = Table(
            [
                [Paragraph("<b>OBSERVACIONES DE INGRESO / PEDIDO DEL TUTOR:</b>", estilos['TextoNegrita'])],
                [Paragraph(cita_spa.notas_ingreso.replace("\n", "<br/>"), estilos['TextoNormal'])]
            ],
            colWidths=[184 * mm]
        )
        t_ingreso.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), COLOR_GRIS_FONDO),
            ('BACKGROUND', (0,1), (-1,1), colors.white),
            ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
            ('INNERGRID', (0,0), (-1,-1), 0.5, COLOR_GRIS_BORDE),
            ('PADDING', (0,0), (-1,-1), 5),
        ]))
        historia.append(t_ingreso)
        historia.append(Spacer(1, 8))

    if cita_spa.notas_salida:
        t_salida = Table(
            [
                [Paragraph("<b>OBSERVACIONES DE ENTREGA / RECOMENDACIONES DEL ESTILISTA:</b>", estilos['TextoNegrita'])],
                [Paragraph(cita_spa.notas_salida.replace("\n", "<br/>"), estilos['TextoNormal'])]
            ],
            colWidths=[184 * mm]
        )
        t_salida.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#ECFDF5")),
            ('BACKGROUND', (0,1), (-1,1), colors.white),
            ('BOX', (0,0), (-1,-1), 1.2, colors.HexColor("#10B981")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#A7F3D0")),
            ('PADDING', (0,0), (-1,-1), 5),
        ]))
        historia.append(t_salida)
        historia.append(Spacer(1, 8))

    # 4. Fotos de la sesión (Antes / Después) si existen
    foto_in = _obtener_foto_spa_flowable(cita_spa.foto_ingreso, width=65 * mm, height=55 * mm)
    foto_out = _obtener_foto_spa_flowable(cita_spa.foto_salida, width=65 * mm, height=55 * mm)
    if foto_in or foto_out:
        if foto_in and foto_out:
            fotos_data = [
                [
                    Paragraph("<b>FOTO DE INGRESO (ANTES)</b>", estilos['TextoCentrado']),
                    Paragraph("<b>FOTO DE SALIDA (DESPUÉS)</b>", estilos['TextoCentrado'])
                ],
                [foto_in, foto_out]
            ]
            t_fotos = Table(fotos_data, colWidths=[92 * mm, 92 * mm])
        elif foto_in:
            fotos_data = [
                [Paragraph("<b>FOTO DE INGRESO (ANTES)</b>", estilos['TextoCentrado'])],
                [foto_in]
            ]
            t_fotos = Table(fotos_data, colWidths=[184 * mm])
        else:
            fotos_data = [
                [Paragraph("<b>FOTO DE SALIDA (DESPUÉS)</b>", estilos['TextoCentrado'])],
                [foto_out]
            ]
            t_fotos = Table(fotos_data, colWidths=[184 * mm])

        t_fotos.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BACKGROUND', (0,0), (-1,0), COLOR_GRIS_FONDO),
            ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
            ('INNERGRID', (0,0), (-1,-1), 0.5, COLOR_GRIS_BORDE),
            ('PADDING', (0,0), (-1,-1), 5),
        ]))
        historia.append(t_fotos)
        historia.append(Spacer(1, 10))

    historia.append(Spacer(1, 12))
    historia.append(Paragraph("¡Tu consentido quedó listo y hermoso para volver a casa! 🐾✂️🧼", estilos['PiePagina']))

    doc.build(historia)
    buffer.seek(0)
    return buffer


def generar_pdf_certificado_salud(cert, db_session=None) -> io.BytesIO:
    """Genera el Certificado Nacional de Salud Animal / Aptitud de Viaje oficial."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    estilos = _crear_estilos()
    historia = []
    clinica = _obtener_datos_clinica(db_session)
    mascota = cert.mascota
    tutor = cert.tutor or (mascota.tutor if mascota else None)
    vet = cert.veterinario

    fecha_emision_str = cert.fecha_emision.strftime("%d/%m/%Y %I:%M %p") if hasattr(cert.fecha_emision, "strftime") else str(cert.fecha_emision)
    fecha_venc_str = cert.fecha_vencimiento.strftime("%d/%m/%Y") if hasattr(cert.fecha_vencimiento, "strftime") else str(cert.fecha_vencimiento)

    # 1. Cabecera Institucional
    logo_img = _obtener_logo_img(width=18 * mm, height=17 * mm)
    if logo_img:
        header_data = [
            [
                logo_img,
                Paragraph(
                    f"<b>{clinica['nombre'].upper()}</b><br/>"
                    f"<font size=8>{clinica['subtitulo']}</font><br/>"
                    f"<font size=7 color='#64748B'>NIT: {clinica['nit']} · Tel: {clinica['telefono']}<br/>"
                    f"{clinica['direccion']} · {clinica['ciudad']}</font>",
                    estilos['TituloClinica']
                ),
                Paragraph(
                    f"<b>REPÚBLICA DE COLOMBIA</b><br/>"
                    f"<font color='#B71C1C' size=9><b>CERTIFICADO DE SALUD ANIMAL</b></font><br/>"
                    f"<font color='#E53935' size=10><b>No. {cert.consecutivo}</b></font><br/>"
                    f"<font size=7 color='#64748B'>Emisión: {fecha_emision_str}<br/><b>Válido hasta: {fecha_venc_str}</b></font>",
                    estilos['DocumentoFolio']
                )
            ]
        ]
        t_header = Table(header_data, colWidths=[20 * mm, 92 * mm, 76 * mm])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('RIGHTPADDING', (0,0), (0,0), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
        ]))
    else:
        header_data = [
            [
                Paragraph(
                    f"<b>{clinica['nombre'].upper()}</b><br/>"
                    f"<font size=8>{clinica['subtitulo']}</font><br/>"
                    f"<font size=7 color='#64748B'>NIT: {clinica['nit']} · Tel: {clinica['telefono']}<br/>"
                    f"{clinica['direccion']} · {clinica['ciudad']}</font>",
                    estilos['TituloClinica']
                ),
                Paragraph(
                    f"<b>REPÚBLICA DE COLOMBIA</b><br/>"
                    f"<font color='#B71C1C' size=9><b>CERTIFICADO DE SALUD ANIMAL</b></font><br/>"
                    f"<font color='#E53935' size=10><b>No. {cert.consecutivo}</b></font><br/>"
                    f"<font size=7 color='#64748B'>Emisión: {fecha_emision_str}<br/><b>Válido hasta: {fecha_venc_str}</b></font>",
                    estilos['DocumentoFolio']
                )
            ]
        ]
        t_header = Table(header_data, colWidths=[112 * mm, 76 * mm])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
    historia.append(t_header)
    historia.append(HRFlowable(width="100%", thickness=2, color=COLOR_PRIMARIO, spaceAfter=8))

    # 2. Datos del Tutor y del Paciente
    nombre_tutor = tutor.nombre_completo if tutor else "Propietario / Tutor"
    doc_tutor = (tutor.documento_texto if hasattr(tutor, "documento_texto") and tutor.documento_texto else (tutor.numero_documento if tutor else "N/A")) or "N/A"
    dir_tutor = (tutor.direccion if tutor and tutor.direccion else None) or f"{clinica['ciudad']}"
    tel_tutor = (tutor.whatsapp_efectivo or tutor.telefono if tutor else None) or "N/A"

    nombre_mascota = mascota.nombre if mascota else "Paciente"
    especie_txt = mascota.especie_etiqueta if hasattr(mascota, "especie_etiqueta") else (mascota.especie.capitalize() if mascota else "Canino/Felino")
    raza_txt = mascota.raza.nombre if (mascota and mascota.raza) else "Mestizo"
    sexo_txt = mascota.sexo_etiqueta if hasattr(mascota, "sexo_etiqueta") else (mascota.sexo if mascota else "Macho/Hembra")
    edad_txt = mascota.edad if hasattr(mascota, "edad") and mascota.edad else "No determinada"
    color_txt = (mascota.color if mascota else None) or "No registrado"
    microchip_txt = (mascota.microchip if mascota else None) or "Sin microchip"

    info_sujetos = [
        [
            Paragraph("<b>I. DATOS DEL PROPIETARIO / TUTOR RESPONSABLE</b>", estilos['SeccionCabecera']),
            Paragraph("<b>II. IDENTIFICACIÓN DEL PACIENTE</b>", estilos['SeccionCabecera']),
        ],
        [
            Paragraph(
                f"<b>Nombre:</b> {nombre_tutor}<br/>"
                f"<b>Documento:</b> {doc_tutor}<br/>"
                f"<b>Teléfono:</b> {tel_tutor}<br/>"
                f"<b>Dirección:</b> {dir_tutor}<br/>"
                f"<b>Origen:</b> {cert.ciudad_origen} → <b>Destino:</b> {cert.ciudad_destino or 'Nacional'} ({cert.pais_destino})",
                estilos['TextoNormal']
            ),
            Paragraph(
                f"<b>Nombre:</b> <font color='#E53935'><b>{nombre_mascota}</b></font> | <b>Especie:</b> {especie_txt}<br/>"
                f"<b>Raza:</b> {raza_txt} | <b>Sexo:</b> {sexo_txt}<br/>"
                f"<b>Edad:</b> {edad_txt} | <b>Color/Señas:</b> {color_txt}<br/>"
                f"<b>Peso:</b> <b>{cert.peso_kg} kg</b> | <b>Microchip:</b> {microchip_txt}<br/>"
                f"<b>Finalidad:</b> {cert.finalidad_etiqueta}",
                estilos['TextoNormal']
            ),
        ]
    ]
    t_sujetos = Table(info_sujetos, colWidths=[94 * mm, 94 * mm])
    t_sujetos.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), COLOR_GRIS_FONDO),
        ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
        ('INNERGRID', (0,0), (-1,-1), 0.5, COLOR_GRIS_BORDE),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    historia.append(t_sujetos)
    historia.append(Spacer(1, 6))

    # 3. Constantes Vitales y Examen Clínico
    fc_txt = f"{cert.frecuencia_cardiaca} lpm" if cert.frecuencia_cardiaca else "Normal"
    fr_txt = f"{cert.frecuencia_respiratoria} rpm" if cert.frecuencia_respiratoria else "Normal"
    temp_txt = f"{cert.temperatura_c} °C" if cert.temperatura_c else "Normal"

    constantes_data = [
        [
            Paragraph("<b>III. CONSTANTES VITALES AL MOMENTO DEL EXAMEN</b>", estilos['SeccionCabecera']),
            Paragraph(f"<b>Temperatura:</b> {temp_txt} | <b>FC:</b> {fc_txt} | <b>FR:</b> {fr_txt} | <b>Condición Corporal:</b> Óptima", estilos['TextoNormal'])
        ]
    ]
    t_constantes = Table(constantes_data, colWidths=[75 * mm, 113 * mm])
    t_constantes.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,0), COLOR_GRIS_FONDO),
        ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    historia.append(t_constantes)
    historia.append(Spacer(1, 6))

    # 4. Historial Sanitario: Vacunación Vigente
    vacunas_list = cert.datos_vacunacion if isinstance(cert.datos_vacunacion, list) else []
    vacunas_rows = [
        [
            Paragraph("<b>Inmunización / Vacuna</b>", estilos['SeccionCabecera']),
            Paragraph("<b>Laboratorio</b>", estilos['SeccionCabecera']),
            Paragraph("<b>Lote</b>", estilos['SeccionCabecera']),
            Paragraph("<b>Fecha Aplicación</b>", estilos['SeccionCabecera']),
            Paragraph("<b>Próxima Revacunación</b>", estilos['SeccionCabecera']),
        ]
    ]

    if vacunas_list:
        for v in vacunas_list:
            es_rabia = "rabia" in (v.get("nombre", "") or "").lower()
            nombre_v = f"<b><font color='#B71C1C'>★ {v.get('nombre')}</font></b>" if es_rabia else v.get("nombre", "Vacuna")
            vacunas_rows.append([
                Paragraph(nombre_v, estilos['TextoNormal']),
                Paragraph(v.get("laboratorio", "--") or "--", estilos['TextoNormal']),
                Paragraph(v.get("lote", "--") or "--", estilos['TextoNormal']),
                Paragraph(v.get("fecha_aplicacion", "--") or "--", estilos['TextoNormal']),
                Paragraph(f"<b>{v.get('fecha_proxima', '--') or '--'}</b>", estilos['TextoNormal']),
            ])
    else:
        vacunas_rows.append([
            Paragraph("Esquema de vacunación básico al día según historial clínico verificado.", estilos['TextoNormal']),
            Paragraph("--", estilos['TextoNormal']),
            Paragraph("--", estilos['TextoNormal']),
            Paragraph("--", estilos['TextoNormal']),
            Paragraph("--", estilos['TextoNormal']),
        ])

    t_vacunas = Table(vacunas_rows, colWidths=[54 * mm, 34 * mm, 32 * mm, 34 * mm, 34 * mm])
    t_vacunas.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), COLOR_GRIS_FONDO),
        ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
        ('INNERGRID', (0,0), (-1,-1), 0.5, COLOR_GRIS_BORDE),
        ('PADDING', (0,0), (-1,-1), 3.5),
    ]))
    historia.append(Paragraph("<b>IV. REGISTRO DE VACUNACIÓN VIGENTE (INMUNIZACIONES)</b>", estilos['SeccionCabecera']))
    historia.append(t_vacunas)
    historia.append(Spacer(1, 6))

    # 5. Historial Sanitario: Desparasitación
    desp_data = cert.datos_desparasitacion if isinstance(cert.datos_desparasitacion, dict) else {}
    desp_interna = desp_data.get("interna", {}) or {}
    desp_externa = desp_data.get("externa", {}) or {}

    desp_rows = [
        [
            Paragraph("<b>Tipo de Control</b>", estilos['SeccionCabecera']),
            Paragraph("<b>Producto Comercial</b>", estilos['SeccionCabecera']),
            Paragraph("<b>Principio Activo</b>", estilos['SeccionCabecera']),
            Paragraph("<b>Lote</b>", estilos['SeccionCabecera']),
            Paragraph("<b>Fecha Aplicación</b>", estilos['SeccionCabecera']),
        ],
        [
            Paragraph("<b>Desparasitación Interna</b> (Endoparásitos)", estilos['TextoNormal']),
            Paragraph(desp_interna.get("producto", "Antiparasitario Interno"), estilos['TextoNormal']),
            Paragraph(desp_interna.get("principio_activo", "Febantel / Pirantel / Praziquantel"), estilos['TextoNormal']),
            Paragraph(desp_interna.get("lote", "--") or "--", estilos['TextoNormal']),
            Paragraph(desp_interna.get("fecha", fecha_emision_str.split()[0]), estilos['TextoNormal']),
        ],
        [
            Paragraph("<b>Desparasitación Externa</b> (Ectoparásitos)", estilos['TextoNormal']),
            Paragraph(desp_externa.get("producto", "Antiparasitario Externo"), estilos['TextoNormal']),
            Paragraph(desp_externa.get("principio_activo", "Fluralaner / Sarolaner / Fipronil"), estilos['TextoNormal']),
            Paragraph(desp_externa.get("lote", "--") or "--", estilos['TextoNormal']),
            Paragraph(desp_externa.get("fecha", fecha_emision_str.split()[0]), estilos['TextoNormal']),
        ]
    ]
    t_desp = Table(desp_rows, colWidths=[54 * mm, 38 * mm, 44 * mm, 24 * mm, 28 * mm])
    t_desp.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), COLOR_GRIS_FONDO),
        ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
        ('INNERGRID', (0,0), (-1,-1), 0.5, COLOR_GRIS_BORDE),
        ('PADDING', (0,0), (-1,-1), 3.5),
    ]))
    historia.append(Paragraph("<b>V. CONTROL DE PARÁSITOS INTERNOS Y EXTERNOS</b>", estilos['SeccionCabecera']))
    historia.append(t_desp)
    historia.append(Spacer(1, 6))

    # 6. Dictamen Clínico y Certificación Médico Legal
    dictamen_box = [
        [
            Paragraph("<b>VI. DICTAMEN MÉDICO VETERINARIO & DECLARACIÓN OFICIAL DE SALUD</b>", estilos['SeccionCabecera'])
        ],
        [
            Paragraph(
                f"<font size=8>{cert.dictamen_texto}</font><br/><br/>"
                f"<b>ESTADO DE APTITUD:</b> <font color='#166534'><b>APTO PARA VIAJE Y CONVIVENCIA</b></font> · "
                f"Certificado expedido a solicitud de la parte interesada, con una vigencia de <b>{cert.dias_vigencia} días calendario</b> a partir de su emisión.",
                estilos['TextoNormal']
            )
        ]
    ]
    t_dictamen = Table(dictamen_box, colWidths=[188 * mm])
    t_dictamen.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,0), COLOR_GRIS_FONDO),
        ('BACKGROUND', (0,1), (0,1), colors.HexColor("#F0FDF4")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#BBF7D0")),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    historia.append(t_dictamen)
    historia.append(Spacer(1, 8))

    # 7. Firma del Profesional y Certificación Digital
    nombre_vet = vet.nombre if vet else clinica.get("doctora_nombre", "Dra. Daniela Pulido")
    titulo_vet = getattr(vet, "titulo_profesional", None) or clinica.get("doctora_titulo", "Médica veterinaria")
    tp_vet = getattr(vet, "tarjeta_profesional", None) or clinica.get("doctora_tp", "53214")
    esp_vet = getattr(vet, "especialidad", None) or clinica.get("doctora_especialidad", "Dpl. Dermatología de pequeñas especies")
    firma_vet = getattr(vet, "firma_digital", None) or clinica.get("doctora_firma", "")
    url_verif = cert.url_verificacion_publica()

    firma_img = _obtener_firma_flowable(firma_vet, width=42 * mm, height=18 * mm)
    lineas_sello = [
        f"<b>{nombre_vet}</b>",
        f"{titulo_vet} · T.P. No. {tp_vet}",
    ]
    if esp_vet:
        lineas_sello.append(f"<font color='#166534' size=7><b>{esp_vet}</b></font>")
    lineas_sello.append(f"<font size=7 color='#64748B'>{clinica['nombre']} · {clinica['subtitulo']}</font>")
    sello_html = "<br/>".join(lineas_sello)

    if firma_img:
        firma_col_cert = [
            firma_img,
            Paragraph(f"__________________________________________<br/>{sello_html}", estilos['PiePagina'])
        ]
    else:
        firma_col_cert = [
            Paragraph(f"__________________________________________<br/>{sello_html}", estilos['PiePagina'])
        ]

    hash_raw = getattr(cert, "hash_integridad_sha256", "") or ""
    hash_display = f"{hash_raw[:20]}...{hash_raw[-12:]}" if len(hash_raw) >= 32 else (hash_raw or "Válido")

    firma_block = [
        [
            Paragraph(
                f"<b>VALIDACIÓN OFICIAL DIGITAL:</b><br/>"
                f"<font size=7 color='#64748B'>"
                f"Certificado verificable en línea por autoridades sanitarias y aerolíneas.<br/>"
                f"URL: <u>{url_verif}</u><br/>"
                f"Hash SHA-256: <code>{hash_display}</code></font>",
                estilos['TextoNormal']
            ),
            firma_col_cert
        ]
    ]
    t_firma = Table(firma_block, colWidths=[100 * mm, 88 * mm])
    t_firma.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    historia.append(KeepTogether(t_firma))

    doc.build(historia)
    buffer.seek(0)
    return buffer


def generar_pdf_control(control, db_session=None) -> io.BytesIO:
    """Genera el Informe Oficial de Control Médico y Evolución Clínica en PDF con diseño Sandía VetCare."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    estilos = _crear_estilos()
    historia = []
    clinica = _obtener_datos_clinica(db_session)
    mascota = control.mascota
    tutor = control.tutor or (mascota.tutor if mascota else None)
    vet = control.veterinario

    # =========================================================================
    # 1. ENCABEZADO OFICIAL
    # =========================================================================
    fecha_str = control.fecha_hora.strftime("%d/%m/%Y %H:%M") if hasattr(control.fecha_hora, "strftime") else str(control.fecha_hora)
    folio_titulo = f"CONTROL #{control.id:04d}"

    logo_img = _obtener_logo_img(width=18 * mm, height=17 * mm)
    if logo_img:
        header_data = [
            [
                logo_img,
                Paragraph(f"<b>{clinica['nombre'].upper()}</b><br/><font size=8>{clinica['subtitulo']}</font><br/><font size=7 color='#64748B'>NIT: {clinica['nit']} · Tel: {clinica['telefono']}<br/>{clinica['direccion']} · {clinica['ciudad']}</font>", estilos['TituloClinica']),
                Paragraph(f"<b>INFORME DE CONTROL MÉDICO</b><br/><font color='#E53935' size=10.5><b>{folio_titulo}</b></font><br/><font size=8 color='#64748B'>Fecha: {fecha_str}</font>", estilos['DocumentoFolio'])
            ]
        ]
        t_header = Table(header_data, colWidths=[20 * mm, 90 * mm, 78 * mm])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('RIGHTPADDING', (0,0), (0,0), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
        ]))
    else:
        header_data = [
            [
                Paragraph(f"<b>{clinica['nombre'].upper()}</b><br/><font size=8>{clinica['subtitulo']}</font><br/><font size=7 color='#64748B'>NIT: {clinica['nit']} · Tel: {clinica['telefono']}<br/>{clinica['direccion']} · {clinica['ciudad']}</font>", estilos['TituloClinica']),
                Paragraph(f"<b>INFORME DE CONTROL MÉDICO</b><br/><font color='#E53935' size=10.5><b>{folio_titulo}</b></font><br/><font size=8 color='#64748B'>Fecha: {fecha_str}</font>", estilos['DocumentoFolio'])
            ]
        ]
        t_header = Table(header_data, colWidths=[110 * mm, 78 * mm])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
    historia.append(t_header)
    historia.append(HRFlowable(width="100%", thickness=1.5, color=COLOR_PRIMARIO, spaceAfter=7))

    # =========================================================================
    # 2. CUADRO DE INFORMACIÓN PACIENTE, TUTOR Y MÉDICO
    # =========================================================================
    nombre_mascota = mascota.nombre if mascota else "Paciente"
    especie_raza = f"{mascota.especie.capitalize() if mascota else ''} · {mascota.raza.nombre if mascota and mascota.raza else 'Mestizo'}"
    sexo_edad = f"{mascota.sexo.capitalize() if mascota and mascota.sexo else 'N/R'} · {mascota.edad_formateada if mascota and hasattr(mascota, 'edad_formateada') else 'N/R'}"
    nombre_tutor = tutor.nombre_completo if tutor else "N/A"
    tel_tutor = (tutor.whatsapp_efectivo or tutor.telefono if tutor else None) or "N/A"
    doc_tutor = f" · Doc: {tutor.documento_texto}" if tutor and hasattr(tutor, "documento_texto") and tutor.documento_texto else ""
    nombre_vet = vet.nombre if vet else clinica.get("doctora_nombre", "Dra. Daniela Pulido")

    info_data = [
        [
            Paragraph(f"<b>PACIENTE:</b> <font color='#E53935'><b>{nombre_mascota}</b></font>", estilos['TextoNormal']),
            Paragraph(f"<b>TUTOR:</b> <b>{nombre_tutor}</b>", estilos['TextoNormal']),
        ],
        [
            Paragraph(f"<b>Especie/Raza:</b> {especie_raza}", estilos['TextoNormal']),
            Paragraph(f"<b>Contacto:</b> {tel_tutor}{doc_tutor}", estilos['TextoNormal']),
        ],
        [
            Paragraph(f"<b>Sexo/Edad:</b> {sexo_edad}", estilos['TextoNormal']),
            Paragraph(f"<b>Médico Tratante:</b> {nombre_vet}", estilos['TextoNormal']),
        ]
    ]
    t_info = Table(info_data, colWidths=[94 * mm, 94 * mm])
    t_info.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), COLOR_GRIS_FONDO),
        ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
        ('INNERGRID', (0,0), (-1,-1), 0.5, COLOR_GRIS_BORDE),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    historia.append(t_info)
    historia.append(Spacer(1, 6))

    # =========================================================================
    # 3. CONSTANTES DEL CONTROL (PESO Y TEMPERATURA)
    # =========================================================================
    v_peso = f"{control.peso_kg} kg" if control.peso_kg else "—"
    v_temp = f"{control.temperatura_c} °C" if control.temperatura_c else "—"
    vitales_data = [
        ["Peso Registrado", "Temperatura Corporal", "Tipo / Motivo de Control"],
        [v_peso, v_temp, control.motivo or "Control de Seguimiento Clínico"]
    ]
    t_vitales = Table(vitales_data, colWidths=[48 * mm, 48 * mm, 92 * mm])
    t_vitales.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), COLOR_OSCURO),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 7.5),
        ('ALIGN', (0,0), (1,-1), 'CENTER'),
        ('ALIGN', (2,0), (2,-1), 'LEFT'),
        ('BACKGROUND', (0,1), (-1,1), COLOR_GRIS_FONDO),
        ('FONTNAME', (0,1), (-1,1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,1), (-1,1), 8),
        ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
        ('INNERGRID', (0,0), (-1,-1), 0.5, COLOR_GRIS_BORDE),
        ('PADDING', (0,0), (-1,-1), 3.5),
    ]))
    historia.append(t_vitales)
    historia.append(Spacer(1, 6))

    # =========================================================================
    # 4. EVOLUCIÓN CLÍNICA & AVANCES
    # =========================================================================
    historia.append(Paragraph("<font color='#0284C7'><b>●</b></font> <b>EVOLUCIÓN CLÍNICA & RESPUESTA AL TRATAMIENTO</b>", estilos['SeccionHeader']))
    historia.append(Spacer(1, 2))
    avances_txt = (control.avances or "Sin evolución registrada.").replace("\n", "<br/>")
    t_avances = Table([[Paragraph(f"<b>Avances / Hallazgos en Recontrol:</b><br/>{avances_txt}", estilos['TextoNormal'])]], colWidths=[188 * mm])
    t_avances.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F0F9FF")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#BAE6FD")),
        ('PADDING', (0,0), (-1,-1), 4.5),
    ]))
    historia.append(t_avances)
    historia.append(Spacer(1, 6))

    # =========================================================================
    # 5. DIAGNÓSTICO
    # =========================================================================
    historia.append(Paragraph("<font color='#D97706'><b>●</b></font> <b>DIAGNÓSTICO & SEGUIMIENTO</b>", estilos['SeccionHeader']))
    historia.append(Spacer(1, 2))
    diag_txt = control.diagnostico or "Seguimiento y control médico."
    t_diag = Table([[Paragraph(f"<b>DIAGNÓSTICO:</b> {diag_txt}", estilos['TextoNormal'])]], colWidths=[188 * mm])
    t_diag.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#FFFBEB")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#FDE68A")),
        ('PADDING', (0,0), (-1,-1), 4.5),
    ]))
    historia.append(t_diag)
    historia.append(Spacer(1, 6))

    # =========================================================================
    # 6. PLAN TERAPÉUTICO Y MEDICACIÓN (Rx)
    # =========================================================================
    historia.append(Paragraph("<font color='#475569'><b>●</b></font> <b>PLAN TERAPÉUTICO & RECOMENDACIONES</b>", estilos['SeccionHeader']))
    historia.append(Spacer(1, 2))
    plan_txt = (control.plan_terapeutico or "Continuar manejo clínico prescrito.").replace("\n", "<br/>")
    t_plan = Table([[Paragraph(f"<b>Plan Terapéutico:</b><br/>{plan_txt}", estilos['TextoNormal'])]], colWidths=[188 * mm])
    t_plan.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), COLOR_GRIS_FONDO),
        ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
        ('PADDING', (0,0), (-1,-1), 4.5),
    ]))
    historia.append(t_plan)
    historia.append(Spacer(1, 6))

    # Medicamentos / Fórmula si existen
    if control.medicamento:
        med_html = _formatear_medicamentos_html(control.medicamento)
        receta_data = [
            [
                Paragraph("<b><font color='#E53935' size=11>Rx</font> FÓRMULA MÉDICA & POSOLOGÍA PRESCRITA</b>", estilos['TextoNegrita'])
            ],
            [
                Paragraph(med_html, estilos['TextoReceta'])
            ]
        ]
        t_receta = Table(receta_data, colWidths=[188 * mm])
        t_receta.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#FEE2E2")),
            ('BACKGROUND', (0,1), (-1,1), colors.HexColor("#FFF1F2")),
            ('BOX', (0,0), (-1,-1), 1.2, COLOR_PRIMARIO),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#FECACA")),
            ('PADDING', (0,0), (-1,-1), 4.5),
        ]))
        historia.append(t_receta)
        historia.append(Spacer(1, 6))

    # Próximo control / Observaciones
    prox_items = []
    if control.fecha_proximo_control:
        f_prox = control.fecha_proximo_control.strftime("%d/%m/%Y %I:%M %p") if hasattr(control.fecha_proximo_control, "strftime") else str(control.fecha_proximo_control)
        prox_items.append(f"🗓️ <b>PRÓXIMO RECONTROL PROGRAMADO:</b> <font color='#E53935'><b>{f_prox}</b></font>")
    if control.observaciones:
        prox_items.append(f"<b>Observaciones:</b> {control.observaciones}")

    if prox_items:
        t_prox = Table([[Paragraph("<br/>".join(prox_items), estilos['TextoNormal'])]], colWidths=[188 * mm])
        t_prox.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F1F5F9")),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#CBD5E1")),
            ('PADDING', (0,0), (-1,-1), 4),
        ]))
        historia.append(t_prox)
        historia.append(Spacer(1, 6))

    # =========================================================================
    # 7. FIRMA MÉDICA Y SELLO
    # =========================================================================
    historia.append(Spacer(1, 6))
    historia.append(_crear_bloque_firma_medica(vet, clinica, estilos, ancho_bloque=75 * mm))

    doc.build(historia)
    buffer.seek(0)
    return buffer


def generar_pdf_remision(remision, db_session=None) -> io.BytesIO:
    """Genera la Orden Oficial de Remisión Clínica / Derivación a Especialista en PDF."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    estilos = _crear_estilos()
    historia = []
    clinica = _obtener_datos_clinica(db_session)
    mascota = remision.mascota
    tutor = remision.tutor or (mascota.tutor if mascota else None)
    vet = remision.veterinario

    # 1. Header
    fecha_str = remision.fecha_remision.strftime("%d/%m/%Y %H:%M") if hasattr(remision.fecha_remision, "strftime") else str(remision.fecha_remision)
    folio_titulo = f"REMISIÓN #{remision.id:04d}"

    logo_img = _obtener_logo_img(width=18 * mm, height=17 * mm)
    if logo_img:
        header_data = [
            [
                logo_img,
                Paragraph(f"<b>{clinica['nombre'].upper()}</b><br/><font size=8>{clinica['subtitulo']}</font><br/><font size=7 color='#64748B'>NIT: {clinica['nit']} · Tel: {clinica['telefono']}<br/>{clinica['direccion']} · {clinica['ciudad']}</font>", estilos['TituloClinica']),
                Paragraph(f"<b>ORDEN DE REMISIÓN MÉDICA</b><br/><font color='#E53935' size=10.5><b>{folio_titulo}</b></font><br/><font size=8 color='#64748B'>Fecha: {fecha_str}</font>", estilos['DocumentoFolio'])
            ]
        ]
        t_header = Table(header_data, colWidths=[20 * mm, 90 * mm, 78 * mm])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('RIGHTPADDING', (0,0), (0,0), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
        ]))
    else:
        header_data = [
            [
                Paragraph(f"<b>{clinica['nombre'].upper()}</b><br/><font size=8>{clinica['subtitulo']}</font><br/><font size=7 color='#64748B'>NIT: {clinica['nit']} · Tel: {clinica['telefono']}<br/>{clinica['direccion']} · {clinica['ciudad']}</font>", estilos['TituloClinica']),
                Paragraph(f"<b>ORDEN DE REMISIÓN MÉDICA</b><br/><font color='#E53935' size=10.5><b>{folio_titulo}</b></font><br/><font size=8 color='#64748B'>Fecha: {fecha_str}</font>", estilos['DocumentoFolio'])
            ]
        ]
        t_header = Table(header_data, colWidths=[110 * mm, 78 * mm])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
    historia.append(t_header)
    historia.append(HRFlowable(width="100%", thickness=1.5, color=COLOR_PRIMARIO, spaceAfter=7))

    # 2. Datos Paciente y Tutor
    nombre_mascota = mascota.nombre if mascota else "Paciente"
    especie_raza = f"{mascota.especie.capitalize() if mascota else ''} · {mascota.raza.nombre if mascota and mascota.raza else 'Mestizo'}"
    sexo_edad = f"{mascota.sexo.capitalize() if mascota and mascota.sexo else 'N/R'} · {mascota.edad_formateada if mascota and hasattr(mascota, 'edad_formateada') else 'N/R'}"
    nombre_tutor = tutor.nombre_completo if tutor else "N/A"
    tel_tutor = (tutor.whatsapp_efectivo or tutor.telefono if tutor else None) or "N/A"
    doc_tutor = f" · Doc: {tutor.documento_texto}" if tutor and hasattr(tutor, "documento_texto") and tutor.documento_texto else ""
    nombre_vet = vet.nombre if vet else clinica.get("doctora_nombre", "Dra. Daniela Pulido")

    info_data = [
        [
            Paragraph(f"<b>PACIENTE:</b> <font color='#E53935'><b>{nombre_mascota}</b></font>", estilos['TextoNormal']),
            Paragraph(f"<b>TUTOR:</b> <b>{nombre_tutor}</b>", estilos['TextoNormal']),
        ],
        [
            Paragraph(f"<b>Especie/Raza:</b> {especie_raza}", estilos['TextoNormal']),
            Paragraph(f"<b>Contacto:</b> {tel_tutor}{doc_tutor}", estilos['TextoNormal']),
        ],
        [
            Paragraph(f"<b>Sexo/Edad:</b> {sexo_edad}", estilos['TextoNormal']),
            Paragraph(f"<b>Médico Remitente:</b> {nombre_vet}", estilos['TextoNormal']),
        ]
    ]
    t_info = Table(info_data, colWidths=[94 * mm, 94 * mm])
    t_info.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), COLOR_GRIS_FONDO),
        ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
        ('INNERGRID', (0,0), (-1,-1), 0.5, COLOR_GRIS_BORDE),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    historia.append(t_info)
    historia.append(Spacer(1, 6))

    # 3. Destino de la Derivación
    dest_lineas = [f"<b>Especialidad Requerida:</b> <font color='#E53935'><b>{remision.especialidad_destino}</b></font>"]
    if remision.centro_medico_destino:
        dest_lineas.append(f"<b>Centro / Especialista:</b> {remision.centro_medico_destino}")
    if remision.telefono_destino:
        dest_lineas.append(f"<b>Teléfono de Contacto:</b> {remision.telefono_destino}")
    if remision.direccion_destino:
        dest_lineas.append(f"<b>Dirección:</b> {remision.direccion_destino}")

    t_dest = Table([[Paragraph("<br/>".join(dest_lineas), estilos['TextoNormal'])]], colWidths=[188 * mm])
    t_dest.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#EFF6FF")),
        ('BOX', (0,0), (-1,-1), 1.2, colors.HexColor("#93C5FD")),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    historia.append(t_dest)
    historia.append(Spacer(1, 6))

    # 4. Motivo de la Remisión
    historia.append(Paragraph("<font color='#E53935'><b>●</b></font> <b>MOTIVO DE LA REMISIÓN & RESUMEN CLÍNICO</b>", estilos['SeccionHeader']))
    historia.append(Spacer(1, 2))
    motivo_txt = (remision.motivo_remision or "Derivación para valoración por especialista.").replace("\n", "<br/>")
    t_motivo = Table([[Paragraph(motivo_txt, estilos['TextoNormal'])]], colWidths=[188 * mm])
    t_motivo.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), COLOR_GRIS_FONDO),
        ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    historia.append(t_motivo)
    historia.append(Spacer(1, 6))

    # 5. Hallazgos y Antecedentes
    if remision.observaciones_clinicas or remision.antecedentes_enfermedades or remision.antecedentes_cirugias:
        historia.append(Paragraph("<font color='#0284C7'><b>●</b></font> <b>ANTECEDENTES & OBSERVACIONES</b>", estilos['SeccionHeader']))
        historia.append(Spacer(1, 2))
        ant_items = []
        if remision.observaciones_clinicas:
            ant_items.append(f"<b>Hallazgos Clínicos:</b> {remision.observaciones_clinicas}")
        if remision.antecedentes_enfermedades:
            ant_items.append(f"<b>Enfermedades / Alergias:</b> {remision.antecedentes_enfermedades}")
        if remision.antecedentes_cirugias:
            ant_items.append(f"<b>Cirugías Previas:</b> {remision.antecedentes_cirugias}")
        if remision.dieta_marca_tipo:
            ant_items.append(f"<b>Dieta / Alimentación:</b> {remision.dieta_marca_tipo}")

        t_ant = Table([[Paragraph("<br/>".join(ant_items), estilos['TextoNormal'])]], colWidths=[188 * mm])
        t_ant.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
            ('PADDING', (0,0), (-1,-1), 4.5),
        ]))
        historia.append(t_ant)
        historia.append(Spacer(1, 6))

    # 6. Estatus Preventivo
    prev_lineas = []
    desp_int = f"{remision.desparasitacion_interna_producto or 'N/A'}" + (f" ({remision.desparasitacion_interna_fecha.strftime('%d/%m/%Y')})" if remision.desparasitacion_interna_fecha else "")
    prev_lineas.append(f"<b>Desparasitación Interna:</b> {desp_int}")
    if remision.desparasitacion_externa_producto:
        prev_lineas.append(f"<b>Externa:</b> {remision.desparasitacion_externa_producto}")
    vac_txt = "Al día" if remision.vacunacion_al_dia else "Incompleta / Pendiente"
    if remision.vacunacion_ultima_fecha:
        vac_txt += f" (Última: {remision.vacunacion_ultima_fecha.strftime('%d/%m/%Y')})"
    prev_lineas.append(f"<b>Vacunación:</b> {vac_txt}")

    t_prev = Table([[Paragraph(" · ".join(prev_lineas), estilos['TextoPequeno'])]], colWidths=[188 * mm])
    t_prev.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F0FDF4")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#BBF7D0")),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    historia.append(t_prev)
    historia.append(Spacer(1, 8))

    # 7. Firma
    historia.append(_crear_bloque_firma_medica(vet, clinica, estilos, ancho_bloque=75 * mm))

    doc.build(historia)
    buffer.seek(0)
    return buffer


def generar_pdf_carnet_vacunacion(mascota, db_session=None) -> io.BytesIO:
    """Genera el Carnet Oficial de Vacunación & Desparasitación de la Mascota en PDF."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    estilos = _crear_estilos()
    historia = []
    clinica = _obtener_datos_clinica(db_session)
    tutor = mascota.tutor

    # 1. Header
    logo_img = _obtener_logo_img(width=18 * mm, height=17 * mm)
    if logo_img:
        header_data = [
            [
                logo_img,
                Paragraph(f"<b>{clinica['nombre'].upper()}</b><br/><font size=8>{clinica['subtitulo']}</font><br/><font size=7 color='#64748B'>NIT: {clinica['nit']} · Tel: {clinica['telefono']}<br/>{clinica['direccion']} · {clinica['ciudad']}</font>", estilos['TituloClinica']),
                Paragraph(f"<b>CARNET DE VACUNACIÓN</b><br/><font color='#E53935' size=10.5><b>PLAN PREVENTIVO</b></font><br/><font size=8 color='#64748B'>Expedición: {datetime.now().strftime('%d/%m/%Y')}</font>", estilos['DocumentoFolio'])
            ]
        ]
        t_header = Table(header_data, colWidths=[20 * mm, 90 * mm, 78 * mm])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('RIGHTPADDING', (0,0), (0,0), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
        ]))
    else:
        header_data = [
            [
                Paragraph(f"<b>{clinica['nombre'].upper()}</b><br/><font size=8>{clinica['subtitulo']}</font><br/><font size=7 color='#64748B'>NIT: {clinica['nit']} · Tel: {clinica['telefono']}<br/>{clinica['direccion']} · {clinica['ciudad']}</font>", estilos['TituloClinica']),
                Paragraph(f"<b>CARNET DE VACUNACIÓN</b><br/><font color='#E53935' size=10.5><b>PLAN PREVENTIVO</b></font><br/><font size=8 color='#64748B'>Expedición: {datetime.now().strftime('%d/%m/%Y')}</font>", estilos['DocumentoFolio'])
            ]
        ]
        t_header = Table(header_data, colWidths=[110 * mm, 78 * mm])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
    historia.append(t_header)
    historia.append(HRFlowable(width="100%", thickness=1.5, color=COLOR_PRIMARIO, spaceAfter=7))

    # 2. Datos Paciente y Tutor
    nombre_mascota = mascota.nombre
    especie_raza = f"{mascota.especie.capitalize()} · {mascota.raza.nombre if mascota.raza else 'Mestizo'}"
    sexo_edad = f"{mascota.sexo.capitalize()} · {mascota.edad_formateada if hasattr(mascota, 'edad_formateada') else 'N/R'}"
    microchip = f" · Chip: {mascota.microchip}" if mascota.microchip else ""
    nombre_tutor = tutor.nombre_completo if tutor else "N/A"
    tel_tutor = (tutor.whatsapp_efectivo or tutor.telefono if tutor else None) or "N/A"
    doc_tutor = f" · Doc: {tutor.documento_texto}" if tutor and hasattr(tutor, "documento_texto") and tutor.documento_texto else ""

    info_data = [
        [
            Paragraph(f"<b>PACIENTE:</b> <font color='#E53935'><b>{nombre_mascota}</b></font>", estilos['TextoNormal']),
            Paragraph(f"<b>TUTOR:</b> <b>{nombre_tutor}</b>", estilos['TextoNormal']),
        ],
        [
            Paragraph(f"<b>Especie/Raza:</b> {especie_raza}", estilos['TextoNormal']),
            Paragraph(f"<b>Contacto:</b> {tel_tutor}{doc_tutor}", estilos['TextoNormal']),
        ],
        [
            Paragraph(f"<b>Sexo/Edad:</b> {sexo_edad}{microchip}", estilos['TextoNormal']),
            Paragraph(f"<b>Clínica:</b> {clinica['nombre']}", estilos['TextoNormal']),
        ]
    ]
    t_info = Table(info_data, colWidths=[94 * mm, 94 * mm])
    t_info.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), COLOR_GRIS_FONDO),
        ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
        ('INNERGRID', (0,0), (-1,-1), 0.5, COLOR_GRIS_BORDE),
        ('PADDING', (0,0), (-1,-1), 4),
    ]))
    historia.append(t_info)
    historia.append(Spacer(1, 8))

    # 3. Historial de Vacunación
    historia.append(Paragraph("<font color='#E53935'><b>💉</b></font> <b>HISTORIAL DE VACUNAS APLICADAS</b>", estilos['SeccionHeader']))
    historia.append(Spacer(1, 2))

    vacunas_lista = getattr(mascota, 'vacunas', []) or []
    if vacunas_lista:
        vac_rows = [["Vacuna / Biológico", "Lote / Lab.", "Aplicación", "Próxima Dosis", "Estado"]]
        for v in vacunas_lista:
            f_apl = v.fecha_aplicacion.strftime("%d/%m/%Y") if hasattr(v.fecha_aplicacion, "strftime") else str(v.fecha_aplicacion)
            f_prox = v.fecha_proxima.strftime("%d/%m/%Y") if v.fecha_proxima and hasattr(v.fecha_proxima, "strftime") else "—"
            est = v.estado_vencimiento
            if est == 'al_dia':
                est_txt = "<font color='#166534'><b>AL DÍA</b></font>"
            elif est == 'proxima_vencer':
                est_txt = "<font color='#D97706'><b>PRÓXIMA</b></font>"
            else:
                est_txt = "<font color='#B91C1C'><b>VENCIDA</b></font>"
            
            lote_lab = f"{v.lote or ''} {v.laboratorio or ''}".strip() or "—"
            vac_rows.append([
                Paragraph(f"<b>{v.nombre_vacuna}</b>", estilos['TextoNormal']),
                Paragraph(lote_lab, estilos['TextoPequeno']),
                Paragraph(f_apl, estilos['TextoNormal']),
                Paragraph(f"<b>{f_prox}</b>", estilos['TextoNormal']),
                Paragraph(est_txt, estilos['TextoCentrado']),
            ])

        t_vac = Table(vac_rows, colWidths=[55 * mm, 38 * mm, 30 * mm, 35 * mm, 30 * mm])
        t_vac.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), COLOR_OSCURO),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 7.5),
            ('ALIGN', (2,0), (3,-1), 'CENTER'),
            ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
            ('INNERGRID', (0,0), (-1,-1), 0.5, COLOR_GRIS_BORDE),
            ('PADDING', (0,0), (-1,-1), 3.5),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        historia.append(t_vac)
    else:
        historia.append(Paragraph("<i>Sin registros de vacunas en el sistema.</i>", estilos['TextoPequeno']))

    historia.append(Spacer(1, 8))

    # 4. Historial de Desparasitaciones
    historia.append(Paragraph("<font color='#059669'><b>💊</b></font> <b>HISTORIAL DE DESPARASITACIÓN</b>", estilos['SeccionHeader']))
    historia.append(Spacer(1, 2))

    desp_lista = getattr(mascota, 'desparasitaciones', []) or []
    if desp_lista:
        desp_rows = [["Producto", "Tipo / Dosis", "Peso", "Fecha Aplicación", "Próxima Dosis"]]
        for d in desp_lista:
            f_apl = d.fecha_aplicacion.strftime("%d/%m/%Y") if hasattr(d.fecha_aplicacion, "strftime") else str(d.fecha_aplicacion)
            f_prox = d.fecha_proxima.strftime("%d/%m/%Y") if d.fecha_proxima and hasattr(d.fecha_proxima, "strftime") else "—"
            p_kg = f"{d.peso_kg} kg" if d.peso_kg else "—"
            tipo_dosis = f"{d.tipo.capitalize()} {d.dosis or ''}".strip()
            desp_rows.append([
                Paragraph(f"<b>{d.producto}</b>", estilos['TextoNormal']),
                Paragraph(tipo_dosis, estilos['TextoNormal']),
                Paragraph(p_kg, estilos['TextoNormal']),
                Paragraph(f_apl, estilos['TextoNormal']),
                Paragraph(f"<b>{f_prox}</b>", estilos['TextoNormal']),
            ])

        t_desp = Table(desp_rows, colWidths=[55 * mm, 45 * mm, 25 * mm, 32 * mm, 31 * mm])
        t_desp.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1E293B")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 7.5),
            ('ALIGN', (2,0), (4,-1), 'CENTER'),
            ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
            ('INNERGRID', (0,0), (-1,-1), 0.5, COLOR_GRIS_BORDE),
            ('PADDING', (0,0), (-1,-1), 3.5),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        historia.append(t_desp)
    else:
        historia.append(Paragraph("<i>Sin registros de desparasitación en el sistema.</i>", estilos['TextoPequeno']))

    historia.append(Spacer(1, 10))
    historia.append(_crear_bloque_firma_medica(None, clinica, estilos, ancho_bloque=75 * mm))

    doc.build(historia)
    buffer.seek(0)
    return buffer


def generar_pdf_consentimiento(doc_consentimiento, db_session=None) -> io.BytesIO:
    """Genera el Documento Oficial de Consentimiento Informado con firmas digitales en PDF."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
    )

    estilos = _crear_estilos()
    historia = []
    clinica = _obtener_datos_clinica(db_session)
    mascota = doc_consentimiento.mascota
    tutor = doc_consentimiento.tutor or (mascota.tutor if mascota else None)
    vet = doc_consentimiento.veterinario
    firma = doc_consentimiento.firma

    # 1. Header
    fecha_str = doc_consentimiento.creado_en.strftime("%d/%m/%Y %H:%M") if hasattr(doc_consentimiento.creado_en, "strftime") else str(doc_consentimiento.creado_en)
    folio_titulo = f"CONSENTIMIENTO #{doc_consentimiento.id:04d}"

    logo_img = _obtener_logo_img(width=18 * mm, height=17 * mm)
    if logo_img:
        header_data = [
            [
                logo_img,
                Paragraph(f"<b>{clinica['nombre'].upper()}</b><br/><font size=8>{clinica['subtitulo']}</font><br/><font size=7 color='#64748B'>NIT: {clinica['nit']} · Tel: {clinica['telefono']}<br/>{clinica['direccion']} · {clinica['ciudad']}</font>", estilos['TituloClinica']),
                Paragraph(f"<b>CONSENTIMIENTO INFORMADO</b><br/><font color='#E53935' size=10.5><b>{folio_titulo}</b></font><br/><font size=8 color='#64748B'>Fecha: {fecha_str}</font>", estilos['DocumentoFolio'])
            ]
        ]
        t_header = Table(header_data, colWidths=[20 * mm, 90 * mm, 78 * mm])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('RIGHTPADDING', (0,0), (0,0), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
        ]))
    else:
        header_data = [
            [
                Paragraph(f"<b>{clinica['nombre'].upper()}</b><br/><font size=8>{clinica['subtitulo']}</font><br/><font size=7 color='#64748B'>NIT: {clinica['nit']} · Tel: {clinica['telefono']}<br/>{clinica['direccion']} · {clinica['ciudad']}</font>", estilos['TituloClinica']),
                Paragraph(f"<b>CONSENTIMIENTO INFORMADO</b><br/><font color='#E53935' size=10.5><b>{folio_titulo}</b></font><br/><font size=8 color='#64748B'>Fecha: {fecha_str}</font>", estilos['DocumentoFolio'])
            ]
        ]
        t_header = Table(header_data, colWidths=[110 * mm, 78 * mm])
        t_header.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
    historia.append(t_header)
    historia.append(HRFlowable(width="100%", thickness=1.5, color=COLOR_PRIMARIO, spaceAfter=7))

    # 2. Título y Estado
    estado_badge = "<font color='#166534'><b>FIRMADO DIGITALMENTE</b></font>" if doc_consentimiento.esta_firmado else "<font color='#B91C1C'><b>PENDIENTE DE FIRMA</b></font>"
    historia.append(Paragraph(f"<b>{doc_consentimiento.titulo.upper()}</b> &nbsp;·&nbsp; {estado_badge}", estilos['SeccionHeader']))
    historia.append(Spacer(1, 4))

    # 3. Contenido del Consentimiento
    parrafos_cuerpo = [p.strip() for p in doc_consentimiento.contenido_final.split("\n\n") if p.strip()]
    cuerpo_data = []
    for p in parrafos_cuerpo:
        cuerpo_data.append([Paragraph(p.replace("\n", "<br/>"), estilos['TextoNormal'])])

    t_cuerpo = Table(cuerpo_data, colWidths=[188 * mm])
    t_cuerpo.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
        ('BOX', (0,0), (-1,-1), 1, COLOR_GRIS_BORDE),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#F1F5F9")),
        ('PADDING', (0,0), (-1,-1), 4.5),
    ]))
    historia.append(t_cuerpo)
    historia.append(Spacer(1, 8))

    # 4. Firmas Duales (Tutor y Veterinario)
    firma_tutor_img = _obtener_firma_flowable(firma.trazo_firma_png if firma else None, width=46 * mm, height=18 * mm)
    nombre_firmante = firma.nombre_firmante if firma else (tutor.nombre_completo if tutor else "Tutor Legal")
    doc_firmante = firma.documento_firmante if firma else (tutor.documento_texto if hasattr(tutor, "documento_texto") and tutor.documento_texto else "")

    lineas_tutor = [
        f"<b>{nombre_firmante}</b>",
        f"<font color='#334155'>CC/Doc: {doc_firmante}</font>",
        f"<font size=6.5 color='#64748B'>Tutor / Responsable Legal</font>",
    ]
    p_sello_tutor = Paragraph("<br/>".join(lineas_tutor), estilos['PiePagina'])

    filas_tutor = []
    if firma_tutor_img:
        filas_tutor.append([firma_tutor_img])
    else:
        filas_tutor.append([Spacer(1, 14 * mm)])
    filas_tutor.append([p_sello_tutor])

    t_sello_tutor = Table(filas_tutor, colWidths=[80 * mm])
    t_sello_tutor.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LINEABOVE', (0,1), (0,1), 1, colors.HexColor("#334155")),
        ('TOPPADDING', (0,1), (0,1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))

    # Bloque Veterinario
    nombre_vet = vet.nombre if vet else clinica.get("doctora_nombre", "Dra. Daniela Pulido")
    titulo_vet = getattr(vet, "titulo_profesional", None) or clinica.get("doctora_titulo", "Médica veterinaria")
    tp_vet = getattr(vet, "tarjeta_profesional", None) or clinica.get("doctora_tp", "53214")
    firma_vet_img = _obtener_firma_flowable(getattr(vet, "firma_digital", None) or clinica.get("doctora_firma", ""), width=46 * mm, height=18 * mm)

    lineas_vet = [
        f"<b>{nombre_vet}</b>",
        f"<font color='#334155'>{titulo_vet} · T.P. {tp_vet}</font>",
        f"<font size=6.5 color='#64748B'>{clinica['nombre']}</font>",
    ]
    p_sello_vet = Paragraph("<br/>".join(lineas_vet), estilos['PiePagina'])

    filas_vet = []
    if firma_vet_img:
        filas_vet.append([firma_vet_img])
    else:
        filas_vet.append([Spacer(1, 14 * mm)])
    filas_vet.append([p_sello_vet])

    t_sello_vet = Table(filas_vet, colWidths=[80 * mm])
    t_sello_vet.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LINEABOVE', (0,1), (0,1), 1, colors.HexColor("#334155")),
        ('TOPPADDING', (0,1), (0,1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
    ]))

    t_firmas_dual = Table([[t_sello_tutor, "", t_sello_vet]], colWidths=[85 * mm, 18 * mm, 85 * mm])
    t_firmas_dual.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    historia.append(KeepTogether(t_firmas_dual))

    # 5. Hash de Integridad
    hash_txt = doc_consentimiento.calcular_hash_integridad() if hasattr(doc_consentimiento, "calcular_hash_integridad") else ""
    if hash_txt:
        historia.append(Spacer(1, 4))
        historia.append(Paragraph(f"<font size=6.5 color='#94A3B8'>Certificación e Integridad Criptográfica SHA-256: {hash_txt} · Sandía VetCare</font>", estilos['PiePagina']))

    doc.build(historia)
    buffer.seek(0)
    return buffer


