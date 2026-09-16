"""Rutas públicas y administrativas para la gestión y confirmación del pago de mensualidad del servidor."""

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from models import ServerPayment, db
from utils import obtener_hora_bogota

bp = Blueprint("servidor", __name__, url_prefix="/servidor")

MESES_NOMBRES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]


@bp.route("/confirmar-pago", methods=["GET", "POST"])
def confirmar_pago():
    """Ruta de confirmación de pago protegida por token firmado y PIN de seguridad del proveedor."""
    token = request.args.get("token") or request.form.get("token")
    if not token:
        return render_template(
            "servidor/confirmar_pago.html",
            error_token="No se proporcionó un token de confirmación de pago.",
        ), 400

    serializer = URLSafeTimedSerializer(current_app.config["SECRET_KEY"])
    try:
        data = serializer.loads(token, salt="server-payment-salt")
        anio = int(data.get("anio"))
        mes = int(data.get("mes"))
    except (SignatureExpired, BadSignature, TypeError, ValueError, KeyError):
        return render_template(
            "servidor/confirmar_pago.html",
            error_token="El enlace o token de confirmación es inválido, está corrupto o ha expirado.",
        ), 400

    mes_nombre = MESES_NOMBRES[mes - 1] if 1 <= mes <= 12 else str(mes)
    pago = ServerPayment.query.filter_by(anio=anio, mes=mes, estado="pagado").first()

    # Si ya está registrado como pagado previamente
    if pago and request.method == "GET":
        return render_template(
            "servidor/confirmar_pago.html",
            token=token,
            anio=anio,
            mes=mes,
            mes_nombre=mes_nombre,
            ya_pagado=True,
            pago=pago,
        )

    # Procesamiento del formulario POST con PIN
    if request.method == "POST":
        pin_ingresado = request.form.get("pin", "").strip()
        pin_esperado = str(current_app.config.get("PIN_CONFIRMACION_SERVIDOR", "9876")).strip()

        if pin_ingresado == pin_esperado:
            if not pago:
                pago = ServerPayment(
                    anio=anio,
                    mes=mes,
                    estado="pagado",
                    fecha_pago=obtener_hora_bogota(),
                    observacion="Confirmado con PIN del proveedor vía WhatsApp",
                )
                db.session.add(pago)
            else:
                pago.estado = "pagado"
                pago.fecha_pago = obtener_hora_bogota()
                pago.observacion = "Re-confirmado con PIN del proveedor"
            db.session.commit()

            return render_template(
                "servidor/confirmar_pago.html",
                token=token,
                anio=anio,
                mes=mes,
                mes_nombre=mes_nombre,
                ya_pagado=True,
                recien_confirmado=True,
                pago=pago,
            )
        else:
            error_pin = "🚨 PIN de confirmación incorrecto. Inténtalo nuevamente."
            return render_template(
                "servidor/confirmar_pago.html",
                token=token,
                anio=anio,
                mes=mes,
                mes_nombre=mes_nombre,
                ya_pagado=False,
                error_pin=error_pin,
            ), 422

    return render_template(
        "servidor/confirmar_pago.html",
        token=token,
        anio=anio,
        mes=mes,
        mes_nombre=mes_nombre,
        ya_pagado=False,
    )
