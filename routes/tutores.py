"""Tutores (dueños de las mascotas): directorio, ficha y edición."""

import io
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_, select

from decorators import admin_required, recepcion_required
from forms import AbonoCuentaTutorForm, CuentaTutorForm, ImportarExcelForm, SoloCsrfForm, TutorForm
from models import AbonoCuentaTutor, CuentaTutor, LoteImportacion, TIPOS_DOCUMENTO, Tutor, db
from utils import ZONA_BOGOTA, hoy_bogota, leer_archivo_tabular, normalizar_texto, normalizar_whatsapp, obtener_hora_bogota, solo_digitos

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
    """Importación masiva de tutores a partir de archivo Excel (.xlsx) o CSV (.csv)."""
    form = ImportarExcelForm()
    form_csrf = SoloCsrfForm()
    reporte = None

    if form.validate_on_submit():
        archivo = form.archivo.data
        try:
            df = leer_archivo_tabular(archivo)
        except Exception as exc:
            current_app.logger.exception("Error al leer archivo de tutores")
            flash(f"No se pudo procesar el archivo: {exc}", "danger")
            return redirect(url_for("tutores.importar_excel"))

        # Limpiar nombres de columnas
        df.columns = [str(c).strip() for c in df.columns]

        # Mapeo flexible de nombres de columnas
        col_doc = next((c for c in df.columns if c.lower() in ("documento", "doc", "numero_documento", "cedula")), None)
        col_nom = next((c for c in df.columns if c.lower() in ("nombres", "nombre", "nombre_completo")), None)

        if not col_nom:
            flash("Falta la columna obligatoria de nombres ('Nombres' o 'Nombre') en el archivo.", "danger")
            return redirect(url_for("tutores.importar_excel"))

        col_ape = next((c for c in df.columns if c.lower() in ("apellidos", "apellido")), None)
        col_tipo_doc = next((c for c in df.columns if c.lower() in ("tipo_doc", "tipo_documento", "tipodoc")), None)
        col_correo = next((c for c in df.columns if c.lower() in ("correo", "email", "correo_electronico")), None)
        col_tel = next((c for c in df.columns if c.lower() in ("telefono", "tel", "celular")), None)
        col_ws = next((c for c in df.columns if c.lower() in ("whatsapp", "ws")), None)
        col_dir = next((c for c in df.columns if c.lower() in ("direccion", "dirección", "domicilio")), None)
        col_barrio = next((c for c in df.columns if c.lower() in ("barrio", "sector")), None)
        col_estado = next((c for c in df.columns if c.lower() in ("estado", "activo")), None)
        col_fecha = next((c for c in df.columns if c.lower() in ("fecha_ingreso", "fecha", "fecha_registro")), None)
        col_id = next((c for c in df.columns if c.lower() in ("id", "id_tutor", "codigo")), None)

        creados = 0
        actualizados = 0
        errores = []
        lote_uuid = str(uuid.uuid4())

        def _limpiar_celda(val):
            if val is None or pd.isna(val):
                return ""
            s = str(val).strip()
            return "" if s.lower() in ("nan", "none", "null") else s

        try:
            for indice, fila in df.iterrows():
                num_fila = indice + 2

                doc_raw = _limpiar_celda(fila.get(col_doc)) if col_doc else ""
                nombres_raw = _limpiar_celda(fila.get(col_nom))
                apellidos_raw = _limpiar_celda(fila.get(col_ape)) if col_ape else ""

                if not nombres_raw and not apellidos_raw:
                    errores.append(f"Fila {num_fila}: Nombre y Apellidos vacíos.")
                    continue

                nombre_completo = f"{nombres_raw} {apellidos_raw}".strip()

                tipo_doc_raw = _limpiar_celda(fila.get(col_tipo_doc)).upper() if col_tipo_doc else ""
                if tipo_doc_raw and tipo_doc_raw not in TIPOS_DOCUMENTO:
                    tipo_doc_raw = "CC" if tipo_doc_raw in ("CEDULA", "CÉDULA") else "OTRO"
                elif not tipo_doc_raw:
                    tipo_doc_raw = "CC" if doc_raw else None

                correo_raw = (_limpiar_celda(fila.get(col_correo)).lower() if col_correo else "") or None
                telefono_raw = (_limpiar_celda(fila.get(col_tel)) if col_tel else "") or None
                whatsapp_raw = (_limpiar_celda(fila.get(col_ws)) if col_ws else "") or None
                direccion_raw = (_limpiar_celda(fila.get(col_dir)) if col_dir else "") or None
                barrio_raw = (_limpiar_celda(fila.get(col_barrio)) if col_barrio else "") or None

                # Estado
                estado_raw = _limpiar_celda(fila.get(col_estado)).lower() if col_estado else "activo"
                activo = estado_raw not in ("inactivo", "desactivado", "false", "0", "no")

                # Fecha de ingreso / registro
                fecha_ingreso_raw = _limpiar_celda(fila.get(col_fecha)) if col_fecha else ""
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

                id_raw = _limpiar_celda(fila.get(col_id)) if col_id else ""

                # REGLA TÉCNICA 1: Búsqueda segura EXCLUSIVAMENTE por documento. NUNCA por ID numérico.
                tutor_existente = None
                if doc_raw:
                    tutor_existente = db.session.execute(
                        select(Tutor).where(Tutor.numero_documento == doc_raw)
                    ).scalar_one_or_none()

                if tutor_existente:
                    tutor_existente.nombre_completo = nombre_completo
                    if tipo_doc_raw:
                        tutor_existente.tipo_documento = tipo_doc_raw
                    if telefono_raw and not tutor_existente.telefono:
                        tutor_existente.telefono = telefono_raw
                    if whatsapp_raw and not tutor_existente.whatsapp:
                        tutor_existente.whatsapp = whatsapp_raw
                    if correo_raw and not tutor_existente.email:
                        tutor_existente.email = correo_raw
                    if direccion_raw and not tutor_existente.direccion:
                        tutor_existente.direccion = direccion_raw
                    if barrio_raw and not tutor_existente.barrio:
                        tutor_existente.barrio = barrio_raw
                    if id_raw and not tutor_existente.id_externo:
                        tutor_existente.id_externo = id_raw
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
                        lote_importacion=lote_uuid,
                        id_externo=id_raw or None,
                    )
                    db.session.add(nuevo_tutor)
                    creados += 1

            # Registrar lote de importación para trazabilidad y reversión
            lote_registro = LoteImportacion(
                uuid=lote_uuid,
                tipo="tutores",
                nombre_archivo=getattr(archivo, "filename", "tutores.xlsx"),
                creados=creados,
                actualizados=actualizados,
                usuario_id=current_user.id,
            )
            db.session.add(lote_registro)

            # Transacción atómica
            db.session.commit()

            reporte = {
                "lote_uuid": lote_uuid,
                "creados": creados,
                "actualizados": actualizados,
                "errores": errores,
                "total_procesados": creados + actualizados,
            }
            flash(
                f"Importación completada. Creados: {creados}, Actualizados: {actualizados}, Con observaciones: {len(errores)}.",
                "success" if not errores else "warning",
            )
        except Exception as exc:
            db.session.rollback()
            current_app.logger.exception("Error general al importar lote de tutores")
            flash(f"Ocurrió un error y se canceló la importación (Rollback preventivo): {exc}", "danger")

    lotes_recientes = db.session.execute(
        select(LoteImportacion).where(LoteImportacion.tipo == "tutores").order_by(LoteImportacion.fecha.desc()).limit(5)
    ).scalars().all()

    return render_template(
        "tutores/importar.html",
        form=form,
        form_csrf=form_csrf,
        reporte=reporte,
        lotes_recientes=lotes_recientes,
    )


@bp.route("/revertir-lote/<uuid_lote>", methods=["POST"])
@login_required
@admin_required
def revertir_lote(uuid_lote):
    """Elimina de forma segura únicamente los tutores creados en el lote indicado."""
    form_csrf = SoloCsrfForm()
    if not form_csrf.validate_on_submit():
        flash("Error de validación de seguridad (CSRF).", "danger")
        return redirect(url_for("tutores.importar_excel"))

    lote = db.session.execute(
        select(LoteImportacion).where(LoteImportacion.uuid == uuid_lote, LoteImportacion.tipo == "tutores")
    ).scalar_one_or_none()

    if not lote:
        flash("El lote de importación no existe.", "danger")
        return redirect(url_for("tutores.importar_excel"))

    if lote.revertido:
        flash("Este lote ya fue revertido previamente.", "warning")
        return redirect(url_for("tutores.importar_excel"))

    tutores = db.session.execute(
        select(Tutor).where(Tutor.lote_importacion == uuid_lote)
    ).scalars().all()

    eliminados = 0
    no_eliminables = 0
    try:
        for t in tutores:
            if t.mascotas:
                no_eliminables += 1
                continue
            db.session.delete(t)
            eliminados += 1

        lote.revertido = True
        lote.fecha_reversion = obtener_hora_bogota()
        lote.usuario_reversion_id = current_user.id
        db.session.commit()

        msg = f"Reversión finalizada: Se eliminaron {eliminados} tutores creados en el lote."
        if no_eliminables > 0:
            msg += f" {no_eliminables} tutores se conservaron porque ya cuentan con mascotas registradas."
        flash(msg, "info")
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("Error al revertir lote %s de tutores", uuid_lote)
        flash(f"Error al revertir lote: {exc}", "danger")

    return redirect(url_for("tutores.importar_excel"))


