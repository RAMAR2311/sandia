"""Módulo de inventario: productos, variantes, lotes, kardex, alertas e importación Excel."""

import io
from datetime import timedelta
from decimal import Decimal, InvalidOperation

import pandas as pd
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import or_, select

from decorators import admin_required
from forms import (
    AjusteStockForm,
    ImportarExcelForm,
    LoteForm,
    ProductoForm,
    ProveedorForm,
    SoloCsrfForm,
    VarianteProductoForm,
)
from models import (
    CATEGORIAS_PRODUCTO,
    TIPOS_MOVIMIENTO,
    UNIDADES_MEDIDA,
    Lote,
    MovimientoStock,
    Producto,
    Proveedor,
    VarianteProducto,
    db,
)
from utils import (
    eliminar_imagen,
    guardar_imagen,
    hoy_bogota,
    normalizar_texto,
    obtener_hora_bogota,
)

bp = Blueprint("inventario", __name__, url_prefix="/inventario")

POR_PAGINA = 30
CARPETA_IMAGENES = "productos"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _opciones_proveedores():
    proveedores = db.session.execute(
        select(Proveedor).where(Proveedor.activo.is_(True)).order_by(Proveedor.nombre)
    ).scalars()
    return [(0, "Sin proveedor asignado")] + [(p.id, f"{p.nombre} ({p.nit or 'Sin NIT'})") for p in proveedores]


def _opciones_variantes(producto: Producto):
    return [(0, "Producto principal (Sin variante)")] + [
        (v.id, f"{v.nombre_variante} (SKU: {v.sku or 'N/A'})") for v in producto.variantes if v.activo
    ]


def _opciones_lotes(producto: Producto):
    return [(0, "Sin lote específico")] + [
        (l.id, f"Lote {l.numero_lote} (Vence: {l.fecha_vencimiento.strftime('%d/%m/%Y')} - Disp: {l.cantidad_disponible})")
        for l in producto.lotes
        if l.cantidad_disponible > 0
    ]


def _sku_en_uso(sku: str, excluir_producto_id: int | None = None, excluir_variante_id: int | None = None) -> bool:
    if not sku:
        return False
    sku_limpio = sku.strip().upper()
    c_prod = select(Producto.id).where(Producto.sku == sku_limpio)
    if excluir_producto_id is not None:
        c_prod = c_prod.where(Producto.id != excluir_producto_id)
    if db.session.execute(c_prod).first() is not None:
        return True

    c_var = select(VarianteProducto.id).where(VarianteProducto.sku == sku_limpio)
    if excluir_variante_id is not None:
        c_var = c_var.where(VarianteProducto.id != excluir_variante_id)
    return db.session.execute(c_var).first() is not None


def _codigo_barras_en_uso(codigo: str, excluir_producto_id: int | None = None, excluir_variante_id: int | None = None) -> bool:
    if not codigo:
        return False
    cod_limpio = codigo.strip()
    c_prod = select(Producto.id).where(Producto.codigo_barras == cod_limpio)
    if excluir_producto_id is not None:
        c_prod = c_prod.where(Producto.id != excluir_producto_id)
    if db.session.execute(c_prod).first() is not None:
        return True

    c_var = select(VarianteProducto.id).where(VarianteProducto.codigo_barras == cod_limpio)
    if excluir_variante_id is not None:
        c_var = c_var.where(VarianteProducto.id != excluir_variante_id)
    return db.session.execute(c_var).first() is not None


def _procesar_imagen(form_campo):
    archivo = form_campo.data
    if not archivo or not getattr(archivo, "filename", ""):
        return None
    try:
        return guardar_imagen(archivo, CARPETA_IMAGENES)
    except ValueError as exc:
        form_campo.errors.append(str(exc))
        return None


# ---------------------------------------------------------------------------
# Catálogo de Productos
# ---------------------------------------------------------------------------


@bp.route("/")
@login_required
def lista():
    texto = request.args.get("q", "").strip()
    categoria = request.args.get("categoria", "").strip()
    estado_stock = request.args.get("stock", "").strip()
    estado = request.args.get("estado", "activos")
    pagina = request.args.get("page", 1, type=int)

    consulta = select(Producto)
    normalizado = normalizar_texto(texto)
    if normalizado:
        consulta = consulta.where(
            or_(
                Producto.nombre_busqueda.ilike(f"%{normalizado}%"),
                Producto.sku.ilike(f"%{normalizado}%"),
                Producto.codigo_barras.ilike(f"%{normalizado}%"),
            )
        )
    if categoria in CATEGORIAS_PRODUCTO:
        consulta = consulta.where(Producto.categoria == categoria)
    if estado == "activos":
        consulta = consulta.where(Producto.activo.is_(True))
    elif estado == "inactivos":
        consulta = consulta.where(Producto.activo.is_(False))

    if estado_stock == "bajo":
        consulta = consulta.where(Producto.tipo != "servicio", Producto.cantidad_stock <= Producto.stock_minimo)
    elif estado_stock == "agotado":
        consulta = consulta.where(Producto.tipo != "servicio", Producto.cantidad_stock <= 0)

    consulta = consulta.order_by(Producto.nombre_busqueda)
    paginacion = db.paginate(consulta, page=pagina, per_page=POR_PAGINA, error_out=False)

    return render_template(
        "inventario/lista.html",
        pagina=paginacion,
        filtro_texto=texto,
        filtro_categoria=categoria,
        filtro_stock=estado_stock,
        filtro_estado=estado,
        CATEGORIAS_PRODUCTO=CATEGORIAS_PRODUCTO,
    )


@bp.route("/nuevo", methods=["GET", "POST"])
@login_required
@admin_required
def nuevo():
    form = ProductoForm()
    form.proveedor_id.choices = _opciones_proveedores()

    if form.validate_on_submit():
        if _sku_en_uso(form.sku.data):
            form.sku.errors.append("Ya existe un producto o variante con este SKU.")
        elif _codigo_barras_en_uso(form.codigo_barras.data):
            form.codigo_barras.errors.append("Ya existe un producto o variante con este código de barras.")
        else:
            nombre_imagen = _procesar_imagen(form.imagen)
            if not form.imagen.errors:
                prov_id = form.proveedor_id.data if form.proveedor_id.data != 0 else None
                producto = Producto(
                    sku=form.sku.data.strip().upper(),
                    codigo_barras=form.codigo_barras.data or None,
                    nombre=form.nombre.data,
                    descripcion=(form.descripcion.data or "").strip() or None,
                    categoria=form.categoria.data,
                    tipo=form.tipo.data,
                    unidad_medida=form.unidad_medida.data,
                    precio_costo=form.precio_costo.data or Decimal("0.00"),
                    precio_minimo=form.precio_minimo.data or Decimal("0.00"),
                    precio_sugerido=form.precio_sugerido.data or Decimal("0.00"),
                    cantidad_stock=Decimal("0.00"),
                    stock_minimo=form.stock_minimo.data or Decimal("0.00"),
                    proveedor_id=prov_id,
                    controla_lote=form.controla_lote.data,
                    requiere_receta=form.requiere_receta.data,
                    activo=form.activo.data,
                    imagen=nombre_imagen,
                    creado_por_id=current_user.id,
                )
                try:
                    db.session.add(producto)
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    eliminar_imagen(CARPETA_IMAGENES, nombre_imagen)
                    current_app.logger.exception("Error al crear producto")
                    flash("No se pudo registrar el producto.", "danger")
                else:
                    flash(f"Producto {producto.nombre} registrado.", "success")
                    return redirect(url_for("inventario.detalle", producto_id=producto.id))

    return render_template("inventario/form_producto.html", form=form, producto=None)


@bp.route("/<int:producto_id>")
@login_required
def detalle(producto_id):
    producto = db.session.get(Producto, producto_id)
    if producto is None:
        abort(404)

    form_variante = VarianteProductoForm()
    form_lote = LoteForm()
    form_lote.variante_id.choices = _opciones_variantes(producto)
    form_lote.proveedor_id.choices = _opciones_proveedores()

    form_ajuste = AjusteStockForm()
    form_ajuste.variante_id.choices = _opciones_variantes(producto)
    form_ajuste.lote_id.choices = _opciones_lotes(producto)

    return render_template(
        "inventario/detalle.html",
        producto=producto,
        form_variante=form_variante,
        form_lote=form_lote,
        form_ajuste=form_ajuste,
        form_csrf=SoloCsrfForm(),
        UNIDADES_MEDIDA=UNIDADES_MEDIDA,
    )


@bp.route("/<int:producto_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def editar(producto_id):
    producto = db.session.get(Producto, producto_id)
    if producto is None:
        abort(404)

    form = ProductoForm(obj=producto)
    form.proveedor_id.choices = _opciones_proveedores()

    if request.method == "GET":
        form.proveedor_id.data = producto.proveedor_id or 0

    if form.validate_on_submit():
        if _sku_en_uso(form.sku.data, excluir_producto_id=producto.id):
            form.sku.errors.append("Ya existe otro producto o variante con este SKU.")
        elif _codigo_barras_en_uso(form.codigo_barras.data, excluir_producto_id=producto.id):
            form.codigo_barras.errors.append("Ya existe otro producto o variante con este código de barras.")
        else:
            nombre_imagen = _procesar_imagen(form.imagen)
            if not form.imagen.errors:
                imagen_anterior = producto.imagen
                producto.sku = form.sku.data.strip().upper()
                producto.codigo_barras = form.codigo_barras.data or None
                producto.nombre = form.nombre.data
                producto.descripcion = (form.descripcion.data or "").strip() or None
                producto.categoria = form.categoria.data
                producto.tipo = form.tipo.data
                producto.unidad_medida = form.unidad_medida.data
                producto.precio_costo = form.precio_costo.data or Decimal("0.00")
                producto.precio_minimo = form.precio_minimo.data or Decimal("0.00")
                producto.precio_sugerido = form.precio_sugerido.data or Decimal("0.00")
                producto.stock_minimo = form.stock_minimo.data or Decimal("0.00")
                producto.proveedor_id = form.proveedor_id.data if form.proveedor_id.data != 0 else None
                producto.controla_lote = form.controla_lote.data
                producto.requiere_receta = form.requiere_receta.data
                producto.activo = form.activo.data
                if nombre_imagen:
                    producto.imagen = nombre_imagen

                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    eliminar_imagen(CARPETA_IMAGENES, nombre_imagen)
                    current_app.logger.exception("Error al editar producto %s", producto_id)
                    flash("No se pudieron guardar los cambios.", "danger")
                else:
                    if nombre_imagen and imagen_anterior:
                        eliminar_imagen(CARPETA_IMAGENES, imagen_anterior)
                    flash("Cambios guardados.", "success")
                    return redirect(url_for("inventario.detalle", producto_id=producto.id))

    return render_template("inventario/form_producto.html", form=form, producto=producto)


@bp.route("/<int:producto_id>/estado", methods=["POST"])
@login_required
@admin_required
def cambiar_estado(producto_id):
    producto = db.session.get(Producto, producto_id)
    if producto is None:
        abort(404)

    form = SoloCsrfForm()
    if not form.validate_on_submit():
        abort(400)

    try:
        producto.activo = not producto.activo
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error al cambiar estado del producto %s", producto_id)
        flash("No se pudo cambiar el estado.", "danger")
    else:
        accion = "activado" if producto.activo else "desactivado"
        flash(f"Producto {accion}.", "success")

    return redirect(url_for("inventario.detalle", producto_id=producto.id))


# ---------------------------------------------------------------------------
# Variantes
# ---------------------------------------------------------------------------


@bp.route("/<int:producto_id>/variantes/nueva", methods=["POST"])
@login_required
@admin_required
def variante_nueva(producto_id):
    producto = db.session.get(Producto, producto_id)
    if producto is None:
        abort(404)

    form = VarianteProductoForm()
    if form.validate_on_submit():
        if _sku_en_uso(form.sku.data):
            flash("Ese SKU ya está en uso por otro producto o variante.", "danger")
        elif _codigo_barras_en_uso(form.codigo_barras.data):
            flash("Ese código de barras ya está en uso.", "danger")
        else:
            variante = VarianteProducto(
                producto_id=producto.id,
                nombre_variante=form.nombre_variante.data.strip(),
                sku=form.sku.data or None,
                codigo_barras=form.codigo_barras.data or None,
                precio_costo=form.precio_costo.data or Decimal("0.00"),
                precio_minimo=form.precio_minimo.data or Decimal("0.00"),
                precio_sugerido=form.precio_sugerido.data or Decimal("0.00"),
                stock_minimo=form.stock_minimo.data or Decimal("0.00"),
                cantidad_stock=Decimal("0.00"),
                activo=form.activo.data,
            )
            try:
                db.session.add(variante)
                db.session.commit()
            except Exception:
                db.session.rollback()
                current_app.logger.exception("Error al crear variante para el producto %s", producto_id)
                flash("No se pudo registrar la variante.", "danger")
            else:
                flash(f"Variante {variante.nombre_variante} agregada.", "success")
            return redirect(url_for("inventario.detalle", producto_id=producto.id))

    for errores in form.errors.values():
        for err in errores:
            flash(err, "danger")
    return redirect(url_for("inventario.detalle", producto_id=producto.id))


# ---------------------------------------------------------------------------
# Lotes
# ---------------------------------------------------------------------------


@bp.route("/<int:producto_id>/lotes/nuevo", methods=["POST"])
@login_required
@admin_required
def lote_nuevo(producto_id):
    producto = db.session.get(Producto, producto_id)
    if producto is None:
        abort(404)

    form = LoteForm()
    form.variante_id.choices = _opciones_variantes(producto)
    form.proveedor_id.choices = _opciones_proveedores()

    if form.validate_on_submit():
        var_id = form.variante_id.data if form.variante_id.data != 0 else None
        prov_id = form.proveedor_id.data if form.proveedor_id.data != 0 else None
        cant = Decimal(str(form.cantidad.data))

        # Concurrencia segura: with_for_update() en producto/variante
        if var_id:
            item_afectado = db.session.execute(
                select(VarianteProducto).where(VarianteProducto.id == var_id).with_for_update()
            ).scalar_one()
        else:
            item_afectado = db.session.execute(
                select(Producto).where(Producto.id == producto.id).with_for_update()
            ).scalar_one()

        stock_ant = item_afectado.cantidad_stock
        stock_nuevo = stock_ant + cant

        lote = Lote(
            producto_id=producto.id,
            variante_id=var_id,
            numero_lote=form.numero_lote.data.strip(),
            fecha_vencimiento=form.fecha_vencimiento.data,
            cantidad_inicial=cant,
            cantidad_disponible=cant,
            proveedor_id=prov_id,
            creado_por_id=current_user.id,
        )
        item_afectado.cantidad_stock = stock_nuevo

        movimiento = MovimientoStock(
            producto_id=producto.id,
            variante_id=var_id,
            lote=lote,
            usuario_id=current_user.id,
            tipo_movimiento="entrada",
            cantidad=cant,
            stock_anterior=stock_ant,
            stock_nuevo=stock_nuevo,
            motivo=f"Ingreso de Lote {lote.numero_lote}",
        )

        try:
            db.session.add(lote)
            db.session.add(movimiento)
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al registrar lote para el producto %s", producto_id)
            flash("No se pudo registrar el lote.", "danger")
        else:
            flash(f"Lote {lote.numero_lote} registrado correctamente (+{cant}).", "success")
        return redirect(url_for("inventario.detalle", producto_id=producto.id))

    for errores in form.errors.values():
        for err in errores:
            flash(err, "danger")
    return redirect(url_for("inventario.detalle", producto_id=producto.id))


# ---------------------------------------------------------------------------
# Ajustes de Stock / Kardex
# ---------------------------------------------------------------------------


@bp.route("/<int:producto_id>/ajuste", methods=["POST"])
@login_required
@admin_required
def registrar_ajuste(producto_id):
    producto = db.session.get(Producto, producto_id)
    if producto is None:
        abort(404)

    form = AjusteStockForm()
    form.variante_id.choices = _opciones_variantes(producto)
    form.lote_id.choices = _opciones_lotes(producto)

    if form.validate_on_submit():
        var_id = form.variante_id.data if form.variante_id.data != 0 else None
        lote_id = form.lote_id.data if form.lote_id.data != 0 else None
        tipo_mov = form.tipo_movimiento.data
        cant = Decimal(str(form.cantidad.data))

        # Bloqueo optimista con lock para concurrencia atómica
        if var_id:
            item = db.session.execute(
                select(VarianteProducto).where(VarianteProducto.id == var_id).with_for_update()
            ).scalar_one()
        else:
            item = db.session.execute(
                select(Producto).where(Producto.id == producto.id).with_for_update()
            ).scalar_one()

        lote = None
        if lote_id:
            lote = db.session.execute(
                select(Lote).where(Lote.id == lote_id).with_for_update()
            ).scalar_one()

        stock_ant = item.cantidad_stock
        if tipo_mov in ("entrada", "ajuste_positivo"):
            delta = cant
        else:
            delta = -cant

        stock_nuevo = stock_ant + delta
        if stock_nuevo < 0:
            flash("El ajuste no puede dejar el stock total en negativo.", "danger")
            return redirect(url_for("inventario.detalle", producto_id=producto.id))

        if lote is not None:
            lote_nuevo = lote.cantidad_disponible + delta
            if lote_nuevo < 0:
                flash("El ajuste no puede dejar la cantidad del lote en negativo.", "danger")
                return redirect(url_for("inventario.detalle", producto_id=producto.id))
            lote.cantidad_disponible = lote_nuevo

        item.cantidad_stock = stock_nuevo

        movimiento = MovimientoStock(
            producto_id=producto.id,
            variante_id=var_id,
            lote_id=lote_id,
            usuario_id=current_user.id,
            tipo_movimiento=tipo_mov,
            cantidad=cant,
            stock_anterior=stock_ant,
            stock_nuevo=stock_nuevo,
            motivo=form.motivo.data,
        )

        try:
            db.session.add(movimiento)
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al ajustar stock del producto %s", producto_id)
            flash("No se pudo guardar el ajuste de stock.", "danger")
        else:
            flash("Ajuste de stock registrado.", "success")

        return redirect(url_for("inventario.detalle", producto_id=producto.id))

    for errores in form.errors.values():
        for err in errores:
            flash(err, "danger")
    return redirect(url_for("inventario.detalle", producto_id=producto.id))


# ---------------------------------------------------------------------------
# Tablero de Alertas (Stock Bajo & Vencimientos)
# ---------------------------------------------------------------------------


@bp.route("/alertas")
@login_required
def alertas():
    hoy = hoy_bogota()
    dias_30 = hoy + timedelta(days=30)
    dias_60 = hoy + timedelta(days=60)
    dias_90 = hoy + timedelta(days=90)

    # 1. Productos con stock bajo
    productos_bajo = (
        db.session.execute(
            select(Producto)
            .where(Producto.activo.is_(True), Producto.tipo != "servicio", Producto.cantidad_stock <= Producto.stock_minimo)
            .order_by(Producto.cantidad_stock)
        )
        .scalars()
        .all()
    )

    # 2. Lotes vencidos o por vencer
    lotes_vencidos = (
        db.session.execute(
            select(Lote)
            .where(Lote.cantidad_disponible > 0, Lote.fecha_vencimiento < hoy)
            .order_by(Lote.fecha_vencimiento)
        )
        .scalars()
        .all()
    )

    lotes_30 = (
        db.session.execute(
            select(Lote)
            .where(Lote.cantidad_disponible > 0, Lote.fecha_vencimiento >= hoy, Lote.fecha_vencimiento <= dias_30)
            .order_by(Lote.fecha_vencimiento)
        )
        .scalars()
        .all()
    )

    lotes_60 = (
        db.session.execute(
            select(Lote)
            .where(Lote.cantidad_disponible > 0, Lote.fecha_vencimiento > dias_30, Lote.fecha_vencimiento <= dias_60)
            .order_by(Lote.fecha_vencimiento)
        )
        .scalars()
        .all()
    )

    lotes_90 = (
        db.session.execute(
            select(Lote)
            .where(Lote.cantidad_disponible > 0, Lote.fecha_vencimiento > dias_60, Lote.fecha_vencimiento <= dias_90)
            .order_by(Lote.fecha_vencimiento)
        )
        .scalars()
        .all()
    )

    return render_template(
        "inventario/alertas.html",
        productos_bajo=productos_bajo,
        lotes_vencidos=lotes_vencidos,
        lotes_30=lotes_30,
        lotes_60=lotes_60,
        lotes_90=lotes_90,
    )


# ---------------------------------------------------------------------------
# Importación desde Excel
# ---------------------------------------------------------------------------


@bp.route("/importar", methods=["GET", "POST"])
@login_required
@admin_required
def importar_excel():
    form = ImportarExcelForm()
    reporte = None

    if form.validate_on_submit():
        archivo = form.archivo.data
        if not archivo.filename.lower().endswith(".xlsx"):
            flash("El archivo debe tener extensión .xlsx", "danger")
            return render_template("inventario/importar.html", form=form, reporte=None)

        try:
            df = pd.read_excel(archivo.stream, engine="openpyxl")
        except Exception as exc:
            current_app.logger.exception("Error al leer Excel de inventario")
            flash(f"No se pudo leer el archivo Excel: {exc}", "danger")
            return render_template("inventario/importar.html", form=form, reporte=None)

        columnas_requeridas = ["SKU", "Nombre"]
        for col in columnas_requeridas:
            if col not in df.columns:
                flash(f"Falta la columna obligatoria '{col}' en el archivo Excel.", "danger")
                return render_template("inventario/importar.html", form=form, reporte=None)

        creados = 0
        actualizados = 0
        errores = []

        for indice, fila in df.iterrows():
            num_fila = indice + 2  # Encabezado en fila 1
            sku_raw = str(fila.get("SKU", "")).strip().upper()
            nombre_raw = str(fila.get("Nombre", "")).strip()

            if not sku_raw or sku_raw == "NAN":
                errores.append(f"Fila {num_fila}: SKU vacío.")
                continue
            if not nombre_raw or nombre_raw == "NAN":
                errores.append(f"Fila {num_fila}: Nombre vacío.")
                continue

            categoria_raw = str(fila.get("Categoria", "otro")).strip().lower()
            if categoria_raw not in CATEGORIAS_PRODUCTO:
                categoria_raw = "otro"

            unidad_raw = str(fila.get("UnidadMedida", "unidad")).strip().lower()
            if unidad_raw not in UNIDADES_MEDIDA:
                unidad_raw = "unidad"

            def _dec(val, def_val="0.00"):
                try:
                    if pd.isna(val):
                        return Decimal(def_val)
                    return Decimal(str(val)).quantize(Decimal("0.01"))
                except (InvalidOperation, ValueError):
                    return Decimal(def_val)

            p_costo = _dec(fila.get("PrecioCosto"))
            p_minimo = _dec(fila.get("PrecioMinimo"))
            p_sugerido = _dec(fila.get("PrecioSugerido"))
            stock_ini = _dec(fila.get("StockInicial"))
            stock_min = _dec(fila.get("StockMinimo"))
            ctrl_lote = str(fila.get("ControlaLote", "")).strip().lower() in ("1", "true", "si", "sí")

            try:
                existente = db.session.execute(select(Producto).filter_by(sku=sku_raw)).scalar_one_or_none()
                if existente is not None:
                    existente.nombre = nombre_raw
                    existente.categoria = categoria_raw
                    existente.unidad_medida = unidad_raw
                    existente.precio_costo = p_costo
                    existente.precio_minimo = p_minimo
                    existente.precio_sugerido = p_sugerido
                    existente.stock_minimo = stock_min
                    existente.controla_lote = ctrl_lote
                    actualizados += 1
                else:
                    nuevo_prod = Producto(
                        sku=sku_raw,
                        nombre=nombre_raw,
                        categoria=categoria_raw,
                        unidad_medida=unidad_raw,
                        precio_costo=p_costo,
                        precio_minimo=p_minimo,
                        precio_sugerido=p_sugerido,
                        cantidad_stock=stock_ini,
                        stock_minimo=stock_min,
                        controla_lote=ctrl_lote,
                        creado_por_id=current_user.id,
                    )
                    db.session.add(nuevo_prod)
                    db.session.flush()

                    if stock_ini > 0:
                        mov = MovimientoStock(
                            producto_id=nuevo_prod.id,
                            usuario_id=current_user.id,
                            tipo_movimiento="inicial",
                            cantidad=stock_ini,
                            stock_anterior=Decimal("0.00"),
                            stock_nuevo=stock_ini,
                            motivo="Carga inicial desde Excel",
                        )
                        db.session.add(mov)
                    creados += 1
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                current_app.logger.exception("Error en fila %s de Excel", num_fila)
                errores.append(f"Fila {num_fila} ({sku_raw}): {exc}")

        reporte = {
            "creados": creados,
            "actualizados": actualizados,
            "errores": errores,
            "total_procesados": creados + actualizados,
        }
        flash(f"Importación finalizada. Creados: {creados}, Actualizados: {actualizados}, Errores: {len(errores)}.", "info")

    return render_template("inventario/importar.html", form=form, reporte=reporte)


@bp.route("/plantilla-excel")
@login_required
@admin_required
def plantilla_excel():
    datos = [
        {
            "SKU": "MED-001",
            "Nombre": "Amoxicilina 250mg x 10 tab",
            "Categoria": "medicamento",
            "UnidadMedida": "caja",
            "PrecioCosto": 12000,
            "PrecioMinimo": 18000,
            "PrecioSugerido": 25000,
            "StockInicial": 20,
            "StockMinimo": 5,
            "ControlaLote": "si",
        },
        {
            "SKU": "ALI-002",
            "Nombre": "Alimento Perro Adulto 10kg",
            "Categoria": "alimento",
            "UnidadMedida": "bulto",
            "PrecioCosto": 85000,
            "PrecioMinimo": 110000,
            "PrecioSugerido": 135000,
            "StockInicial": 10,
            "StockMinimo": 3,
            "ControlaLote": "no",
        },
    ]

    df = pd.DataFrame(datos)
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Inventario")
    out.seek(0)

    return send_file(
        out,
        as_attachment=True,
        download_name="plantilla_inventario_vetcare.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


# ---------------------------------------------------------------------------
# Proveedores
# ---------------------------------------------------------------------------


@bp.route("/proveedores")
@login_required
@admin_required
def proveedores_lista():
    texto = request.args.get("q", "").strip()
    consulta = select(Proveedor)
    norm = normalizar_texto(texto)
    if norm:
        consulta = consulta.where(
            or_(
                Proveedor.nombre_busqueda.ilike(f"%{norm}%"),
                Proveedor.nit.ilike(f"%{norm}%"),
                Proveedor.telefono.ilike(f"%{norm}%"),
            )
        )
    consulta = consulta.order_by(Proveedor.nombre_busqueda)
    lista = db.session.execute(consulta).scalars().all()
    return render_template("inventario/proveedores.html", proveedores=lista, filtro_texto=texto)


@bp.route("/proveedores/nuevo", methods=["GET", "POST"])
@login_required
@admin_required
def proveedor_nuevo():
    form = ProveedorForm()
    if form.validate_on_submit():
        prov = Proveedor(
            nit=form.nit.data,
            nombre=form.nombre.data,
            contacto=form.contacto.data,
            telefono=form.telefono.data,
            email=form.email.data,
            direccion=form.direccion.data,
            ciudad=form.ciudad.data,
            notas=form.notas.data,
            activo=form.activo.data,
        )
        try:
            db.session.add(prov)
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al crear proveedor")
            flash("No se pudo registrar el proveedor.", "danger")
        else:
            flash(f"Proveedor {prov.nombre} registrado.", "success")
            return redirect(url_for("inventario.proveedores_lista"))
    return render_template("inventario/form_proveedor.html", form=form, proveedor=None)


@bp.route("/proveedores/<int:proveedor_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def proveedor_editar(proveedor_id):
    prov = db.session.get(Proveedor, proveedor_id)
    if prov is None:
        abort(404)
    form = ProveedorForm(obj=prov)
    if form.validate_on_submit():
        prov.nit = form.nit.data
        prov.nombre = form.nombre.data
        prov.contacto = form.contacto.data
        prov.telefono = form.telefono.data
        prov.email = form.email.data
        prov.direccion = form.direccion.data
        prov.ciudad = form.ciudad.data
        prov.notas = form.notas.data
        prov.activo = form.activo.data
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al editar proveedor %s", proveedor_id)
            flash("No se pudieron guardar los cambios.", "danger")
        else:
            flash("Cambios guardados.", "success")
            return redirect(url_for("inventario.proveedores_lista"))
    return render_template("inventario/form_proveedor.html", form=form, proveedor=prov)
