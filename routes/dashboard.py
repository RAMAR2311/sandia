"""Tablero principal y registro de módulos visibles por rol."""

from datetime import datetime, time, timedelta
from decimal import Decimal

from flask import Blueprint, current_app, jsonify, render_template
from flask_login import current_user, login_required
from sqlalchemy import func, select, text
from sqlalchemy.orm import selectinload

from forms import SoloCsrfForm
from models import (
    ROLES_TODOS,
    Cita,
    CitaSpa,
    Mascota,
    Producto,
    TurnoCaja,
    VacunaMascota,
    Venta,
    db,
)
from utils import ZONA_BOGOTA, enlace_whatsapp, hoy_bogota, obtener_hora_bogota

bp = Blueprint("dashboard", __name__)

# Registro central de módulos. Cada fase agrega los suyos aquí y aparecen
# automáticamente en el tablero, en el menú superior y en la barra inferior
# del celular (``en_barra``). El orden de la lista es el orden de aparición.
MODULOS = [
    # Módulos esenciales (Operación diaria de la clínica y tienda)
    {
        "clave": "historias",
        "nombre": "Historias Clínicas",
        "descripcion": "Consultas SOAP, vacunación y desparasitación",
        "icono": "bi-journal-medical",
        "endpoint": "historias.lista",
        "roles": ("admin", "veterinario", "auxiliar"),
        "en_barra": True,
        "esencial": True,
    },
    {
        "clave": "mascotas",
        "nombre": "Mascotas",
        "descripcion": "Fichas, historia y curva de peso",
        "icono": "bi-heart-fill",
        "endpoint": "mascotas.lista",
        "roles": ROLES_TODOS,
        "en_barra": True,
        "esencial": True,
    },
    {
        "clave": "tutores",
        "nombre": "Tutores",
        "descripcion": "Directorio de dueños y contacto por WhatsApp",
        "icono": "bi-person-vcard-fill",
        "endpoint": "tutores.lista",
        "roles": ROLES_TODOS,
        "en_barra": True,
        "esencial": True,
    },
    {
        "clave": "agenda",
        "nombre": "Agenda",
        "descripcion": "Citas médicas, vacunación, cirugía y controles",
        "icono": "bi-calendar-week-fill",
        "endpoint": "agenda.lista",
        "roles": ("admin", "recepcion", "auxiliar", "veterinario"),
        "en_barra": False,
        "esencial": True,
    },
    {
        "clave": "spa",
        "nombre": "Spa & Grooming",
        "descripcion": "Agenda de peluquería y notificaciones por WhatsApp",
        "icono": "bi-scissors",
        "endpoint": "spa.agenda",
        "roles": ("admin", "recepcion", "groomer"),
        "en_barra": True,
        "esencial": True,
    },
    {
        "clave": "pos",
        "nombre": "Punto de Venta",
        "descripcion": "Terminal de cobro rápido y facturación",
        "icono": "bi-cart-check-fill",
        "endpoint": "pos.terminal",
        "roles": ("admin", "cajero"),
        "en_barra": True,
        "esencial": True,
    },
    {
        "clave": "caja",
        "nombre": "Caja",
        "descripcion": "Apertura, cierre y arqueo de turno",
        "icono": "bi-cash-coin",
        "endpoint": "pos.caja_estado",
        "roles": ("admin", "cajero"),
        "en_barra": False,
        "esencial": True,
    },
    {
        "clave": "inventario",
        "nombre": "Inventario",
        "descripcion": "Productos, variantes, lotes, kardex y alertas",
        "icono": "bi-box-seam-fill",
        "endpoint": "inventario.lista",
        "roles": ROLES_TODOS,
        "en_barra": True,
        "esencial": True,
    },

    # Módulos secundarios / administrativos
    {
        "clave": "reportes",
        "nombre": "Reportes & Métricas",
        "descripcion": "Análisis financiero, volumen de ventas y valoración de stock",
        "icono": "bi-graph-up-arrow",
        "endpoint": "reportes.dashboard",
        "roles": ("admin",),
        "en_barra": False,
        "esencial": False,
    },
    {
        "clave": "gastos",
        "nombre": "Gastos",
        "descripcion": "Gastos diarios y costos indirectos",
        "icono": "bi-receipt-cutoff",
        "endpoint": "gastos.lista",
        "roles": ("admin",),
        "en_barra": False,
        "esencial": False,
    },
    {
        "clave": "cuentas_por_pagar",
        "nombre": "Cuentas por pagar",
        "descripcion": "Facturas a crédito con proveedores",
        "icono": "bi-cash-stack",
        "endpoint": "inventario.cuentas_por_pagar",
        "roles": ("admin",),
        "en_barra": False,
        "esencial": False,
    },
    {
        "clave": "proveedores",
        "nombre": "Proveedores",
        "descripcion": "Directorio de proveedores y compras",
        "icono": "bi-truck",
        "endpoint": "inventario.proveedores_lista",
        "roles": ("admin",),
        "en_barra": False,
        "esencial": False,
    },
    {
        "clave": "usuarios",
        "nombre": "Usuarios",
        "descripcion": "Cuentas y roles del personal",
        "icono": "bi-people-fill",
        "endpoint": "admin.usuarios",
        "roles": ("admin",),
        "en_barra": True,
        "esencial": False,
    },
    {
        "clave": "configuracion",
        "nombre": "Configuración",
        "descripcion": "Datos de la clínica y ajustes del sistema",
        "icono": "bi-gear-fill",
        "endpoint": "admin.configuracion",
        "roles": ("admin",),
        "en_barra": True,
        "esencial": False,
    },
    {
        "clave": "razas",
        "nombre": "Razas",
        "descripcion": "Catálogo de razas por especie",
        "icono": "bi-tags-fill",
        "endpoint": "admin.razas",
        "roles": ("admin",),
        "en_barra": False,
        "esencial": False,
    },
    {
        "clave": "mi_cuenta",
        "nombre": "Mi cuenta",
        "descripcion": "Cambiar mi contraseña",
        "icono": "bi-person-lock",
        "endpoint": "auth.cambiar_password",
        "roles": ROLES_TODOS,
        "en_barra": False,
        "esencial": False,
    },
]


def modulos_para(rol: str) -> list[dict]:
    """Módulos accesibles para un rol, en orden de aparición."""
    return [modulo for modulo in MODULOS if rol in modulo["roles"]]


def vacunas_por_vencer(limite_dias: int = 15, tope: int = 20):
    """Última aplicación de cada mascota activa cuya próxima dosis está vencida
    o vence dentro de ``limite_dias`` días (regla de negocio: recordatorios de
    vacunación con enlace directo de WhatsApp)."""
    try:
        ultima_por_mascota = (
            select(VacunaMascota.mascota_id, func.max(VacunaMascota.fecha_aplicacion).label("ultima_fecha"))
            .group_by(VacunaMascota.mascota_id)
            .subquery()
        )
        limite = hoy_bogota() + timedelta(days=limite_dias)
        consulta = (
            select(VacunaMascota)
            .join(
                ultima_por_mascota,
                (VacunaMascota.mascota_id == ultima_por_mascota.c.mascota_id)
                & (VacunaMascota.fecha_aplicacion == ultima_por_mascota.c.ultima_fecha),
            )
            .join(Mascota, VacunaMascota.mascota_id == Mascota.id)
            .options(selectinload(VacunaMascota.mascota), selectinload(VacunaMascota.tutor))
            .where(Mascota.activo.is_(True), Mascota.fallecido.is_(False), VacunaMascota.fecha_proxima <= limite)
            .order_by(VacunaMascota.fecha_proxima.asc())
            .limit(tope)
        )
        return db.session.execute(consulta).scalars().all()
    except Exception:
        db.session.rollback()
        return []


def obtener_mascotas_pendientes_recogida():
    """Obtiene citas de spa listas para entrega y calcula tiempo transcurrido y nivel de urgencia."""
    try:
        ahora = obtener_hora_bogota()
        citas = db.session.execute(
            select(CitaSpa)
            .filter_by(estado="listo_recogida")
            .options(
                selectinload(CitaSpa.mascota),
                selectinload(CitaSpa.tutor),
                selectinload(CitaSpa.servicio_spa),
                selectinload(CitaSpa.venta),
                selectinload(CitaSpa.groomer),
            )
            .order_by(CitaSpa.fecha_hora.asc())
        ).scalars().all()

        resultado = []
        for c in citas:
            momento_listo = c.fecha_listo or (c.fecha_hora + timedelta(minutes=c.duracion_minutos))
            if momento_listo.tzinfo is None:
                momento_listo = momento_listo.replace(tzinfo=ZONA_BOGOTA)

            diff = ahora - momento_listo
            minutos = max(0, int(diff.total_seconds() // 60))

            if minutos >= 90:
                nivel = "critico"
                etiqueta = f"Hace {minutos // 60}h {minutos % 60}m"
            elif minutos >= 45:
                nivel = "alerta"
                etiqueta = f"Hace {minutos} min"
            else:
                nivel = "normal"
                etiqueta = f"Hace {minutos} min" if minutos > 0 else "Hace instantes"

            nombre_tutor = c.tutor.nombre_completo if c.tutor else "Estimado/a cliente"
            nombre_mascota = c.mascota.nombre if c.mascota else "su mascota"
            tel = c.tutor.whatsapp or c.tutor.telefono if c.tutor else ""
            
            msg_wa = (
                f"¡Hola {nombre_tutor}! 👋🍉 Te saludamos desde *Sandía Medicina & Spa Veterinario*.\n\n"
                f"Te recordamos con mucho cariño que *{nombre_mascota}* ya finalizó su servicio de *{c.servicio_spa.nombre if c.servicio_spa else 'Grooming'}* "
                f"y se encuentra listo/a y esperándote en la sede para su recogida 🐾✨.\n\n"
                f"¡Te esperamos!"
            )
            wa_url = enlace_whatsapp(tel, msg_wa) if tel else ""

            resultado.append({
                "cita": c,
                "minutos_espera": minutos,
                "etiqueta_tiempo": etiqueta,
                "nivel_alerta": nivel,
                "momento_listo": momento_listo,
                "wa_url": wa_url,
                "pagado": bool(c.venta_id),
            })

        resultado.sort(key=lambda x: x["minutos_espera"], reverse=True)
        return resultado
    except Exception:
        db.session.rollback()
        return []


@bp.route("/")
@login_required
def index():
    vacunas_pendientes = []
    if current_user.rol in ("admin", "veterinario", "auxiliar"):
        vacunas_pendientes = vacunas_por_vencer()

    mascotas_recogida = obtener_mascotas_pendientes_recogida()
    form_csrf = SoloCsrfForm()

    hoy = hoy_bogota()
    inicio_dia = datetime.combine(hoy, time.min, tzinfo=ZONA_BOGOTA)
    fin_dia = datetime.combine(hoy, time.max, tzinfo=ZONA_BOGOTA)

    # Métricas clave del día según rol
    metricas = {
        "citas_hoy": 0,
        "ventas_hoy": Decimal("0.00"),
        "stock_critico": 0,
        "turno_abierto": False,
        "turno_caja_actual": None,
        "total_pacientes": 0,
    }

    try:
        # Citas programadas hoy (médicas o spa)
        citas_count = db.session.execute(
            select(func.count(Cita.id)).where(Cita.fecha_hora >= inicio_dia, Cita.fecha_hora <= fin_dia)
        ).scalar() or 0
        citas_spa_count = db.session.execute(
            select(func.count(CitaSpa.id)).where(CitaSpa.fecha_hora >= inicio_dia, CitaSpa.fecha_hora <= fin_dia)
        ).scalar() or 0
        metricas["citas_hoy"] = citas_count + citas_spa_count

        # Total pacientes activos
        metricas["total_pacientes"] = db.session.execute(
            select(func.count(Mascota.id)).where(Mascota.activo.is_(True), Mascota.fallecido.is_(False))
        ).scalar() or 0

        # Turno de caja abierto (para admin y cajero)
        if current_user.rol in ("admin", "cajero"):
            turno = db.session.execute(
                select(TurnoCaja)
                .where(TurnoCaja.usuario_id == current_user.id, TurnoCaja.estado.in_(("abierta", "abierto")))
                .order_by(TurnoCaja.fecha_apertura.desc())
            ).scalars().first()
            if turno:
                metricas["turno_abierto"] = True
                metricas["turno_caja_actual"] = turno

        # Ventas de hoy (para admin)
        if current_user.rol == "admin":
            ventas_hoy_val = db.session.execute(
                select(func.coalesce(func.sum(Venta.total), Decimal("0.00")))
                .where(Venta.fecha_venta >= inicio_dia, Venta.fecha_venta <= fin_dia, Venta.estado == "completada")
            ).scalar()
            metricas["ventas_hoy"] = ventas_hoy_val or Decimal("0.00")

        # Alertas de stock crítico
        if current_user.rol in ("admin", "veterinario", "auxiliar", "cajero"):
            productos_alerta = db.session.execute(
                select(func.count(Producto.id)).where(
                    Producto.activo.is_(True),
                    Producto.tipo == "producto",
                    Producto.cantidad_stock <= Producto.stock_minimo,
                )
            ).scalar() or 0
            metricas["stock_critico"] = productos_alerta
    except Exception:
        pass

    todos_modulos = modulos_para(current_user.rol)
    modulos_esenciales = [m for m in todos_modulos if m.get("esencial", False)]
    modulos_secundarios = [m for m in todos_modulos if not m.get("esencial", False)]

    return render_template(
        "dashboard/index.html",
        modulos=todos_modulos,
        modulos_esenciales=modulos_esenciales,
        modulos_secundarios=modulos_secundarios,
        vacunas_pendientes=vacunas_pendientes,
        mascotas_recogida=mascotas_recogida,
        form_csrf=form_csrf,
        metricas=metricas,
    )


@bp.route("/salud")
def salud():
    """Comprobación de vida para Nginx/monitoreo: verifica la conexión a la base."""
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Comprobación de salud fallida")
        return jsonify(estado="error", base_datos="sin conexión"), 503
    return jsonify(estado="ok", base_datos="ok")
