"""Tablero principal y registro de módulos visibles por rol."""

from flask import Blueprint, current_app, jsonify, render_template
from flask_login import current_user, login_required
from sqlalchemy import text

from models import ROLES_TODOS, db

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
        "roles": ROLES_TODOS,
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
        "roles": ROLES_TODOS,
        "en_barra": True,
    },
    {
        "clave": "pos",
        "nombre": "Punto de Venta",
        "descripcion": "Terminal de cobro rápido y facturación",
        "icono": "bi-cart-check-fill",
        "endpoint": "pos.terminal",
        "roles": ROLES_TODOS,
        "en_barra": True,
    },
    {
        "clave": "caja",
        "nombre": "Caja",
        "descripcion": "Apertura, cierre y arqueo de turno",
        "icono": "bi-cash-coin",
        "endpoint": "pos.caja_estado",
        "roles": ROLES_TODOS,
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
        "roles": ("admin", "recepcion", "auxiliar"),
        "en_barra": False,
    },
    {
        "clave": "reportes",
        "nombre": "Reportes & Métricas",
        "descripcion": "Análisis financiero, volumen de ventas y valoración de stock",
        "icono": "bi-graph-up-arrow",
        "endpoint": "reportes.dashboard",
        "roles": ("admin", "recepcion", "veterinario"),
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


@bp.route("/")
@login_required
def index():
    return render_template("dashboard/index.html", modulos=modulos_para(current_user.rol))


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
