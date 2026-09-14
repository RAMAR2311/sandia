"""Administración: usuarios del sistema y configuración de la clínica."""

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_, select

from decorators import admin_required
from forms import RazaForm, UsuarioCrearForm, UsuarioForm, construir_configuracion_form, valor_de_campo
from models import ESPECIES, GRUPOS_CONFIGURACION, ROLES, ConfiguracionSistema, Raza, Usuario, db

bp = Blueprint("admin", __name__, url_prefix="/admin")


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------


def _hay_otro_admin_activo(excluir_id: int) -> bool:
    consulta = select(func.count(Usuario.id)).where(
        Usuario.rol == "admin", Usuario.activo.is_(True), Usuario.id != excluir_id
    )
    return db.session.execute(consulta).scalar_one() > 0


def _email_en_uso(email: str, excluir_id: int | None = None) -> bool:
    consulta = select(Usuario.id).where(Usuario.email == email.strip().lower())
    if excluir_id is not None:
        consulta = consulta.where(Usuario.id != excluir_id)
    return db.session.execute(consulta).first() is not None


@bp.route("/usuarios")
@login_required
@admin_required
def usuarios():
    texto = request.args.get("q", "").strip()
    rol = request.args.get("rol", "").strip()
    estado = request.args.get("estado", "activos")

    consulta = select(Usuario)
    if texto:
        patron = f"%{texto}%"
        consulta = consulta.where(or_(Usuario.nombre.ilike(patron), Usuario.email.ilike(patron)))
    if rol in ROLES:
        consulta = consulta.where(Usuario.rol == rol)
    if estado == "activos":
        consulta = consulta.where(Usuario.activo.is_(True))
    elif estado == "inactivos":
        consulta = consulta.where(Usuario.activo.is_(False))
    consulta = consulta.order_by(Usuario.activo.desc(), Usuario.nombre)
    lista = db.session.execute(consulta).scalars().all()
    return render_template(
        "admin/usuarios.html", usuarios=lista, filtro_texto=texto, filtro_rol=rol, filtro_estado=estado
    )


@bp.route("/usuarios/nuevo", methods=["GET", "POST"])
@login_required
@admin_required
def usuario_nuevo():
    form = UsuarioCrearForm()
    if form.validate_on_submit():
        if _email_en_uso(form.email.data):
            form.email.errors.append("Ya existe un usuario con ese correo.")
        else:
            usuario = Usuario(
                nombre=form.nombre.data.strip(),
                email=form.email.data,
                telefono=(form.telefono.data or "").strip() or None,
                rol=form.rol.data,
                activo=form.activo.data,
            )
            usuario.establecer_password(form.password.data)
            try:
                db.session.add(usuario)
                db.session.commit()
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Error al crear usuario %s", form.email.data)
                flash("No se pudo crear el usuario. Inténtalo de nuevo.", "danger")
            else:
                current_app.logger.info("Usuario %s creado por %s", usuario.email, current_user.email)
                flash(f"Usuario {usuario.nombre} creado.", "success")
                return redirect(url_for("admin.usuarios"))
    return render_template("admin/usuario_form.html", form=form, usuario=None)


@bp.route("/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def usuario_editar(usuario_id):
    usuario = db.session.get(Usuario, usuario_id)
    if usuario is None:
        abort(404)
    form = UsuarioForm(obj=usuario)
    if form.validate_on_submit():
        if _email_en_uso(form.email.data, excluir_id=usuario.id):
            form.email.errors.append("Ya existe otro usuario con ese correo.")
        elif usuario.id == current_user.id and (form.rol.data != "admin" or not form.activo.data):
            flash("No puedes quitarte el rol de administrador ni desactivar tu propia cuenta.", "warning")
        elif usuario.rol == "admin" and (form.rol.data != "admin" or not form.activo.data) and not _hay_otro_admin_activo(usuario.id):
            flash("No se puede: el sistema quedaría sin ningún administrador activo.", "warning")
        else:
            usuario.nombre = form.nombre.data.strip()
            usuario.email = form.email.data
            usuario.telefono = (form.telefono.data or "").strip() or None
            usuario.rol = form.rol.data
            usuario.activo = form.activo.data
            if form.password.data:
                usuario.establecer_password(form.password.data)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Error al editar usuario %s", usuario_id)
                flash("No se pudieron guardar los cambios. Inténtalo de nuevo.", "danger")
            else:
                current_app.logger.info("Usuario %s editado por %s", usuario.email, current_user.email)
                flash("Cambios guardados.", "success")
                return redirect(url_for("admin.usuarios"))
    return render_template("admin/usuario_form.html", form=form, usuario=usuario)


@bp.route("/usuarios/<int:usuario_id>/estado", methods=["POST"])
@login_required
@admin_required
def usuario_cambiar_estado(usuario_id):
    """Activa o desactiva un usuario (borrado lógico, nunca físico)."""
    usuario = db.session.get(Usuario, usuario_id)
    if usuario is None:
        abort(404)
    if usuario.id == current_user.id:
        flash("No puedes desactivar tu propia cuenta.", "warning")
        return redirect(url_for("admin.usuarios"))
    if usuario.activo and usuario.rol == "admin" and not _hay_otro_admin_activo(usuario.id):
        flash("No se puede desactivar: el sistema quedaría sin ningún administrador activo.", "warning")
        return redirect(url_for("admin.usuarios"))
    try:
        usuario.activo = not usuario.activo
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error al cambiar estado del usuario %s", usuario_id)
        flash("No se pudo cambiar el estado del usuario.", "danger")
    else:
        accion = "activado" if usuario.activo else "desactivado"
        current_app.logger.info("Usuario %s %s por %s", usuario.email, accion, current_user.email)
        flash(f"Usuario {usuario.nombre} {accion}.", "success")
    return redirect(url_for("admin.usuarios", estado=request.args.get("estado", "activos")))


# ---------------------------------------------------------------------------
# Configuración del sistema
# ---------------------------------------------------------------------------


@bp.route("/configuracion", methods=["GET", "POST"])
@login_required
@admin_required
def configuracion():
    items = ConfiguracionSistema.listar()
    form = construir_configuracion_form(items)
    if form.validate_on_submit():
        try:
            for item in items:
                campo = getattr(form, item.clave)
                ConfiguracionSistema.establecer(item.clave, valor_de_campo(campo, item.tipo), current_user)
            db.session.commit()
        except Exception:
            db.session.rollback()
            ConfiguracionSistema.invalidar_cache()
            current_app.logger.exception("Error al guardar la configuración")
            flash("No se pudo guardar la configuración. Inténtalo de nuevo.", "danger")
        else:
            current_app.logger.info("Configuración actualizada por %s", current_user.email)
            flash("Configuración guardada.", "success")
            return redirect(url_for("admin.configuracion"))

    grupos = []
    for clave_grupo, titulo in GRUPOS_CONFIGURACION.items():
        campos = [getattr(form, item.clave) for item in items if item.grupo == clave_grupo]
        if campos:
            grupos.append((titulo, campos))
    return render_template("admin/configuracion.html", form=form, grupos=grupos)


# ---------------------------------------------------------------------------
# Catálogo de razas
# ---------------------------------------------------------------------------


def _raza_en_uso(especie: str, nombre: str, excluir_id: int | None = None) -> bool:
    consulta = select(Raza.id).where(Raza.especie == especie, func.lower(Raza.nombre) == nombre.strip().lower())
    if excluir_id is not None:
        consulta = consulta.where(Raza.id != excluir_id)
    return db.session.execute(consulta).first() is not None


@bp.route("/razas")
@login_required
@admin_required
def razas():
    especie = request.args.get("especie", "canino")
    if especie not in ESPECIES:
        especie = "canino"
    lista = db.session.execute(
        select(Raza).where(Raza.especie == especie).order_by(Raza.activo.desc(), Raza.nombre)
    ).scalars().all()
    return render_template("admin/razas.html", razas=lista, especie=especie, ESPECIES=ESPECIES)


@bp.route("/razas/nueva", methods=["GET", "POST"])
@login_required
@admin_required
def raza_nueva():
    form = RazaForm(especie=request.args.get("especie", "canino"))
    if form.validate_on_submit():
        if _raza_en_uso(form.especie.data, form.nombre.data):
            form.nombre.errors.append("Esa raza ya existe para la especie.")
        else:
            raza = Raza(especie=form.especie.data, nombre=form.nombre.data, activo=form.activo.data)
            try:
                db.session.add(raza)
                db.session.commit()
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Error al crear raza")
                flash("No se pudo guardar la raza.", "danger")
            else:
                flash(f"Raza {raza.nombre} agregada.", "success")
                return redirect(url_for("admin.razas", especie=raza.especie))
    return render_template("admin/raza_form.html", form=form, raza=None)


@bp.route("/razas/<int:raza_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def raza_editar(raza_id):
    raza = db.session.get(Raza, raza_id)
    if raza is None:
        abort(404)
    form = RazaForm(obj=raza)
    if form.validate_on_submit():
        if _raza_en_uso(form.especie.data, form.nombre.data, excluir_id=raza.id):
            form.nombre.errors.append("Esa raza ya existe para la especie.")
        else:
            raza.especie = form.especie.data
            raza.nombre = form.nombre.data
            raza.activo = form.activo.data
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Error al editar raza %s", raza_id)
                flash("No se pudieron guardar los cambios.", "danger")
            else:
                flash("Cambios guardados.", "success")
                return redirect(url_for("admin.razas", especie=raza.especie))
    return render_template("admin/raza_form.html", form=form, raza=raza)
