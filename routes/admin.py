"""Administración: usuarios del sistema y configuración de la clínica."""

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_, select

from decorators import admin_required
from forms import PerfilMedicoForm, RazaForm, UsuarioCrearForm, UsuarioForm, construir_configuracion_form, valor_de_campo
from models import ESPECIES, GRUPOS_CONFIGURACION, ROLES, ConfiguracionSistema, Raza, Usuario, db
from utils import eliminar_firma_digital, guardar_firma_digital

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
        consulta = consulta.where(or_(Usuario.nombre.ilike(patron), Usuario.email.ilike(patron), Usuario.telefono.ilike(patron)))
    if rol in ROLES:
        consulta = consulta.where(Usuario.rol == rol)
    if estado == "activos":
        consulta = consulta.where(Usuario.activo.is_(True))
    elif estado == "inactivos":
        consulta = consulta.where(Usuario.activo.is_(False))
    consulta = consulta.order_by(Usuario.activo.desc(), Usuario.nombre)
    lista = db.session.execute(consulta).scalars().all()

    # Estadísticas globales del equipo para tarjetas KPI
    todos = db.session.execute(select(Usuario)).scalars().all()
    stats = {
        "total": len(todos),
        "activos": len([u for u in todos if u.activo]),
        "inactivos": len([u for u in todos if not u.activo]),
        "admins": len([u for u in todos if u.rol == "admin" and u.activo]),
        "clinicos": len([u for u in todos if u.rol in ("veterinario", "auxiliar") and u.activo]),
        "operativos": len([u for u in todos if u.rol in ("groomer", "cajero", "recepcion") and u.activo]),
    }

    return render_template(
        "admin/usuarios.html",
        usuarios=lista,
        filtro_texto=texto,
        filtro_rol=rol,
        filtro_estado=estado,
        stats=stats,
        ROLES=ROLES,
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
                tarjeta_profesional=(form.tarjeta_profesional.data or "").strip() or None,
                titulo_profesional=(form.titulo_profesional.data or "").strip() or None,
                especialidad=(form.especialidad.data or "").strip() or None,
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
                flash(f"Usuario {usuario.nombre} creado correctamente.", "success")
                return redirect(url_for("admin.usuarios"))
    return render_template("admin/usuario_form.html", form=form, usuario=None, ROLES=ROLES)


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
            usuario.tarjeta_profesional = (form.tarjeta_profesional.data or "").strip() or None
            usuario.titulo_profesional = (form.titulo_profesional.data or "").strip() or None
            usuario.especialidad = (form.especialidad.data or "").strip() or None
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
                flash(f"Usuario {usuario.nombre} actualizado correctamente.", "success")
                return redirect(url_for("admin.usuarios"))
    return render_template("admin/usuario_form.html", form=form, usuario=usuario, ROLES=ROLES)


# ---------------------------------------------------------------------------
# Perfil del Médico Veterinario Principal y Firma Digital
# ---------------------------------------------------------------------------


@bp.route("/medico-principal", methods=["GET", "POST"])
@login_required
@admin_required
def medico_principal():
    """Panel de configuración de la doctora/médico veterinaria principal del centro y su firma."""
    nombre_def = ConfiguracionSistema.obtener("medico_principal_nombre", "Dra. Daniela Pulido")
    titulo_def = ConfiguracionSistema.obtener("medico_principal_titulo", "Médica veterinaria")
    tp_def = ConfiguracionSistema.obtener("medico_principal_tp", "53214")
    esp_def = ConfiguracionSistema.obtener("medico_principal_especialidad", "Dpl. Dermatología de pequeñas especies")
    firma_def = ConfiguracionSistema.obtener("medico_principal_firma", "")

    # Buscar el usuario de la doctora
    usuario_vet = db.session.execute(
        select(Usuario).where(
            or_(
                Usuario.rol == "veterinario",
                Usuario.email == "veterinaria@sandiavet.com",
                Usuario.nombre.ilike("%Daniela%"),
            )
        )
    ).scalars().first()

    if usuario_vet:
        if not firma_def and usuario_vet.firma_digital:
            firma_def = usuario_vet.firma_digital

    form = PerfilMedicoForm()

    if request.method == "GET":
        form.nombre.data = nombre_def
        form.titulo_profesional.data = titulo_def
        form.tarjeta_profesional.data = tp_def
        form.especialidad.data = esp_def
        if usuario_vet:
            form.email.data = usuario_vet.email
            form.telefono.data = usuario_vet.telefono or ""

    if form.validate_on_submit():
        try:
            nombre = form.nombre.data.strip()
            titulo = form.titulo_profesional.data.strip()
            tp = form.tarjeta_profesional.data.strip()
            especialidad = (form.especialidad.data or "").strip()
            tel = (form.telefono.data or "").strip() or None
            email_val = (form.email.data or "").strip().lower()

            ConfiguracionSistema.establecer("medico_principal_nombre", nombre, current_user)
            ConfiguracionSistema.establecer("medico_principal_titulo", titulo, current_user)
            ConfiguracionSistema.establecer("medico_principal_tp", tp, current_user)
            ConfiguracionSistema.establecer("medico_principal_especialidad", especialidad, current_user)

            # Manejo de archivo o trazo de firma
            archivo_firma = form.firma_archivo.data
            canvas_firma = form.firma_canvas.data
            nueva_firma_nombre = None

            if archivo_firma and getattr(archivo_firma, "filename", ""):
                nueva_firma_nombre = guardar_firma_digital(archivo_firma)
            elif canvas_firma and canvas_firma.startswith("data:image"):
                nueva_firma_nombre = guardar_firma_digital(canvas_firma)

            if nueva_firma_nombre:
                firma_anterior = ConfiguracionSistema.obtener("medico_principal_firma")
                if firma_anterior and firma_anterior != nueva_firma_nombre:
                    eliminar_firma_digital(firma_anterior)
                ConfiguracionSistema.establecer("medico_principal_firma", nueva_firma_nombre, current_user)
                if usuario_vet:
                    usuario_vet.firma_digital = nueva_firma_nombre

            # Sincronizar en el registro del usuario veterinario
            if usuario_vet:
                usuario_vet.nombre = nombre
                usuario_vet.tarjeta_profesional = tp
                usuario_vet.titulo_profesional = titulo
                usuario_vet.especialidad = especialidad
                if tel:
                    usuario_vet.telefono = tel
                if email_val:
                    usuario_vet.email = email_val

            db.session.commit()
            ConfiguracionSistema.invalidar_cache()
            flash("Datos profesionales y firma guardados exitosamente.", "success")
            return redirect(url_for("admin.medico_principal"))
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("Error al guardar perfil del médico principal")
            flash(f"No se pudo guardar la información: {e}", "danger")

    firma_actual = ConfiguracionSistema.obtener("medico_principal_firma", "") or (usuario_vet.firma_digital if usuario_vet else "")
    url_firma_preview = None
    if firma_actual:
        if firma_actual.startswith("data:") or firma_actual.startswith("/"):
            url_firma_preview = firma_actual
        else:
            url_firma_preview = url_for("static", filename=f"uploads/firmas/{firma_actual}")

    return render_template(
        "admin/medico_perfil.html",
        form=form,
        configs={
            "nombre": nombre_def,
            "titulo": titulo_def,
            "tp": tp_def,
            "especialidad": esp_def,
            "firma": firma_actual,
        },
        usuario_vet=usuario_vet,
        url_firma_preview=url_firma_preview,
    )


@bp.route("/medico-principal/firma/eliminar", methods=["POST"])
@login_required
@admin_required
def medico_eliminar_firma():
    firma_actual = ConfiguracionSistema.obtener("medico_principal_firma", "")
    if firma_actual:
        eliminar_firma_digital(firma_actual)
        ConfiguracionSistema.establecer("medico_principal_firma", "", current_user)

    vets = db.session.execute(
        select(Usuario).where(
            or_(
                Usuario.rol == "veterinario",
                Usuario.email == "veterinaria@sandiavet.com",
                Usuario.nombre.ilike("%Daniela%"),
            )
        )
    ).scalars().all()
    for v in vets:
        if v.firma_digital:
            v.firma_digital = None

    db.session.commit()
    ConfiguracionSistema.invalidar_cache()
    flash("Firma digital eliminada correctamente.", "info")
    return redirect(url_for("admin.medico_principal"))



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

    texto = request.args.get("q", "").strip()
    pagina = request.args.get("page", 1, type=int)

    consulta = select(Raza).where(Raza.especie == especie)
    if texto:
        patron = f"%{texto}%"
        consulta = consulta.where(Raza.nombre.ilike(patron))
    consulta = consulta.order_by(Raza.activo.desc(), Raza.nombre)

    paginacion = db.paginate(consulta, page=pagina, per_page=12, error_out=False)

    conteos_por_especie = dict(
        db.session.execute(
            select(Raza.especie, func.count(Raza.id)).group_by(Raza.especie)
        ).all()
    )

    return render_template(
        "admin/razas.html",
        razas=paginacion.items,
        pagina=paginacion,
        especie=especie,
        ESPECIES=ESPECIES,
        filtro_texto=texto,
        conteos_por_especie=conteos_por_especie,
    )


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
