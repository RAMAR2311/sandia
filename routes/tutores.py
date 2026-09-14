"""Tutores (dueños de las mascotas): directorio, ficha y edición."""

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_, select

from decorators import admin_required, recepcion_required
from forms import AbonoCuentaTutorForm, CuentaTutorForm, SoloCsrfForm, TutorForm
from models import AbonoCuentaTutor, CuentaTutor, Tutor, db
from utils import hoy_bogota, normalizar_texto, solo_digitos

bp = Blueprint("tutores", __name__, url_prefix="/tutores")

POR_PAGINA = 30


def _consulta_busqueda(texto: str):
    """Filtro tolerante a tildes/mayúsculas por nombre, y por dígitos en teléfono o documento."""
    condiciones = []
    normalizado = normalizar_texto(texto)
    if normalizado:
        condiciones.append(Tutor.nombre_busqueda.ilike(f"%{normalizado}%"))
    digitos = solo_digitos(texto)
    if len(digitos) >= 3:
        patron = f"%{digitos}%"
        condiciones += [Tutor.telefono.ilike(patron), Tutor.whatsapp.ilike(patron), Tutor.numero_documento.ilike(patron)]
    return or_(*condiciones) if condiciones else None


def _documento_en_uso(numero: str | None, excluir_id: int | None = None) -> bool:
    if not numero:
        return False
    consulta = select(Tutor.id).where(Tutor.numero_documento == numero.strip())
    if excluir_id is not None:
        consulta = consulta.where(Tutor.id != excluir_id)
    return db.session.execute(consulta).first() is not None


def _aplicar_formulario(tutor: Tutor, form: TutorForm) -> None:
    tutor.tipo_documento = form.tipo_documento.data or None
    tutor.numero_documento = form.numero_documento.data
    tutor.nombre_completo = form.nombre_completo.data
    tutor.telefono = form.telefono.data
    tutor.whatsapp = form.whatsapp.data
    tutor.email = form.email.data
    tutor.direccion = form.direccion.data
    tutor.barrio = form.barrio.data
    tutor.notas = (form.notas.data or "").strip() or None
    tutor.acepta_recordatorios = form.acepta_recordatorios.data


@bp.route("/")
@login_required
def lista():
    texto = request.args.get("q", "").strip()
    estado = request.args.get("estado", "activos")
    pagina = request.args.get("page", 1, type=int)

    consulta = select(Tutor)
    filtro = _consulta_busqueda(texto)
    if filtro is not None:
        consulta = consulta.where(filtro)
    if estado == "activos":
        consulta = consulta.where(Tutor.activo.is_(True))
    elif estado == "inactivos":
        consulta = consulta.where(Tutor.activo.is_(False))
    consulta = consulta.order_by(Tutor.nombre_busqueda)
    paginacion = db.paginate(consulta, page=pagina, per_page=POR_PAGINA, error_out=False)
    return render_template("tutores/lista.html", pagina=paginacion, filtro_texto=texto, filtro_estado=estado)


@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@recepcion_required
def nuevo():
    form = TutorForm()
    if form.validate_on_submit():
        if _documento_en_uso(form.numero_documento.data):
            form.numero_documento.errors.append("Ya hay un tutor registrado con ese documento.")
        else:
            tutor = Tutor(creado_por_id=current_user.id)
            _aplicar_formulario(tutor, form)
            try:
                db.session.add(tutor)
                db.session.commit()
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Error al crear tutor")
                flash("No se pudo guardar el tutor. Inténtalo de nuevo.", "danger")
            else:
                flash(f"Tutor {tutor.nombre_completo} registrado.", "success")
                if request.args.get("siguiente") == "mascota":
                    return redirect(url_for("mascotas.nueva", tutor_id=tutor.id))
                return redirect(url_for("tutores.detalle", tutor_id=tutor.id))
    return render_template("tutores/form.html", form=form, tutor=None)


@bp.route("/<int:tutor_id>")
@login_required
def detalle(tutor_id):
    tutor = db.session.get(Tutor, tutor_id)
    if tutor is None:
        abort(404)
    return render_template("tutores/detalle.html", tutor=tutor, form_csrf=SoloCsrfForm())


@bp.route("/<int:tutor_id>/editar", methods=["GET", "POST"])
@login_required
@recepcion_required
def editar(tutor_id):
    tutor = db.session.get(Tutor, tutor_id)
    if tutor is None:
        abort(404)
    form = TutorForm(obj=tutor)
    if request.method == "GET":
        form.tipo_documento.data = tutor.tipo_documento or ""
    if form.validate_on_submit():
        if _documento_en_uso(form.numero_documento.data, excluir_id=tutor.id):
            form.numero_documento.errors.append("Ya hay otro tutor registrado con ese documento.")
        else:
            _aplicar_formulario(tutor, form)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Error al editar tutor %s", tutor_id)
                flash("No se pudieron guardar los cambios. Inténtalo de nuevo.", "danger")
            else:
                flash("Cambios guardados.", "success")
                return redirect(url_for("tutores.detalle", tutor_id=tutor.id))
    return render_template("tutores/form.html", form=form, tutor=tutor)


@bp.route("/<int:tutor_id>/estado", methods=["POST"])
@login_required
@recepcion_required
def cambiar_estado(tutor_id):
    """Activa o desactiva (borrado lógico) un tutor."""
    tutor = db.session.get(Tutor, tutor_id)
    if tutor is None:
        abort(404)
    form = SoloCsrfForm()
    if not form.validate_on_submit():
        abort(400)
    try:
        tutor.activo = not tutor.activo
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error al cambiar estado del tutor %s", tutor_id)
        flash("No se pudo cambiar el estado.", "danger")
    else:
        accion = "reactivado" if tutor.activo else "desactivado"
        current_app.logger.info("Tutor %s %s por %s", tutor.id, accion, current_user.email)
        flash(f"Tutor {accion}.", "success")
    return redirect(url_for("tutores.detalle", tutor_id=tutor.id))


# ---------------------------------------------------------------------------
# Cartera de tutores con crédito (fiado)
# ---------------------------------------------------------------------------


@bp.route("/<int:tutor_id>/cartera", methods=["GET"])
@login_required
@admin_required
def cartera(tutor_id):
    tutor = db.session.get(Tutor, tutor_id)
    if not tutor:
        abort(404)
    cuentas = db.session.execute(
        select(CuentaTutor).filter_by(tutor_id=tutor_id).order_by(CuentaTutor.fecha_factura.desc())
    ).scalars().all()
    saldo_total = sum((c.saldo_pendiente for c in cuentas if c.estado == "pendiente"), 0)
    return render_template(
        "tutores/cartera.html", tutor=tutor, cuentas=cuentas, saldo_total=saldo_total, form_abono=AbonoCuentaTutorForm()
    )


@bp.route("/<int:tutor_id>/cartera/nueva", methods=["GET", "POST"])
@login_required
@admin_required
def cartera_nueva(tutor_id):
    tutor = db.session.get(Tutor, tutor_id)
    if not tutor:
        abort(404)
    form = CuentaTutorForm(fecha_factura=hoy_bogota())
    if form.validate_on_submit():
        cuenta = CuentaTutor(
            tutor_id=tutor.id,
            descripcion=form.descripcion.data,
            monto_total=form.monto_total.data,
            fecha_factura=form.fecha_factura.data,
            fecha_vencimiento=form.fecha_vencimiento.data,
            creado_por_id=current_user.id,
        )
        try:
            db.session.add(cuenta)
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al registrar cargo a crédito")
            flash("No se pudo registrar el cargo.", "danger")
        else:
            flash("Cargo a crédito registrado.", "success")
            return redirect(url_for("tutores.cartera", tutor_id=tutor.id))
    return render_template("tutores/form_cartera.html", form=form, tutor=tutor)


@bp.route("/cartera/<int:cuenta_id>/abono", methods=["POST"])
@login_required
@admin_required
def cartera_abono(cuenta_id):
    cuenta = db.session.get(CuentaTutor, cuenta_id)
    if not cuenta:
        abort(404)
    form = AbonoCuentaTutorForm()
    if form.validate_on_submit():
        if form.monto.data > cuenta.saldo_pendiente:
            flash(f"El abono (${form.monto.data:,.2f}) supera el saldo pendiente (${cuenta.saldo_pendiente:,.2f}).", "danger")
        else:
            try:
                db.session.add(AbonoCuentaTutor(
                    cuenta_id=cuenta.id,
                    usuario_id=current_user.id,
                    monto=form.monto.data,
                    metodo_pago=form.metodo_pago.data,
                    notas=form.notas.data,
                ))
                db.session.flush()
                if cuenta.saldo_pendiente <= 0:
                    cuenta.estado = "pagada"
                db.session.commit()
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Error al registrar abono a cuenta %d", cuenta_id)
                flash("No se pudo registrar el abono.", "danger")
            else:
                flash("Abono registrado.", "success")
    return redirect(url_for("tutores.cartera", tutor_id=cuenta.tutor_id))
