"""Módulo de Punto de Venta (POS) y Gestión de Caja.

Controla la apertura y cierre de turnos de caja con arqueo de dinero,
la venta rápida de productos y servicios con selección de cliente y mascota,
el descuento automático de stock mediante FEFO y la emisión y anulación de facturas.
"""

from decimal import Decimal, InvalidOperation
from typing import Optional

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from decorators import admin_required, caja_required
from flask_login import current_user, login_required
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from forms import AnularVentaForm, AperturaCajaForm, AprobarPrecioForm, CierreCajaForm, RechazarPrecioForm, SoloCsrfForm
from models import (
    ESTADOS_VENTA,
    METODOS_PAGO,
    AprobacionPrecio,
    ConfiguracionSistema,
    DetalleVenta,
    Lote,
    Mascota,
    MovimientoStock,
    PagoVenta,
    Producto,
    TurnoCaja,
    Tutor,
    Usuario,
    VarianteProducto,
    Venta,
    CitaSpa,
    db,
)
from utils import hoy_bogota, obtener_hora_bogota

bp = Blueprint("pos", __name__, url_prefix="/pos")


def obtener_turno_activo(usuario_id: int) -> Optional[TurnoCaja]:
    """Devuelve el turno de caja abierto para el usuario o None si no hay ninguno."""
    return db.session.execute(
        select(TurnoCaja)
        .filter_by(usuario_id=usuario_id, estado="abierta")
        .order_by(TurnoCaja.id.desc())
    ).scalar_one_or_none()


def generar_numero_factura() -> str:
    """Genera un número de factura correlativo único: VET-YYYYMMDD-0001."""
    hoy_str = hoy_bogota().strftime("%Y%m%d")
    prefijo = f"VET-{hoy_str}-"
    
    ultimo_numero = db.session.execute(
        select(func.max(Venta.numero_factura))
        .filter(Venta.numero_factura.like(f"{prefijo}%"))
    ).scalar()

    if ultimo_numero:
        try:
            secuencia = int(ultimo_numero.split("-")[-1]) + 1
        except ValueError:
            secuencia = 1
    else:
        secuencia = 1

    return f"{prefijo}{secuencia:04d}"


def _buscar_aprobacion_activa(usuario_id: int, producto_id: int, variante_id, precio_unitario: Decimal):
    """Aprobación ya autorizada y sin usar para exactamente este precio (regla 8.1)."""
    return db.session.execute(
        select(AprobacionPrecio)
        .where(
            AprobacionPrecio.solicitante_id == usuario_id,
            AprobacionPrecio.producto_id == producto_id,
            AprobacionPrecio.variante_id == variante_id,
            AprobacionPrecio.estado == "aprobado",
            AprobacionPrecio.venta_id.is_(None),
            AprobacionPrecio.precio_aprobado == precio_unitario,
        )
        .order_by(AprobacionPrecio.id.desc())
    ).scalars().first()


def _resolver_solicitud_precio(usuario, producto, variante, descripcion, precio_minimo, precio_solicitado):
    """Reutiliza una solicitud pendiente/rechazada al mismo precio, o crea una nueva pendiente.

    Se ejecuta después de descartar (rollback) los cambios de la venta en curso,
    así que hace su propio commit aislado: la solicitud debe quedar visible para
    el admin aunque la venta que la originó no se haya completado.
    """
    variante_id = variante.id if variante else None
    existente = db.session.execute(
        select(AprobacionPrecio)
        .where(
            AprobacionPrecio.solicitante_id == usuario.id,
            AprobacionPrecio.producto_id == producto.id,
            AprobacionPrecio.variante_id == variante_id,
            AprobacionPrecio.precio_solicitado == precio_solicitado,
            AprobacionPrecio.estado.in_(("pendiente", "rechazado")),
        )
        .order_by(AprobacionPrecio.id.desc())
    ).scalars().first()
    if existente is not None:
        return existente

    solicitud = AprobacionPrecio(
        solicitante_id=usuario.id,
        producto_id=producto.id,
        variante_id=variante_id,
        descripcion=descripcion,
        precio_original=precio_minimo,
        precio_solicitado=precio_solicitado,
        estado="pendiente",
    )
    db.session.add(solicitud)
    db.session.commit()
    return solicitud


# ---------------------------------------------------------------------------
# Gestión de Caja
# ---------------------------------------------------------------------------


@bp.route("/caja", methods=["GET"])
@login_required
@caja_required
def caja_estado():
    turno_activo = obtener_turno_activo(current_user.id)
    form_apertura = AperturaCajaForm()
    form_cierre = CierreCajaForm()
    form_csrf = SoloCsrfForm()

    resumen_caja = {
        "efectivo": Decimal("0.00"),
        "nequi": Decimal("0.00"),
        "daviplata": Decimal("0.00"),
        "tarjeta_debito": Decimal("0.00"),
        "tarjeta_credito": Decimal("0.00"),
        "transferencia": Decimal("0.00"),
        "total_ventas": Decimal("0.00"),
        "ventas_count": 0,
    }

    if turno_activo:
        ventas_turno = db.session.execute(
            select(Venta)
            .filter_by(turno_caja_id=turno_activo.id, estado="completada")
            .options(selectinload(Venta.pagos))
        ).scalars().all()

        resumen_caja["ventas_count"] = len(ventas_turno)
        for v in ventas_turno:
            resumen_caja["total_ventas"] += v.total
            for pago in v.pagos:
                metodo = pago.metodo_pago
                if metodo in resumen_caja:
                    resumen_caja[metodo] += pago.monto

        # Cierre sugerido: Efectivo base + ventas en efectivo
        form_cierre.monto_efectivo.data = turno_activo.monto_apertura + resumen_caja["efectivo"]
        form_cierre.monto_nequi.data = resumen_caja["nequi"]
        form_cierre.monto_daviplata.data = resumen_caja["daviplata"]
        form_cierre.monto_tarjetas.data = resumen_caja["tarjeta_debito"] + resumen_caja["tarjeta_credito"]
        form_cierre.monto_transferencia.data = resumen_caja["transferencia"]

    # Historial de turnos recientes
    turnos_recientes = db.session.execute(
        select(TurnoCaja)
        .options(selectinload(TurnoCaja.usuario))
        .order_by(TurnoCaja.id.desc())
        .limit(20)
    ).scalars().all()

    return render_template(
        "pos/caja_estado.html",
        turno_activo=turno_activo,
        form_apertura=form_apertura,
        form_cierre=form_cierre,
        form_csrf=form_csrf,
        resumen=resumen_caja,
        turnos_recientes=turnos_recientes,
    )


@bp.route("/caja/abrir", methods=["POST"])
@login_required
@caja_required
def abrir_caja():
    turno_activo = obtener_turno_activo(current_user.id)
    if turno_activo:
        flash("Ya tienes una caja abierta. No puedes abrir otra simultáneamente.", "warning")
        return redirect(url_for("pos.terminal"))

    datos_post = request.form.copy()
    if "monto_apertura" in datos_post:
        raw = datos_post["monto_apertura"].strip()
        limpio = raw.replace(".", "").replace(" ", "").replace(",", ".")
        datos_post["monto_apertura"] = limpio

    form = AperturaCajaForm(formdata=datos_post)
    if form.validate():
        try:
            nuevo_turno = TurnoCaja(
                usuario_id=current_user.id,
                monto_apertura=form.monto_apertura.data,
                estado="abierta",
                fecha_apertura=obtener_hora_bogota(),
                notas_apertura=form.notas.data,
            )
            db.session.add(nuevo_turno)
            db.session.commit()
            flash("Turno de caja abierto correctamente. ¡Buenas ventas!", "success")
            return redirect(url_for("pos.terminal"))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al abrir turno de caja")
            flash("Ocurrió un error al abrir la caja. Inténtalo de nuevo.", "danger")

    for err in form.monto_apertura.errors:
        flash(err, "danger")
    return redirect(url_for("pos.caja_estado"))


@bp.route("/caja/cerrar", methods=["POST"])
@login_required
@caja_required
def cerrar_caja():
    turno_activo = obtener_turno_activo(current_user.id)
    if not turno_activo:
        flash("No tienes un turno de caja abierto para cerrar.", "warning")
        return redirect(url_for("pos.caja_estado"))

    datos_post = request.form.copy()
    for campo in ["monto_efectivo", "monto_nequi", "monto_daviplata", "monto_tarjetas", "monto_transferencia"]:
        if campo in datos_post:
            raw = datos_post[campo].strip()
            limpio = raw.replace(".", "").replace(" ", "").replace(",", ".")
            datos_post[campo] = limpio

    form = CierreCajaForm(formdata=datos_post)
    if form.validate():
        try:
            # Calcular ventas en efectivo
            ventas_efectivo = db.session.execute(
                select(func.coalesce(func.sum(PagoVenta.monto), Decimal("0.00")))
                .join(Venta)
                .filter(
                    Venta.turno_caja_id == turno_activo.id,
                    Venta.estado == "completada",
                    PagoVenta.metodo_pago == "efectivo",
                )
            ).scalar() or Decimal("0.00")

            monto_esperado = turno_activo.monto_apertura + ventas_efectivo
            monto_real = form.monto_efectivo.data or Decimal("0.00")
            diferencia = monto_real - monto_esperado

            turno_activo.monto_cierre_esperado = monto_esperado
            turno_activo.monto_cierre_real = monto_real
            turno_activo.diferencia = diferencia
            turno_activo.estado = "cerrada"
            turno_activo.fecha_cierre = obtener_hora_bogota()
            turno_activo.notas_cierre = form.notas.data

            db.session.commit()

            if diferencia == Decimal("0.00"):
                msg = f"Caja cerrada correctamente. Cuadre perfecto (${monto_real:,.2f})."
                cat = "success"
            elif diferencia > 0:
                msg = f"Caja cerrada. Sobrante detectado de +${diferencia:,.2f}."
                cat = "info"
            else:
                msg = f"Caja cerrada. Faltante detectado de -${abs(diferencia):,.2f}."
                cat = "warning"

            flash(msg, cat)
            return redirect(url_for("pos.caja_estado"))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al cerrar turno de caja")
            flash("Error al procesar el cierre de caja.", "danger")

    flash("Datos de cierre inválidos.", "danger")
    return redirect(url_for("pos.caja_estado"))


# ---------------------------------------------------------------------------
# Terminal POS y Cobro
# ---------------------------------------------------------------------------


@bp.route("/terminal", methods=["GET"])
@login_required
@caja_required
def terminal():
    turno_activo = obtener_turno_activo(current_user.id)
    if not turno_activo:
        flash("Debes abrir la caja antes de ingresar a la terminal de ventas.", "warning")
        return redirect(url_for("pos.caja_estado"))

    cita_spa_id = request.args.get("cita_spa_id", type=int)
    datos_precarga = None

    if cita_spa_id:
        cita = db.session.get(CitaSpa, cita_spa_id)
        if cita and not cita.venta_id:
            tutor_data = None
            if cita.tutor:
                mascotas_tutor = [
                    {"id": m.id, "nombre": m.nombre, "especie": m.especie, "emoji": m.especie_emoji}
                    for m in cita.tutor.mascotas if m.activo and not m.fallecido
                ]
                tutor_data = {
                    "id": cita.tutor.id,
                    "nombre": cita.tutor.nombre_completo,
                    "documento": cita.tutor.documento_texto or "Sin documento",
                    "telefono": cita.tutor.telefono or cita.tutor.whatsapp or "",
                    "mascotas": mascotas_tutor,
                }

            item_servicio = None
            if cita.servicio_spa:
                item_servicio = {
                    "producto_id": f"spa_{cita.servicio_spa.id}",
                    "servicio_spa_id": cita.servicio_spa.id,
                    "sku": f"SPA-{cita.servicio_spa.id:02d}",
                    "nombre": cita.servicio_spa.nombre,
                    "tipo": "servicio",
                    "categoria": "spa",
                    "precio_unitario": float(cita.servicio_spa.precio_sugerido),
                    "cantidad": 1,
                    "descuento": 0,
                }

            datos_precarga = {
                "cita_spa_id": cita.id,
                "tutor": tutor_data,
                "mascota_id": cita.mascota_id,
                "mascota_nombre": cita.mascota.nombre if cita.mascota else "",
                "item": item_servicio,
            }

    return render_template("pos/terminal.html", turno=turno_activo, datos_precarga=datos_precarga)


@bp.route("/venta/procesar", methods=["POST"])
@login_required
@caja_required
def procesar_venta():
    turno_activo = obtener_turno_activo(current_user.id)
    if not turno_activo:
        return jsonify(error="Debes tener un turno de caja abierto para registrar ventas."), 400

    datos = request.get_json() or {}
    tutor_id = datos.get("tutor_id")
    mascota_id = datos.get("mascota_id")
    descuento_monto_solicitado = Decimal(str(datos.get("descuento_monto", "0.00") or "0.00"))
    items = datos.get("items", [])
    pagos_req = datos.get("pagos", [])

    if not items:
        return jsonify(error="El carrito de compras está vacío."), 400

    if not pagos_req:
        return jsonify(error="Debes agregar al menos un medio de pago."), 400

    descuenta_stock = ConfiguracionSistema.obtener("descontar_stock_ventas", True)

    try:
        subtotal_venta = Decimal("0.00")
        detalles_a_crear = []
        movimientos_kardex_a_crear = []
        aprobaciones_a_consumir = []

        # 1. Procesar cada ítem del carrito
        for item in items:
            producto_id = item.get("producto_id")
            variante_id = item.get("variante_id")
            cantidad_req = Decimal(str(item.get("cantidad", "1")))
            precio_unitario = Decimal(str(item.get("precio_unitario", "0.00")))
            descuento_item = Decimal(str(item.get("descuento", "0.00")))
            descripcion_override = item.get("descripcion") or item.get("nombre")
            tipo_item = item.get("tipo", "producto")

            if cantidad_req <= Decimal("0.00"):
                return jsonify(error=f"La cantidad para '{descripcion_override}' debe ser mayor a 0."), 400

            if tipo_item == "servicio" or not producto_id:
                # Servicio genérico, spa o consulta clínica
                fk_prod_id = None
                try:
                    if producto_id and str(producto_id).isdigit():
                        p_check = db.session.get(Producto, int(producto_id))
                        if p_check:
                            fk_prod_id = p_check.id
                except Exception:
                    fk_prod_id = None

                linea_subtotal = (cantidad_req * precio_unitario) - descuento_item
                subtotal_venta += linea_subtotal
                detalles_a_crear.append({
                    "producto_id": fk_prod_id,
                    "variante_id": None,
                    "lote_id": None,
                    "descripcion": descripcion_override or "Servicio",
                    "tipo_item": "servicio",
                    "cantidad": cantidad_req,
                    "precio_unitario": precio_unitario,
                    "subtotal": cantidad_req * precio_unitario,
                    "descuento": descuento_item,
                    "total_linea": linea_subtotal,
                })
                continue

            # Es producto físico
            producto = db.session.get(Producto, producto_id)
            if not producto or not producto.activo:
                return jsonify(error=f"El producto ID {producto_id} no existe o no está activo."), 400

            variante = db.session.get(VarianteProducto, variante_id) if variante_id else None
            descripcion = f"{producto.nombre} ({variante.nombre_variante})" if variante else producto.nombre

            # Regla de negocio: un cajero no puede vender bajo el precio mínimo
            # sin aprobación del admin. El admin no tiene esta restricción.
            precio_minimo_aplicable = variante.precio_minimo if variante else producto.precio_minimo
            if not current_user.es_admin and precio_unitario < precio_minimo_aplicable:
                aprobacion_activa = _buscar_aprobacion_activa(
                    current_user.id, producto.id, variante.id if variante else None, precio_unitario
                )
                if aprobacion_activa is None:
                    db.session.rollback()
                    solicitud = _resolver_solicitud_precio(
                        current_user, producto, variante, descripcion, precio_minimo_aplicable, precio_unitario
                    )
                    return jsonify(
                        ok=False,
                        requiere_aprobacion=True,
                        aprobacion_id=solicitud.id,
                        estado_aprobacion=solicitud.estado,
                        motivo_rechazo=solicitud.motivo_rechazo,
                        precio_minimo=float(precio_minimo_aplicable),
                        producto_id=producto.id,
                        variante_id=variante.id if variante else None,
                        mensaje=(
                            f"'{descripcion}' está por debajo del precio mínimo "
                            f"(${precio_minimo_aplicable:,.2f}). Se envió la solicitud al administrador."
                            if solicitud.estado == "pendiente"
                            else f"La solicitud anterior para '{descripcion}' fue rechazada: {solicitud.motivo_rechazo or 'sin motivo indicado'}."
                        ),
                    ), 409
                aprobaciones_a_consumir.append(aprobacion_activa)

            if not descuenta_stock:
                # El ajuste "Descontar inventario automáticamente" está apagado:
                # se registra la venta sin tocar cantidades de stock ni kardex.
                linea_subtotal = (cantidad_req * precio_unitario) - descuento_item
                subtotal_venta += linea_subtotal
                detalles_a_crear.append({
                    "producto_id": producto.id,
                    "variante_id": variante.id if variante else None,
                    "lote_id": None,
                    "descripcion": descripcion,
                    "tipo_item": "producto",
                    "cantidad": cantidad_req,
                    "precio_unitario": precio_unitario,
                    "subtotal": cantidad_req * precio_unitario,
                    "descuento": descuento_item,
                    "total_linea": linea_subtotal,
                })
            elif producto.controla_lote:
                # Descuento FEFO por lotes
                lotes_disponibles = producto.lotes_disponibles
                stock_lotes = sum((l.cantidad_disponible for l in lotes_disponibles), Decimal("0.00"))

                if stock_lotes < cantidad_req:
                    return jsonify(error=f"Stock insuficiente en lotes para '{descripcion}'. Disponible: {stock_lotes:.2f}, Solicitado: {cantidad_req:.2f}"), 400

                pendiente = cantidad_req
                for lote in lotes_disponibles:
                    if pendiente <= Decimal("0.00"):
                        break
                    descontar = min(lote.cantidad_disponible, pendiente)
                    stock_ant_lote = lote.cantidad_disponible
                    lote.cantidad_disponible -= descontar
                    pendiente -= descontar

                    linea_subtotal = (descontar * precio_unitario) - (descuento_item * (descontar / cantidad_req))
                    subtotal_venta += linea_subtotal

                    detalles_a_crear.append({
                        "producto_id": producto.id,
                        "variante_id": variante.id if variante else None,
                        "lote_id": lote.id,
                        "descripcion": f"{descripcion} - Lote: {lote.numero_lote}",
                        "tipo_item": "producto",
                        "cantidad": descontar,
                        "precio_unitario": precio_unitario,
                        "subtotal": descontar * precio_unitario,
                        "descuento": descuento_item * (descontar / cantidad_req),
                        "total_linea": linea_subtotal,
                    })

                    # Descontar stock acumulado
                    stock_ant_prod = producto.cantidad_stock
                    producto.cantidad_stock -= descontar
                    if variante:
                        variante.cantidad_stock -= descontar

                    movimientos_kardex_a_crear.append(
                        MovimientoStock(
                            producto_id=producto.id,
                            variante_id=variante.id if variante else None,
                            lote_id=lote.id,
                            usuario_id=current_user.id,
                            tipo_movimiento="venta",
                            cantidad=-descontar,
                            stock_anterior=stock_ant_prod,
                            stock_nuevo=producto.cantidad_stock,
                            motivo="Venta en POS",
                        )
                    )
            else:
                # Sin control de lotes
                stock_disp = variante.cantidad_stock if variante else producto.cantidad_stock
                if stock_disp < cantidad_req:
                    return jsonify(error=f"Stock insuficiente para '{descripcion}'. Disponible: {stock_disp:.2f}"), 400

                stock_ant_prod = producto.cantidad_stock
                producto.cantidad_stock -= cantidad_req
                if variante:
                    variante.cantidad_stock -= cantidad_req

                linea_subtotal = (cantidad_req * precio_unitario) - descuento_item
                subtotal_venta += linea_subtotal

                detalles_a_crear.append({
                    "producto_id": producto.id,
                    "variante_id": variante.id if variante else None,
                    "lote_id": None,
                    "descripcion": descripcion,
                    "tipo_item": "producto",
                    "cantidad": cantidad_req,
                    "precio_unitario": precio_unitario,
                    "subtotal": cantidad_req * precio_unitario,
                    "descuento": descuento_item,
                    "total_linea": linea_subtotal,
                })

                movimientos_kardex_a_crear.append(
                    MovimientoStock(
                        producto_id=producto.id,
                        variante_id=variante.id if variante else None,
                        lote_id=None,
                        usuario_id=current_user.id,
                        tipo_movimiento="venta",
                        cantidad=-cantidad_req,
                        stock_anterior=stock_ant_prod,
                        stock_nuevo=producto.cantidad_stock,
                        motivo="Venta en POS",
                    )
                )

        # 2. Calcular total final de la venta
        total_descuentos = sum((d["descuento"] for d in detalles_a_crear), Decimal("0.00")) + descuento_monto_solicitado
        total_venta = max(Decimal("0.00"), subtotal_venta - descuento_monto_solicitado)

        # 3. Validar pagos recibidos
        pagos_a_crear = []
        suma_pagos = Decimal("0.00")
        for p in pagos_req:
            metodo = p.get("metodo_pago")
            monto_pago = Decimal(str(p.get("monto", "0.00")))
            if metodo not in METODOS_PAGO:
                return jsonify(error=f"Método de pago inválido: {metodo}"), 400
            if monto_pago <= Decimal("0.00"):
                continue
            suma_pagos += monto_pago
            pagos_a_crear.append(
                PagoVenta(
                    metodo_pago=metodo,
                    monto=monto_pago,
                    referencia_transaccion=(p.get("referencia") or "").strip() or None,
                    fecha_pago=obtener_hora_bogota(),
                )
            )

        if suma_pagos < total_venta:
            return jsonify(error=f"El total pagado (${suma_pagos:,.2f}) es inferior al total de la factura (${total_venta:,.2f})."), 400

        # 4. Generar encabezado de Venta
        num_factura = generar_numero_factura()
        venta = Venta(
            numero_factura=num_factura,
            turno_caja_id=turno_activo.id,
            tutor_id=tutor_id if tutor_id else None,
            mascota_id=mascota_id if mascota_id else None,
            usuario_id=current_user.id,
            subtotal=subtotal_venta,
            descuento_monto=total_descuentos,
            impuesto_monto=Decimal("0.00"),
            total=total_venta,
            estado="completada",
            fecha_venta=obtener_hora_bogota(),
        )

        db.session.add(venta)
        db.session.flush()

        for det in detalles_a_crear:
            det["venta_id"] = venta.id
            db.session.add(DetalleVenta(**det))

        for m in movimientos_kardex_a_crear:
            m.referencia = f"Factura {num_factura}"
            db.session.add(m)

        for p in pagos_a_crear:
            p.venta_id = venta.id
            db.session.add(p)

        # Marcar como usadas las aprobaciones de precio consumidas en esta venta:
        # no pueden reutilizarse en otra factura.
        for aprobacion in aprobaciones_a_consumir:
            aprobacion.estado = "utilizada"
            aprobacion.venta_id = venta.id

        # Si la venta proviene de una cita de spa, vincularla automáticamente
        cita_spa_id = datos.get("cita_spa_id")
        if cita_spa_id:
            try:
                cita = db.session.get(CitaSpa, int(cita_spa_id))
                if cita:
                    cita.venta_id = venta.id
            except Exception as e:
                current_app.logger.warning(f"No se pudo vincular cita spa {cita_spa_id}: {e}")

        db.session.commit()

        return jsonify(
            ok=True,
            venta_id=venta.id,
            numero_factura=venta.numero_factura,
            total=float(total_venta),
            url=url_for("pos.venta_detalle", id=venta.id),
        )

    except InvalidOperation:
        db.session.rollback()
        return jsonify(error="Formato numérico inválido en precios o montos."), 400
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error al procesar la venta en POS")
        return jsonify(error="Ocurrió un error interno al registrar la venta."), 500


# ---------------------------------------------------------------------------
# Consultas de Ventas y Comprobantes
# ---------------------------------------------------------------------------


@bp.route("/ventas", methods=["GET"])
@login_required
@caja_required
def ventas_lista():
    q = (request.args.get("q") or "").strip()
    estado = (request.args.get("estado") or "").strip()
    metodo = (request.args.get("metodo") or "").strip()

    consulta = select(Venta).options(
        selectinload(Venta.tutor),
        selectinload(Venta.usuario),
        selectinload(Venta.pagos),
    ).order_by(Venta.fecha_venta.desc())

    if q:
        consulta = consulta.filter(Venta.numero_factura.ilike(f"%{q}%"))
    if estado in ESTADOS_VENTA:
        consulta = consulta.filter(Venta.estado == estado)
    if metodo in METODOS_PAGO:
        consulta = consulta.join(PagoVenta).filter(PagoVenta.metodo_pago == metodo)

    ventas = db.session.execute(consulta.limit(50)).scalars().all()
    form_csrf = SoloCsrfForm()

    return render_template(
        "pos/ventas_lista.html",
        ventas=ventas,
        q=q,
        estado=estado,
        metodo=metodo,
        form_csrf=form_csrf,
    )


@bp.route("/venta/<int:id>", methods=["GET"])
@login_required
@caja_required
def venta_detalle(id: int):
    venta = db.session.execute(
        select(Venta)
        .filter_by(id=id)
        .options(
            selectinload(Venta.detalles),
            selectinload(Venta.pagos),
            selectinload(Venta.tutor),
            selectinload(Venta.mascota),
            selectinload(Venta.usuario),
            selectinload(Venta.anulada_por),
        )
    ).scalar_one_or_none()

    if not venta:
        flash("La venta especificada no existe.", "danger")
        return redirect(url_for("pos.ventas_lista"))

    cita_spa = db.session.execute(
        select(CitaSpa).filter_by(venta_id=venta.id)
    ).scalar_one_or_none()

    form_anular = AnularVentaForm()
    return render_template("pos/venta_detalle.html", venta=venta, form_anular=form_anular, cita_spa=cita_spa)


@bp.route("/venta/<int:id>/anular", methods=["POST"])
@login_required
@admin_required
def anular_venta(id: int):

    venta = db.session.get(Venta, id)
    if not venta:
        flash("La venta especificada no existe.", "danger")
        return redirect(url_for("pos.ventas_lista"))

    if venta.estado == "anulada":
        flash("Esta venta ya se encuentra anulada.", "warning")
        return redirect(url_for("pos.venta_detalle", id=id))

    # Regla de negocio: una vez cerrado (arqueado) el turno de caja de esa
    # venta, el día queda bloqueado: no se puede anular ni reeditar.
    if venta.turno_caja and venta.turno_caja.estado == "cerrada":
        flash(
            "No se puede anular: la caja del turno en que se registró esta venta ya fue cerrada y arqueada.",
            "danger",
        )
        return redirect(url_for("pos.venta_detalle", id=id))

    form = AnularVentaForm()
    if form.validate_on_submit():
        try:
            # 1. Revertir stock de los detalles
            detalles = db.session.execute(select(DetalleVenta).filter_by(venta_id=venta.id)).scalars().all()

            for d in detalles:
                if d.tipo_item == "producto" and d.producto_id:
                    producto = db.session.get(Producto, d.producto_id)
                    variante = db.session.get(VarianteProducto, d.variante_id) if d.variante_id else None
                    lote = db.session.get(Lote, d.lote_id) if d.lote_id else None

                    stock_ant = producto.cantidad_stock if producto else Decimal("0.00")

                    if lote:
                        lote.cantidad_disponible += d.cantidad

                    if producto:
                        producto.cantidad_stock += d.cantidad

                    if variante:
                        variante.cantidad_stock += d.cantidad

                    db.session.add(
                        MovimientoStock(
                            producto_id=d.producto_id,
                            variante_id=d.variante_id,
                            lote_id=d.lote_id,
                            usuario_id=current_user.id,
                            tipo_movimiento="devolucion",
                            cantidad=d.cantidad,
                            stock_anterior=stock_ant,
                            stock_nuevo=producto.cantidad_stock if producto else d.cantidad,
                            motivo=f"Anulación de Factura {venta.numero_factura}: {form.motivo.data}",
                            referencia=f"Anulación {venta.numero_factura}",
                        )
                    )

            # 2. Marcar venta como anulada
            venta.estado = "anulada"
            venta.motivo_anulacion = form.motivo.data
            venta.anulada_por_id = current_user.id
            venta.fecha_anulacion = obtener_hora_bogota()

            db.session.commit()
            flash(f"Factura {venta.numero_factura} anulada correctamente y stock revertido.", "success")
            return redirect(url_for("pos.venta_detalle", id=id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al anular la venta %d", id)
            flash("Error interno al intentar anular la venta.", "danger")

    flash("Proporciona un motivo válido de al menos 10 caracteres.", "danger")
    return redirect(url_for("pos.venta_detalle", id=id))


@bp.route("/venta/<int:id>/ticket", methods=["GET"])
@login_required
@caja_required
def ticket_impresion(id: int):
    venta = db.session.execute(
        select(Venta)
        .filter_by(id=id)
        .options(
            selectinload(Venta.detalles),
            selectinload(Venta.pagos),
            selectinload(Venta.tutor),
            selectinload(Venta.mascota),
            selectinload(Venta.usuario),
        )
    ).scalar_one_or_none()

    if not venta:
        flash("La venta especificada no existe.", "danger")
        return redirect(url_for("pos.ventas_lista"))

    cita_spa = db.session.execute(
        select(CitaSpa).filter_by(venta_id=venta.id)
    ).scalar_one_or_none()

    return render_template("pos/ticket.html", venta=venta, cita_spa=cita_spa)



# ---------------------------------------------------------------------------
# Aprobaciones de precio mínimo (regla de negocio crítica #1)
# ---------------------------------------------------------------------------


@bp.route("/aprobaciones/<int:id>/estado", methods=["GET"])
@login_required
@caja_required
def aprobacion_estado(id: int):
    """El terminal de venta consulta este endpoint cada 5 segundos mientras espera."""
    aprobacion = db.session.get(AprobacionPrecio, id)
    if not aprobacion or aprobacion.solicitante_id != current_user.id:
        return jsonify(error="Solicitud no encontrada."), 404
    return jsonify(
        estado=aprobacion.estado,
        precio_solicitado=float(aprobacion.precio_solicitado),
        precio_aprobado=float(aprobacion.precio_aprobado) if aprobacion.precio_aprobado is not None else None,
        motivo_rechazo=aprobacion.motivo_rechazo,
    )


@bp.route("/aprobaciones", methods=["GET"])
@login_required
@admin_required
def aprobaciones_lista():
    pendientes = db.session.execute(
        select(AprobacionPrecio)
        .filter_by(estado="pendiente")
        .options(selectinload(AprobacionPrecio.solicitante), selectinload(AprobacionPrecio.producto), selectinload(AprobacionPrecio.variante))
        .order_by(AprobacionPrecio.fecha_solicitud.asc())
    ).scalars().all()
    resueltas = db.session.execute(
        select(AprobacionPrecio)
        .filter(AprobacionPrecio.estado != "pendiente")
        .options(selectinload(AprobacionPrecio.solicitante), selectinload(AprobacionPrecio.admin))
        .order_by(AprobacionPrecio.fecha_resolucion.desc())
        .limit(20)
    ).scalars().all()
    return render_template(
        "pos/aprobaciones.html",
        pendientes=pendientes,
        resueltas=resueltas,
        form_aprobar=AprobarPrecioForm(),
        form_rechazar=RechazarPrecioForm(),
    )


@bp.route("/aprobaciones/json", methods=["GET"])
@login_required
@admin_required
def aprobaciones_json():
    """IDs de solicitudes pendientes, para que el tablero detecte novedades cada 5s."""
    ids = db.session.execute(
        select(AprobacionPrecio.id).filter_by(estado="pendiente").order_by(AprobacionPrecio.id)
    ).scalars().all()
    return jsonify(ids=ids)


@bp.route("/aprobaciones/<int:id>/aprobar", methods=["POST"])
@login_required
@admin_required
def aprobacion_aprobar(id: int):
    aprobacion = db.session.get(AprobacionPrecio, id)
    if not aprobacion:
        flash("La solicitud no existe.", "danger")
        return redirect(url_for("pos.aprobaciones_lista"))
    if aprobacion.estado != "pendiente":
        flash("Esta solicitud ya fue resuelta.", "warning")
        return redirect(url_for("pos.aprobaciones_lista"))

    form = AprobarPrecioForm()
    if form.validate_on_submit():
        try:
            aprobacion.estado = "aprobado"
            aprobacion.precio_aprobado = form.precio_aprobado.data
            aprobacion.admin_id = current_user.id
            aprobacion.fecha_resolucion = obtener_hora_bogota()
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al aprobar la solicitud de precio %d", id)
            flash("No se pudo aprobar la solicitud.", "danger")
        else:
            flash(f"Precio autorizado para '{aprobacion.descripcion}': ${aprobacion.precio_aprobado:,.2f}.", "success")
    else:
        flash("Indica un precio válido para autorizar.", "danger")
    return redirect(url_for("pos.aprobaciones_lista"))


@bp.route("/aprobaciones/<int:id>/rechazar", methods=["POST"])
@login_required
@admin_required
def aprobacion_rechazar(id: int):
    aprobacion = db.session.get(AprobacionPrecio, id)
    if not aprobacion:
        flash("La solicitud no existe.", "danger")
        return redirect(url_for("pos.aprobaciones_lista"))
    if aprobacion.estado != "pendiente":
        flash("Esta solicitud ya fue resuelta.", "warning")
        return redirect(url_for("pos.aprobaciones_lista"))

    form = RechazarPrecioForm()
    if form.validate_on_submit():
        try:
            aprobacion.estado = "rechazado"
            aprobacion.motivo_rechazo = form.motivo_rechazo.data
            aprobacion.admin_id = current_user.id
            aprobacion.fecha_resolucion = obtener_hora_bogota()
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al rechazar la solicitud de precio %d", id)
            flash("No se pudo rechazar la solicitud.", "danger")
        else:
            flash(f"Solicitud de '{aprobacion.descripcion}' rechazada.", "info")
    else:
        flash("Explica el motivo del rechazo.", "danger")
    return redirect(url_for("pos.aprobaciones_lista"))
