"""VetCare · fábrica de la aplicación Flask.

Arranque estricto: si faltan ``SECRET_KEY`` o ``DATABASE_URL`` en el entorno la
aplicación se niega a iniciar. Nunca hay credenciales por defecto.
"""

import logging
import os
from datetime import timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

# Carga explícita del .env ANTES de leer cualquier variable de entorno.
load_dotenv()

import click  # noqa: E402
from flask import Flask, jsonify, render_template, request, url_for  # noqa: E402
from flask_login import LoginManager  # noqa: E402
from flask_migrate import Migrate  # noqa: E402
from flask_wtf.csrf import CSRFError, CSRFProtect  # noqa: E402
from sqlalchemy import select  # noqa: E402
from werkzeug.exceptions import HTTPException  # noqa: E402
from werkzeug.middleware.proxy_fix import ProxyFix  # noqa: E402

import utils  # noqa: E402
from models import ESPECIES, ROLES, SEXOS, TAMANOS, ConfiguracionSistema, Usuario, db  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent

login_manager = LoginManager()
migrate = Migrate()
csrf = CSRFProtect()


# ---------------------------------------------------------------------------
# Lectura estricta del entorno
# ---------------------------------------------------------------------------


def _requerir_env(nombre: str) -> str:
    valor = os.environ.get(nombre, "").strip()
    if not valor:
        raise RuntimeError(f"Falta {nombre}: defínela en el archivo .env (mira .env.example).")
    return valor


def _env_bool(nombre: str, predeterminado: bool = False) -> bool:
    valor = os.environ.get(nombre)
    if valor is None or valor.strip() == "":
        return predeterminado
    return valor.strip().lower() in ("1", "true", "si", "sí", "yes", "on")


def _env_int(nombre: str, predeterminado: int) -> int:
    valor = os.environ.get(nombre, "").strip()
    try:
        return int(valor) if valor else predeterminado
    except ValueError as exc:
        raise RuntimeError(f"{nombre} debe ser un número entero, no {valor!r}.") from exc


def _normalizar_url_postgres(url: str) -> str:
    """Acepta solo PostgreSQL y fuerza el driver psycopg 3."""
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    if not url.startswith("postgresql+psycopg://"):
        raise RuntimeError(
            "VetCare solo soporta PostgreSQL: DATABASE_URL debe empezar por postgresql+psycopg://"
        )
    return url


# ---------------------------------------------------------------------------
# Fábrica
# ---------------------------------------------------------------------------


def create_app(config_override: dict | None = None) -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")

    configuracion = {
        "SECRET_KEY": _requerir_env("SECRET_KEY"),
        "SQLALCHEMY_DATABASE_URI": _requerir_env("DATABASE_URL"),
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "SQLALCHEMY_ENGINE_OPTIONS": {
            "pool_pre_ping": True,
            # Toda sesión SQL trabaja en hora de Bogotá: date(fecha) agrupa por día colombiano.
            "connect_args": {"options": "-c timezone=America/Bogota"},
        },
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": _env_bool("SESSION_COOKIE_SECURE", False),
        "PERMANENT_SESSION_LIFETIME": timedelta(hours=_env_int("SESSION_HOURS", 12)),
        "MAX_CONTENT_LENGTH": _env_int("MAX_UPLOAD_MB", 20) * 1024 * 1024,
        "UPLOAD_FOLDER": str(BASE_DIR / os.environ.get("UPLOAD_FOLDER", "static/uploads")),
        # El token CSRF vive lo mismo que la sesión: un POS abierto horas no debe fallar.
        "WTF_CSRF_TIME_LIMIT": None,
        "NOMBRE_APP": "VetCare",
    }
    if config_override:
        configuracion.update(config_override)
    configuracion["SQLALCHEMY_DATABASE_URI"] = _normalizar_url_postgres(configuracion["SQLALCHEMY_DATABASE_URI"])
    app.config.update(configuracion)

    if _env_bool("BEHIND_PROXY", False):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True

    _configurar_logging(app)

    db.init_app(app)
    migrate.init_app(app, db, directory=str(BASE_DIR / "migrations"))
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Inicia sesión para continuar."
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def cargar_usuario(usuario_id):
        try:
            return db.session.get(Usuario, int(usuario_id))
        except (TypeError, ValueError):
            return None

    _registrar_blueprints(app)
    _registrar_plantillas(app)
    _registrar_manejadores_errores(app)
    _registrar_comandos(app)

    Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)
    return app


# ---------------------------------------------------------------------------
# Piezas de la fábrica
# ---------------------------------------------------------------------------


def _configurar_logging(app: Flask) -> None:
    nivel = getattr(logging, os.environ.get("LOG_LEVEL", "INFO").upper(), logging.INFO)
    app.logger.setLevel(nivel)
    ruta = os.environ.get("LOG_FILE", "").strip()
    if ruta and not app.testing:
        archivo = BASE_DIR / ruta
        archivo.parent.mkdir(parents=True, exist_ok=True)
        manejador = RotatingFileHandler(archivo, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
        manejador.setLevel(nivel)
        manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(module)s] %(message)s"))
        app.logger.addHandler(manejador)


def _registrar_blueprints(app: Flask) -> None:
    from routes.admin import bp as admin_bp
    from routes.agenda import bp as agenda_bp
    from routes.api import bp as api_bp
    from routes.gastos import bp as gastos_bp
    from routes.auth import bp as auth_bp
    from routes.dashboard import bp as dashboard_bp
    from routes.historias import bp as historias_bp
    from routes.inventario import bp as inventario_bp
    from routes.mascotas import bp as mascotas_bp
    from routes.pos import bp as pos_bp
    from routes.reportes import bp as reportes_bp
    from routes.spa import bp as spa_bp
    from routes.tutores import bp as tutores_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(tutores_bp)
    app.register_blueprint(mascotas_bp)
    app.register_blueprint(historias_bp)
    app.register_blueprint(inventario_bp)
    app.register_blueprint(pos_bp)
    app.register_blueprint(spa_bp)
    app.register_blueprint(reportes_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(agenda_bp)
    app.register_blueprint(gastos_bp)
    app.register_blueprint(api_bp)


def _registrar_plantillas(app: Flask) -> None:
    from routes.dashboard import modulos_para

    app.jinja_env.filters["cop"] = utils.formato_cop
    app.jinja_env.filters["fecha"] = utils.formato_fecha
    app.jinja_env.filters["fecha_hora"] = lambda valor: utils.formato_fecha(valor, con_hora=True)
    app.jinja_env.filters["hora"] = utils.formato_hora
    app.jinja_env.filters["fecha_larga"] = utils.fecha_larga
    app.jinja_env.filters["kg"] = utils.formato_kg

    def foto_mascota(mascota, mini=True):
        """URL de la foto (o miniatura) de una mascota; ``None`` si no tiene."""
        if not getattr(mascota, "foto", None):
            return None
        nombre = f"{utils.PREFIJO_MINIATURA}{mascota.foto}" if mini else mascota.foto
        return url_for("static", filename=f"uploads/mascotas/{nombre}")

    app.jinja_env.globals["foto_mascota"] = foto_mascota

    def static_url(nombre_archivo: str) -> str:
        """URL de un archivo estático con versión por fecha de modificación (evita caché vieja)."""
        ruta = Path(app.static_folder) / nombre_archivo
        try:
            version = int(ruta.stat().st_mtime)
        except OSError:
            version = 0
        return url_for("static", filename=nombre_archivo, v=version)

    app.jinja_env.globals["static_url"] = static_url

    @app.context_processor
    def inyectar_globales():
        from flask_login import current_user

        try:
            clinica = ConfiguracionSistema.datos_clinica()
        except Exception:  # la página de error debe renderizar aunque la base falle
            db.session.rollback()
            app.logger.exception("No se pudo leer la configuración de la clínica")
            clinica = {"nombre": "Sandía", "subtitulo": "Medicina y Spa Veterinario"}
        rol = current_user.rol if current_user.is_authenticated else None
        return {
            "clinica": clinica,
            "ahora": utils.obtener_hora_bogota(),
            "ROLES": ROLES,
            "ESPECIES": ESPECIES,
            "SEXOS": SEXOS,
            "TAMANOS": TAMANOS,
            "modulos_menu": modulos_para(rol) if rol else [],
        }


def _quiere_json() -> bool:
    return request.path.startswith("/api/") or request.is_json or request.accept_mimetypes.best == "application/json"


def _registrar_manejadores_errores(app: Flask) -> None:
    @app.errorhandler(CSRFError)
    def csrf_invalido(error):
        app.logger.warning("CSRF inválido en %s: %s", request.path, error.description)
        if _quiere_json():
            return jsonify(error="Sesión expirada o token inválido. Recarga la página."), 400
        return render_template(
            "errores/400.html",
            descripcion="El formulario expiró o el token de seguridad no es válido. Recarga la página e inténtalo de nuevo.",
        ), 400

    @app.errorhandler(HTTPException)
    def error_http(error):
        # 403, 404, 405, 429... se muestran tal cual, con su propia página.
        if _quiere_json():
            return jsonify(error=error.description, codigo=error.code), error.code
        plantilla = f"errores/{error.code}.html"
        if error.code not in (400, 403, 404, 429, 500):
            plantilla = "errores/generico.html"
        return render_template(plantilla, error=error), error.code

    @app.errorhandler(Exception)
    def error_no_controlado(error):
        # Regla de oro: una transacción fallida en PostgreSQL queda envenenada
        # hasta que alguien hace ROLLBACK explícito.
        db.session.rollback()
        app.logger.exception("Error no controlado en %s", request.path)
        if app.debug:
            # En desarrollo conviene ver el depurador / traza exacta.
            raise error
        if _quiere_json():
            return jsonify(error="Error interno del servidor."), 500
        return render_template("errores/500.html"), 500


def _registrar_comandos(app: Flask) -> None:
    @app.cli.command("crear-admin")
    @click.option("--nombre", prompt="Nombre completo")
    @click.option("--email", prompt="Correo electrónico")
    @click.option("--password", prompt="Contraseña", hide_input=True, confirmation_prompt=True)
    def crear_admin(nombre, email, password):
        """Crea un usuario administrador de forma interactiva."""
        from forms import LONGITUD_MINIMA_PASSWORD

        email = email.strip().lower()
        if "@" not in email or "." not in email.split("@")[-1]:
            raise click.ClickException("El correo no es válido.")
        if len(password) < LONGITUD_MINIMA_PASSWORD:
            raise click.ClickException(f"La contraseña debe tener al menos {LONGITUD_MINIMA_PASSWORD} caracteres.")
        try:
            existente = db.session.execute(select(Usuario).filter_by(email=email)).scalar_one_or_none()
            if existente is not None:
                raise click.ClickException(f"Ya existe un usuario con el correo {email}.")
            usuario = Usuario(nombre=nombre.strip(), email=email, rol="admin", activo=True)
            usuario.establecer_password(password)
            db.session.add(usuario)
            db.session.commit()
        except click.ClickException:
            db.session.rollback()
            raise
        except Exception as exc:
            db.session.rollback()
            raise click.ClickException(f"No se pudo crear el administrador: {exc}") from exc
        click.echo(f"Administrador {usuario.email} creado correctamente.")

    @app.cli.command("sembrar-datos")
    def comando_sembrar_datos():
        """Siembra datos de prueba realistas en todos los módulos de la aplicación."""
        from sembrar import sembrar
        sembrar()

    from commands import backup_cli
    app.cli.add_command(backup_cli)
