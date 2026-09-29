"""Tutores (dueños de las mascotas): directorio, ficha y edición."""

import io
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_, select

from decorators import admin_required, recepcion_required
from forms import AbonoCuentaTutorForm, CuentaTutorForm, ImportarExcelForm, SoloCsrfForm, TutorForm
from models import AbonoCuentaTutor, CuentaTutor, TIPOS_DOCUMENTO, Tutor, db
from utils import ZONA_BOGOTA, hoy_bogota, normalizar_texto, normalizar_whatsapp, obtener_hora_bogota, solo_digitos

bp = Blueprint("tutores", __name__, url_prefix="/tutores")

POR_PAGINA = 12



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


# ---------------------------------------------------------------------------
# Importación masiva desde Excel
# ---------------------------------------------------------------------------


@bp.route("/plantilla-excel")
@login_required
@recepcion_required
def plantilla_excel():
    """Descarga la plantilla oficial en Excel (.xlsx) para importar tutores."""
    columnas = [
        "ID",
        "Tipo_Doc",
        "Documento",
        "Nombres",
        "Apellidos",
        "Correo",
        "Telefono",
        "WhatsApp",
        "Direccion",
        "Barrio",
        "Estado",
        "Fecha_Ingreso",
    ]
    ejemplos = [
        {
            "ID": 1,
            "Tipo_Doc": "CC",
            "Documento": "1010202020",
            "Nombres": "Miguel",
            "Apellidos": "Herrera",
            "Correo": "",
            "Telefono": "300 3034316",
            "WhatsApp": "",
            "Direccion": "alameda la felicidad",
            "Barrio": "",
            "Estado": "Activo",
            "Fecha_Ingreso": "10/01/2026 1:01",
        },
        {
            "ID": 2,
            "Tipo_Doc": "CC",
            "Documento": "1014249063",
            "Nombres": "SEBASTIAN LEONARDO",
            "Apellidos": "RAMIREZ CASTILLO",
            "Correo": "elnheodark@gmail.com",
            "Telefono": "",
            "WhatsApp": "573242100713",
            "Direccion": "Calle 51 # 3 - 90",
            "Barrio": "",
            "Estado": "Activo",
            "Fecha_Ingreso": "10/01/2026 18:01",
        },
    ]

    df = pd.DataFrame(ejemplos, columns=columnas)
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Tutores")
    out.seek(0)

    return send_file(
        out,
        as_attachment=True,
        download_name="plantilla_tutores_sandia.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@bp.route("/importar-excel", methods=["GET", "POST"])
@login_required
@recepcion_required
def importar_excel():
    """Importación masiva de tutores a partir de un archivo Excel (.xlsx)."""
    form = ImportarExcelForm()
    reporte = None

    if form.validate_on_submit():
        archivo = form.archivo.data
        if not archivo.filename.lower().endswith(".xlsx"):
            flash("El archivo debe tener extensión .xlsx", "danger")
            return render_template("tutores/importar.html", form=form, reporte=None)

        try:
            # Leer todas las columnas como string inicialmente para preservar ceros a la izquierda y formatos
            df = pd.read_excel(archivo.stream, engine="openpyxl", dtype=str)
        except Exception as exc:
            current_app.logger.exception("Error al leer archivo Excel de tutores")
            flash(f"No se pudo procesar el archivo Excel: {exc}", "danger")
            return render_template("tutores/importar.html", form=form, reporte=None)

        columnas_requeridas = ["Documento", "Nombres"]
        for col in columnas_requeridas:
            if col not in df.columns:
                flash(f"Falta la columna obligatoria '{col}' en el archivo Excel.", "danger")
                return render_template("tutores/importar.html", form=form, reporte=None)

        creados = 0
        actualizados = 0
        errores = []

        def _limpiar_celda(val):
            if val is None or pd.isna(val):
                return ""
            s = str(val).strip()
            return "" if s.lower() in ("nan", "none", "null") else s

        for indice, fila in df.iterrows():
            num_fila = indice + 2

            doc_raw = _limpiar_celda(fila.get("Documento"))
            nombres_raw = _limpiar_celda(fila.get("Nombres"))
            apellidos_raw = _limpiar_celda(fila.get("Apellidos"))

            # Validar nombres
            if not nombres_raw and not apellidos_raw:
                errores.append(f"Fila {num_fila}: Nombre y Apellidos vacíos.")
                continue

            nombre_completo = f"{nombres_raw} {apellidos_raw}".strip()

            tipo_doc_raw = _limpiar_celda(fila.get("Tipo_Doc")).upper()
            if tipo_doc_raw and tipo_doc_raw not in TIPOS_DOCUMENTO:
                tipo_doc_raw = "CC" if tipo_doc_raw in ("CEDULA", "CÉDULA") else "OTRO"
            elif not tipo_doc_raw:
                tipo_doc_raw = "CC" if doc_raw else None

            correo_raw = _limpiar_celda(fila.get("Correo")).lower() or None
            telefono_raw = _limpiar_celda(fila.get("Telefono")) or None
            whatsapp_raw = _limpiar_celda(fila.get("WhatsApp")) or None
            direccion_raw = _limpiar_celda(fila.get("Direccion")) or None
            barrio_raw = _limpiar_celda(fila.get("Barrio")) or None

            # Estado
            estado_raw = _limpiar_celda(fila.get("Estado")).lower()
            activo = estado_raw not in ("inactivo", "desactivado", "false", "0", "no")

            # Fecha de ingreso / registro
            fecha_ingreso_raw = _limpiar_celda(fila.get("Fecha_Ingreso"))
            fecha_registro = None
            if fecha_ingreso_raw:
                formatos = [
                    "%d/%m/%Y %H:%M",
                    "%d/%m/%Y %H:%M:%S",
                    "%Y-%m-%d %H:%M:%S",
                    "%Y-%m-%d %H:%M",
                    "%d-%m-%Y %H:%M",
                    "%d/%m/%Y",
                    "%Y-%m-%d",
                ]
                for fmt in formatos:
                    try:
                        dt = datetime.strptime(fecha_ingreso_raw, fmt)
                        fecha_registro = dt.replace(tzinfo=ZONA_BOGOTA)
                        break
                    except ValueError:
                        continue
            if not fecha_registro:
                fecha_registro = obtener_hora_bogota()

            try:
                tutor_existente = None
                # Si viene documento, buscar por documento
                if doc_raw:
                    tutor_existente = db.session.execute(
                        select(Tutor).where(Tutor.numero_documento == doc_raw)
                    ).scalar_one_or_none()

                # Si no se encontró por documento pero viene ID numérico, buscar por ID
                if not tutor_existente:
                    id_raw = _limpiar_celda(fila.get("ID"))
                    if id_raw.isdigit():
                        tutor_existente = db.session.get(Tutor, int(id_raw))

                if tutor_existente:
                    # Actualizar tutor existente
                    tutor_existente.nombre_completo = nombre_completo
                    if tipo_doc_raw:
                        tutor_existente.tipo_documento = tipo_doc_raw
                    if doc_raw:
                        tutor_existente.numero_documento = doc_raw
                    if telefono_raw:
                        tutor_existente.telefono = telefono_raw
                    if whatsapp_raw:
                        tutor_existente.whatsapp = whatsapp_raw
                    if correo_raw:
                        tutor_existente.email = correo_raw
                    if direccion_raw:
                        tutor_existente.direccion = direccion_raw
                    if barrio_raw:
                        tutor_existente.barrio = barrio_raw
                    tutor_existente.activo = activo
                    actualizados += 1
                else:
                    nuevo_tutor = Tutor(
                        tipo_documento=tipo_doc_raw,
                        numero_documento=doc_raw or None,
                        nombre_completo=nombre_completo,
                        telefono=telefono_raw,
                        whatsapp=whatsapp_raw,
                        email=correo_raw,
                        direccion=direccion_raw,
                        barrio=barrio_raw,
                        activo=activo,
                        fecha_registro=fecha_registro,
                        creado_por_id=current_user.id,
                    )
                    db.session.add(nuevo_tutor)
                    creados += 1

                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                current_app.logger.exception("Error al procesar fila %s de tutores", num_fila)
                errores.append(f"Fila {num_fila} ({nombre_completo}): {exc}")

        reporte = {
            "creados": creados,
            "actualizados": actualizados,
            "errores": errores,
            "total_procesados": creados + actualizados,
        }
        flash(
            f"Importación completada. Creados: {creados}, Actualizados: {actualizados}, Con error: {len(errores)}.",
            "success" if not errores else "warning",
        )

    return render_template("tutores/importar.html", form=form, reporte=reporte)

