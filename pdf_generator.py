"""Generador de documentos PDF oficiales para Sandía VetCare con ReportLab.

Incluye:
- Informe Clínico de Consulta Médica (SOAP) y Examen por Sistemas
- Fórmula Médica / Prescripción (Rx)
- Comprobante / Factura de Venta POS
- Certificado y Resumen de Spa & Peluquería
"""

import io
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
    """Recupera la configuración de la clínica o valores por defecto."""
    datos = {
        "nombre": "Sandía",
        "subtitulo": "Medicina y Spa Veterinario",
        "nit": "901.554.892-1",
        "direccion": "Cra. 15 # 104-32, Usaquén",
        "ciudad": "Bogotá D.C., Colombia",
        "telefono": "312 456 7890",
        "whatsapp": "+57 312 456 7890",
        "email": "contacto@sandiavetcare.com",
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
        except Exception:
            pass
    return datos


def _crear_estilos():
    estilos = getSampleStyleSheet()
    
    estilos.add(ParagraphStyle(
        'TituloClinica',
        parent=estilos['Normal'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=18,
        textColor=COLOR_PRIMARIO,
    ))
    
    estilos.add(ParagraphStyle(
        'SubtituloClinica',
        parent=estilos['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=COLOR_TEXTO,
    ))
    
    estilos.add(ParagraphStyle(
        'DocumentoFolio',
        parent=estilos['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=COLOR_OSCURO,
        alignment=2, # Derecha
    ))

    estilos.add(ParagraphStyle(
        'SeccionHeader',
        parent=estilos['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=COLOR_OSCURO,
    ))

    estilos.add(ParagraphStyle(
        'TextoNormal',
        parent=estilos['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11.5,
        textColor=COLOR_TEXTO,
    ))

    estilos.add(ParagraphStyle(
        'TextoNegrita',
        parent=estilos['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8.5,
        leading=11.5,
        textColor=COLOR_OSCURO,
    ))

    estilos.add(ParagraphStyle(
        'TextoReceta',
        parent=estilos['Normal'],
        fontName='Courier',
        fontSize=9,
        leading=12,
        textColor=COLOR_OSCURO,
    ))

    estilos.add(ParagraphStyle(
        'PiePagina',
        parent=estilos['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=7.5,
        leading=9.5,
        textColor=colors.HexColor("#64748B"),
        alignment=1, # Centro
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
    nombre_vet = f"Dr/a. {vet.nombre}" if vet else "Médico Veterinario"

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
    v_fr = f"{consulta.frecuencia_respiratoria} rpm" if consulta.frecuencia_respiratoria else "—"
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
    if sistemas:
        sist_rows = [["Sistema Evaluado", "Estado", "Hallazgos / Observaciones Clínicas"]]
        for k, v in sistemas.items():
            nom = v.get("nombre") or k.replace("_", " ").capitalize()
            est = v.get("estado", "normal").upper()
            obs = v.get("observacion") or "Sin alteraciones aparentes."
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
    historia.append(Paragraph("<b>A · AVALÚO (Diagnóstico Clínico)</b>", estilos['SeccionHeader']))
    historia.append(Spacer(1, 2))
    diag_data = [[Paragraph(f"<b>DIAGNÓSTICO:</b> {consulta.diagnostico}", estilos['TextoNormal'])]]
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
    
    plan_data = [
        [Paragraph(f"<b>Indicaciones Clínicas & Procedimientos:</b><br/>{consulta.plan_tratamiento.replace(chr(10), '<br/>')}", estilos['TextoNormal'])]
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
        receta_data = [
            [
                Paragraph("<b><font color='#E53935' size=11>Rx</font> FÓRMULA MÉDICA & PRESCRIPCIÓN AL TUTOR</b>", estilos['TextoNegrita'])
            ],
            [
                Paragraph(consulta.receta_medica.replace(chr(10), "<br/>"), estilos['TextoReceta'])
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
    firma_data = [
        [
            "",
            Paragraph(f"______________________________________<br/><b>{nombre_vet}</b><br/>Médico Veterinario Tratante<br/><font size=7 color='#64748B'>{clinica['nombre']} · Medicina & Spa Veterinario</font>", estilos['PiePagina'])
        ]
    ]
    t_firma = Table(firma_data, colWidths=[100 * mm, 88 * mm])
    t_firma.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
    ]))
    historia.append(KeepTogether(t_firma))

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
    cliente_doc = f"NIT/CC: {tutor.documento_texto}" if tutor and hasattr(tutor, "documento_texto") else "NIT/CC: 222222222222"
    cliente_tel = f"Tel: {tutor.telefono}" if tutor and tutor.telefono else ""
    cajero_nom = usuario_vendedor.nombre if usuario_vendedor else "Caja Principal"
    mascota_nom = f" · Mascota: <strong>{venta.mascota.nombre}</strong>" if venta.mascota else ""

    info_data = [
        [
            Paragraph(f"<b>CLIENTE:</b> {cliente_nom}{mascota_nom}", estilos['TextoNormal']),
            Paragraph(f"<b>ATENDIDO POR:</b> {cajero_nom}", estilos['TextoNormal']),
        ],
        [
            Paragraph(f"<b>Documento:</b> {cliente_doc} · {cliente_tel}", estilos['TextoNormal']),
            Paragraph(f"<b>Estado:</b> <font color='#166534'><b>{venta.estado.upper()}</b></font>", estilos['TextoNormal']),
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
    detalles_lista = getattr(venta, 'detalles', [])
    for item in detalles_lista:
        desc = item.descripcion
        cant = f"{item.cantidad:g}" if hasattr(item, "cantidad") else str(item.cantidad)
        unit = f"${item.precio_unitario:,.2f}"
        desc_txt = f"-${item.descuento:,.2f}" if hasattr(item, "descuento") and item.descuento else "$0.00"
        total_it = f"${item.total_linea:,.2f}"
        items_table.append([cant, Paragraph(desc, estilos['TextoNormal']), unit, desc_txt, total_it])

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
    subtotal_str = f"${venta.subtotal:,.2f}" if hasattr(venta, "subtotal") and venta.subtotal else f"${venta.total:,.2f}"
    descuento_str = f"-${venta.descuento_monto:,.2f}" if hasattr(venta, "descuento_monto") and venta.descuento_monto else "$0.00"
    iva_str = f"${venta.impuesto_monto:,.2f}" if hasattr(venta, "impuesto_monto") and venta.impuesto_monto else "$0.00"
    total_str = f"${venta.total:,.2f}"

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
    pagos_lista = getattr(venta, 'pagos', [])
    pagos_str = ", ".join([f"{p.metodo_etiqueta}: ${p.monto:,.2f}" for p in pagos_lista]) if pagos_lista else "Pago registrado"
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
    nombre_vet = f"Dr/a. {vet.nombre}" if vet else "Médico Veterinario"

    info_data = [
        [
            Paragraph(f"<b>PACIENTE:</b> <font color='#E53935'><b>{nombre_mascota}</b></font> ({especie_raza}) · {peso_str}", estilos['TextoNormal']),
            Paragraph(f"<b>TUTOR:</b> <b>{nombre_tutor}</b>", estilos['TextoNormal']),
        ],
        [
            Paragraph(f"<b>Diagnóstico:</b> {consulta.diagnostico}", estilos['TextoNormal']),
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
    receta_txt = consulta.receta_medica or consulta.plan_tratamiento or "Sin medicamentos prescritos."
    receta_data = [
        [
            Paragraph("<b><font color='#E53935' size=14>Rx</font> MEDICAMENTOS, DOSIS & INSTRUCCIONES DE USO</b>", estilos['TextoNegrita'])
        ],
        [
            Paragraph(receta_txt.replace(chr(10), "<br/>"), estilos['TextoReceta'])
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
    historia.append(Spacer(1, 20))
    firma_data = [
        [
            "",
            Paragraph(f"______________________________________<br/><b>{nombre_vet}</b><br/>Médico Veterinario Tratante<br/><font size=7 color='#64748B'>{clinica['nombre']} · Medicina & Spa Veterinario</font>", estilos['PiePagina'])
        ]
    ]
    t_firma = Table(firma_data, colWidths=[94 * mm, 90 * mm])
    t_firma.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
    ]))
    historia.append(KeepTogether(t_firma))

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

    # 3. Observaciones y Notas
    if cita_spa.notas_ingreso:
        historia.append(Paragraph(f"<b>Observaciones de Ingreso:</b> {cita_spa.notas_ingreso}", estilos['TextoNormal']))
        historia.append(Spacer(1, 6))

    if cita_spa.notas_salida:
        historia.append(Paragraph(f"<b>Recomendaciones del Estilista:</b> {cita_spa.notas_salida}", estilos['TextoNormal']))
        historia.append(Spacer(1, 6))

    historia.append(Spacer(1, 15))
    historia.append(Paragraph("¡Tu consentido quedó listo y hermoso para volver a casa! 🐾✂️🧼", estilos['PiePagina']))

    doc.build(historia)
    buffer.seek(0)
    return buffer
