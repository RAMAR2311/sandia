"""Tablero principal y registro de módulos visibles por rol."""

from datetime import timedelta

from flask import Blueprint, current_app, jsonify, render_template
from flask_login import current_user, login_required
from sqlalchemy import func, select, text
from sqlalchemy.orm import selectinload

from models import ROLES_TODOS, Mascota, VacunaMascota, db
from utils import hoy_bogota

bp = Blueprint("dashboard", __name__)

# Registro central de módulos. Cada fase agrega los suyos aquí y aparecen
# automáticamente en el tablero, en el menú superior y en la barra inferior
# del celular (``en_barra``). El orden de la lista es el orden de aparición.
MODULOS = [
    {
        "clave": "historias",
        "nombre": "Historias Clínicas",
        "descripcion": "Consultas SOAP, vacunación y desparasitación",
        "icono": "bi-journal-medical",
        "endpoint": "historias.lista",
        "roles": ("admin", "veterinario", "auxiliar"),
        "en_barra": True,
    },
    {
        "clave": "mascotas",
        "nombre": "Mascotas",
        "descripcion": "Fichas, historia y curva de peso",
        "icono": "bi-heart-fill",
        "endpoint": "mascotas.lista",
        "roles": ROLES_TODOS,
        "en_barra": True,
    },
    {
        "clave": "tutores",
        "nombre": "Tutores",
        "descripcion": "Directorio de dueños y contacto por WhatsApp",
        "icono": "bi-person-vcard-fill",
        "endpoint": "tutores.lista",
        "roles": ROLES_TODOS,
        "en_barra": True,
    },
    {
        "clave": "spa",
        "nombre": "Spa & Grooming",
        "descripcion": "Agenda de peluquería y notificaciones por WhatsApp",
        "icono": "bi-scissors",
        "endpoint": "spa.agenda",
        "roles": ("admin", "recepcion", "groomer"),
        "en_barra": True,
    },
    {
        "clave": "pos",
        "nombre": "Punto de Venta",
        "descripcion": "Terminal de cobro rápido y facturación",
        "icono": "bi-cart-check-fill",
        "endpoint": "pos.terminal",
        "roles": ("admin", "cajero"),
        "en_barra": True,
    },
    {
        "clave": "caja",
        "nombre": "Caja",
        "descripcion": "Apertura, cierre y arqueo de turno",
        "icono": "bi-cash-coin",
        "endpoint": "pos.caja_estado",
        "roles": ("admin", "cajero"),
        "en_barra": False,
    },
    {
        "clave": "inventario",
        "nombre": "Inventario",
        "descripcion": "Productos, variantes, lotes, kardex y alertas",
        "icono": "bi-box-seam-fill",
        "endpoint": "inventario.lista",
        "roles": ROLES_TODOS,
        "en_barra": True,
    },
    {
        "clave": "proveedores",
        "nombre": "Proveedores",
        "descripcion": "Directorio de proveedores y compras",
        "icono": "bi-truck",
        "endpoint": "inventario.proveedores_lista",
        "roles": ("admin",),
        "en_barra": False,
    },
    {
        "clave": "aprobaciones_precio",
        "nombre": "Aprobaciones de precio",
        "descripcion": "Solicitudes de cajeros para vender bajo el precio mínimo",
        "icono": "bi-shield-exclamation",
        "endpoint": "pos.aprobaciones_lista",
        "roles": ("admin",),
        "en_barra": False,
    },
    {
        "clave": "reportes",
        "nombre": "Reportes & Métricas",
        "descripcion": "Análisis financiero, volumen de ventas y valoración de stock",
        "icono": "bi-graph-up-arrow",
        "endpoint": "reportes.dashboard",
        "roles": ("admin",),
        "en_barra": False,
    },
    {
        "clave": "usuarios",
        "nombre": "Usuarios",
        "descripcion": "Cuentas y roles del personal",
        "icono": "bi-people-fill",
        "endpoint": "admin.usuarios",
        "roles": ("admin",),
        "en_barra": True,
    },
    {
        "clave": "configuracion",
        "nombre": "Configuración",
        "descripcion": "Datos de la clínica y ajustes del sistema",
        "icono": "bi-gear-fill",
        "endpoint": "admin.configuracion",
        "roles": ("admin",),
        "en_barra": True,
    },
    {
        "clave": "razas",
        "nombre": "Razas",
        "descripcion": "Catálogo de razas por especie",
        "icono": "bi-tags-fill",
        "endpoint": "admin.razas",
        "roles": ("admin",),
        "en_barra": False,
    },
    {
        "clave": "mi_cuenta",
        "nombre": "Mi cuenta",
        "descripcion": "Cambiar mi contraseña",
        "icono": "bi-person-lock",
        "endpoint": "auth.cambiar_password",
        "roles": ROLES_TODOS,
        "en_barra": False,
    },
]


def modulos_para(rol: str) -> list[dict]:
    """Módulos accesibles para un rol, en orden de aparición."""
    return [modulo for modulo in MODULOS if rol in modulo["roles"]]


def vacunas_por_vencer(limite_dias: int = 15, tope: int = 20):
    """Última aplicación de cada mascota activa cuya próxima dosis está vencida
    o vence dentro de ``limite_dias`` días (regla de negocio: recordatorios de
    vacunación con enlace directo de WhatsApp)."""
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


@bp.route("/")
@login_required
def index():
    vacunas_pendientes = []
    if current_user.rol in ("admin", "veterinario", "auxiliar"):
        vacunas_pendientes = vacunas_por_vencer()
    return render_template(
        "dashboard/index.html", modulos=modulos_para(current_user.rol), vacunas_pendientes=vacunas_pendientes
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
