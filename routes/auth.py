"""Autenticación: inicio y cierre de sesión, cambio de contraseña."""

from urllib.parse import urlparse

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from sqlalchemy import select

from forms import CambiarPasswordForm, LoginForm
from models import IntentoLogin, Usuario, db
from utils import obtener_hora_bogota

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _ip_cliente() -> str:
    # Con BEHIND_PROXY=true, ProxyFix ya dejó en remote_addr la IP real del cliente.
    return (request.remote_addr or "desconocida")[:45]


def _destino_seguro(siguiente: str | None) -> str:
    """Solo acepta rutas relativas del mismo sitio para evitar redirecciones abiertas."""
    if not siguiente:
        return url_for("dashboard.index")
    partes = urlparse(siguiente)
    if partes.scheme or partes.netloc or not siguiente.startswith("/") or siguiente.startswith("//"):
        return url_for("dashboard.index")
    return siguiente


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = LoginForm()
    if form.validate_on_submit():
        ip = _ip_cliente()
        email = form.email.data.strip().lower()
        try:
            if IntentoLogin.bloqueado(ip):
                current_app.logger.warning("Login bloqueado por exceso de intentos desde %s", ip)
                flash(
                    f"Demasiados intentos fallidos. Espera {IntentoLogin.VENTANA_MINUTOS} minutos e inténtalo de nuevo.",
                    "danger",
                )
                return render_template("auth/login.html", form=form), 429

            usuario = db.session.execute(select(Usuario).filter_by(email=email)).scalar_one_or_none()
            exitoso = usuario is not None and usuario.activo and usuario.verificar_password(form.password.data)
            IntentoLogin.registrar(ip, email, exitoso)
            if exitoso:
                usuario.ultimo_acceso = obtener_hora_bogota()
                IntentoLogin.limpiar_antiguos()
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al procesar el inicio de sesión")
            flash("Ocurrió un error al iniciar sesión. Inténtalo de nuevo.", "danger")
            return render_template("auth/login.html", form=form), 500

        if exitoso:
            session.permanent = True
            login_user(usuario)
            current_app.logger.info("Inicio de sesión: %s (%s)", usuario.email, usuario.rol)
            return redirect(_destino_seguro(request.args.get("next")))

        current_app.logger.info("Inicio de sesión fallido para %s desde %s", email, ip)
        flash("Correo o contraseña incorrectos.", "danger")

    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada. ¡Hasta pronto!", "success")
    return redirect(url_for("auth.login"))


@bp.route("/cambiar-password", methods=["GET", "POST"])
@login_required
def cambiar_password():
    form = CambiarPasswordForm()
    if form.validate_on_submit():
        if not current_user.verificar_password(form.password_actual.data):
            form.password_actual.errors.append("La contraseña actual no es correcta.")
        else:
            try:
                current_user.establecer_password(form.password_nueva.data)
                db.session.commit()
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Error al cambiar la contraseña de %s", current_user.email)
                flash("No se pudo cambiar la contraseña. Inténtalo de nuevo.", "danger")
            else:
                flash("Contraseña actualizada correctamente.", "success")
                return redirect(url_for("dashboard.index"))
    return render_template("auth/cambiar_password.html", form=form)
