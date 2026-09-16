"""Mascotas: directorio, ficha (centro de todo), fotos, curva de peso y línea de tiempo."""

from datetime import datetime, time

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from decorators import admin_required, recepcion_required
from forms import FallecimientoForm, FotoForm, MascotaForm, RegistroPesoForm, SoloCsrfForm
from models import (
    ESPECIES,
    Cirugia,
    Cita,
    CitaSpa,
    ConsentimientoEmitido,
    ConsultaMedica,
    DesparasitacionMascota,
    ExamenLaboratorio,
    Hospitalizacion,
    Mascota,
    Raza,
    RegistroPeso,
    RemisionInterna,
    Tutor,
    VacunaMascota,
    db,
)
from utils import (
    ZONA_BOGOTA,
    edad_en_meses,
    eliminar_imagen,
    formato_kg,
    guardar_imagen,
    hoy_bogota,
    normalizar_texto,
    obtener_hora_bogota,
)

bp = Blueprint("mascotas", __name__, url_prefix="/mascotas")

POR_PAGINA = 12
CARPETA_FOTOS = "mascotas"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _opciones_raza(especie: str):
    razas = db.session.execute(
        select(Raza).where(Raza.especie == especie, Raza.activo.is_(True)).order_by(Raza.nombre)
    ).scalars()
    return [(0, "Sin especificar")] + [(raza.id, raza.nombre) for raza in razas]


def _raza_valida(raza_id, especie: str):
    """Devuelve la raza si pertenece a la especie; ``None`` si no se eligió; ``False`` si es inválida."""
    if not raza_id:
        return None
    raza = db.session.get(Raza, raza_id)
    if raza is None or raza.especie != especie:
        return False
    return raza


def _tutor_valido(tutor_id):
    try:
        tutor = db.session.get(Tutor, int(tutor_id))
    except (TypeError, ValueError):
        return None
    return tutor if tutor is not None and tutor.activo else None


def _aplicar_formulario(mascota: Mascota, form: MascotaForm, raza) -> None:
    mascota.nombre = form.nombre.data
    mascota.especie = form.especie.data
    mascota.raza_id = raza.id if raza else None
    mascota.sexo = form.sexo.data
    mascota.fecha_nacimiento, mascota.fecha_nacimiento_estimada = form.fecha_nacimiento_resuelta()
    mascota.tamano = form.tamano.data or None
    mascota.color = form.color.data
    mascota.senas_particulares = (form.senas_particulares.data or "").strip() or None
    mascota.microchip = form.microchip.data
    mascota.esterilizado = form.esterilizado.data
    mascota.alergias = (form.alergias.data or "").strip() or None
    mascota.condiciones_preexistentes = (form.condiciones_preexistentes.data or "").strip() or None


def _microchip_en_uso(microchip, excluir_id=None) -> bool:
    if not microchip:
        return False
    consulta = select(Mascota.id).where(Mascota.microchip == microchip.strip())
    if excluir_id is not None:
        consulta = consulta.where(Mascota.id != excluir_id)
    return db.session.execute(consulta).first() is not None


def _procesar_foto(form_campo):
    """Guarda la foto subida si la hay. Devuelve el nombre o ``None``; agrega errores al campo."""
    archivo = form_campo.data
    if not archivo or not getattr(archivo, "filename", ""):
        return None
    try:
        return guardar_imagen(archivo, CARPETA_FOTOS)
    except ValueError as exc:
        form_campo.errors.append(str(exc))
        return None


def _fecha_hora_desde_dia(dia):
    """Fecha elegida a las 12:00 de Bogotá; si es hoy o no hay fecha, ahora mismo."""
    if dia is None or dia == hoy_bogota():
        return obtener_hora_bogota()
    return datetime.combine(dia, time(12, 0), tzinfo=ZONA_BOGOTA)


def construir_linea_tiempo(mascota: Mascota) -> list[dict]:
    """Eventos cronológicos integrales de la mascota (consultas SOAP, spa, vacunas, citas, ingresos, etc.)."""
    eventos = [
        {
            "fecha": mascota.fecha_registro,
            "tipo": "registro",
            "categoria": "Registro",
            "icono": "bi-clipboard2-plus",
            "color": "primary",
            "titulo": "Registro en el sistema",
            "detalle": f"Registrado por {mascota.creado_por.nombre}" if mascota.creado_por else "",
            "url": None,
        }
    ]

    # 1. Consultas Médicas SOAP
    consultas = db.session.execute(
        select(ConsultaMedica).where(ConsultaMedica.mascota_id == mascota.id).order_by(ConsultaMedica.fecha_hora.desc())
    ).scalars().all()
    for c in consultas:
        vet_nombre = c.veterinario.nombre if c.veterinario else "Veterinario"
        diag = c.diagnostico or c.motivo_consulta or "Consulta clínica"
        eventos.append({
            "fecha": c.fecha_hora,
            "tipo": "consulta",
            "categoria": "Consulta Médica",
            "icono": "bi-journal-medical",
            "color": "danger",
            "titulo": f"Consulta SOAP: {diag[:60]}",
            "detalle": f"Atendido por {vet_nombre} · Motivo: {c.motivo_consulta or 'Revisión general'}",
            "url": url_for("historias.consulta_detalle", id=c.id),
        })

    # 2. Servicios de Spa y Peluquería
    citas_spa = db.session.execute(
        select(CitaSpa).where(CitaSpa.mascota_id == mascota.id).order_by(CitaSpa.fecha_hora.desc())
    ).scalars().all()
    for s in citas_spa:
        servicio_nom = s.servicio_spa.nombre if s.servicio_spa else "Servicio Spa / Peluquería"
        groomer_nom = s.groomer.nombre if s.groomer else "Estilista"
        estado_spa = s.estado_etiqueta if hasattr(s, "estado_etiqueta") else s.estado
        eventos.append({
            "fecha": s.fecha_hora,
            "tipo": "spa",
            "categoria": "Spa & Grooming",
            "icono": "bi-scissors",
            "color": "warning",
            "titulo": f"Spa: {servicio_nom}",
            "detalle": f"Estado: {estado_spa} · A cargo de {groomer_nom}{(' · ' + s.notas_ingreso) if s.notas_ingreso else ''}",
            "url": url_for("spa.cita_detalle", id=s.id),
            "foto_ingreso": s.url_mini_ingreso,
            "foto_salida": s.url_mini_salida,
        })

    # 3. Citas Médicas Agendadas
    citas_agenda = db.session.execute(
        select(Cita).where(Cita.mascota_id == mascota.id).order_by(Cita.fecha_hora.desc())
    ).scalars().all()
    for a in citas_agenda:
        prof = a.profesional.nombre if a.profesional else "General"
        eventos.append({
            "fecha": a.fecha_hora,
            "tipo": "cita",
            "categoria": "Cita Agendada",
            "icono": "bi-calendar2-check",
            "color": "info",
            "titulo": f"Cita: {a.tipo_etiqueta}",
            "detalle": f"Estado: {a.estado.capitalize()} · Con {prof}{(' · ' + a.motivo) if a.motivo else ''}",
            "url": url_for("agenda.detalle", id=a.id),
        })

    # 4. Hospitalizaciones / Ingresos
    hosps = db.session.execute(
        select(Hospitalizacion).where(Hospitalizacion.mascota_id == mascota.id).order_by(Hospitalizacion.fecha_ingreso.desc())
    ).scalars().all()
    for h in hosps:
        vet = h.veterinario_responsable.nombre if h.veterinario_responsable else "Veterinario"
        jaula = f"Jaula: {h.jaula}" if h.jaula else ""
        eventos.append({
            "fecha": h.fecha_ingreso,
            "tipo": "hospitalizacion",
            "categoria": "Ingreso Hospitalario",
            "icono": "bi-hospital",
            "color": "danger",
            "titulo": f"Ingreso Hospitalario ({h.estado.capitalize()})",
            "detalle": f"Motivo: {h.motivo or 'Observación clínica'} · {jaula} · Responsable: {vet}",
            "url": url_for("historias.hospitalizacion_detalle", id=h.id),
        })

    # 5. Cirugías
    cirugias = db.session.execute(
        select(Cirugia).where(Cirugia.mascota_id == mascota.id).order_by(Cirugia.fecha.desc())
    ).scalars().all()
    for cir in cirugias:
        vet = cir.veterinario.nombre if cir.veterinario else "Cirujano"
        fecha_dt = _fecha_hora_desde_dia(cir.fecha)
        eventos.append({
            "fecha": fecha_dt,
            "tipo": "cirugia",
            "categoria": "Cirugía",
            "icono": "bi-bandaid",
            "color": "danger",
            "titulo": f"Cirugía: {cir.tipo_procedimiento}",
            "detalle": f"Cirujano: {vet}{(' · ' + cir.notas_postquirurgicas[:60]) if cir.notas_postquirurgicas else ''}",
            "url": url_for("historias.cirugia_detalle", id=cir.id),
        })

    # 6. Vacunas
    vacunas = db.session.execute(
        select(VacunaMascota).where(VacunaMascota.mascota_id == mascota.id).order_by(VacunaMascota.fecha_aplicacion.desc())
    ).scalars().all()
    for v in vacunas:
        fecha_dt = _fecha_hora_desde_dia(v.fecha_aplicacion)
        prox = f" · Próxima: {v.fecha_proxima.strftime('%d/%m/%Y')}" if v.fecha_proxima else ""
        eventos.append({
            "fecha": fecha_dt,
            "tipo": "vacuna",
            "categoria": "Vacunación",
            "icono": "bi-shield-check",
            "color": "success",
            "titulo": f"Vacuna: {v.nombre_vacuna}",
            "detalle": f"Lote: {v.lote or 'N/A'}{prox}",
            "url": url_for("historias.ficha_medica", mascota_id=mascota.id),
        })

    # 7. Desparasitaciones
    desparasitaciones = db.session.execute(
        select(DesparasitacionMascota).where(DesparasitacionMascota.mascota_id == mascota.id).order_by(DesparasitacionMascota.fecha_aplicacion.desc())
    ).scalars().all()
    for d in desparasitaciones:
        fecha_dt = _fecha_hora_desde_dia(d.fecha_aplicacion)
        prox = f" · Próxima: {d.fecha_proxima.strftime('%d/%m/%Y')}" if d.fecha_proxima else ""
        eventos.append({
            "fecha": fecha_dt,
            "tipo": "desparasitacion",
            "categoria": "Desparasitación",
            "icono": "bi-bug",
            "color": "success",
            "titulo": f"Desparasitación: {d.producto}",
            "detalle": f"Tipo: {d.tipo.capitalize()}{prox}",
            "url": url_for("historias.ficha_medica", mascota_id=mascota.id),
        })

    # 8. Registros de peso
    for peso in mascota.registros_peso:
        eventos.append({
            "fecha": peso.fecha,
            "tipo": "peso",
            "categoria": "Control de Peso",
            "icono": "bi-speedometer2",
            "color": "secondary",
            "titulo": f"Peso registrado: {formato_kg(peso.peso_kg)}",
            "detalle": f"Por {peso.registrado_por.nombre}" if peso.registrado_por else "",
            "url": None,
        })

    # 9. Exámenes de laboratorio
    examenes = db.session.execute(
        select(ExamenLaboratorio).where(ExamenLaboratorio.mascota_id == mascota.id).order_by(ExamenLaboratorio.fecha_toma.desc())
    ).scalars().all()
    for ex in examenes:
        fecha_dt = _fecha_hora_desde_dia(ex.fecha_toma) if ex.fecha_toma else ex.fecha_registro
        eventos.append({
            "fecha": fecha_dt,
            "tipo": "laboratorio",
            "categoria": "Laboratorio",
            "icono": "bi-file-earmark-medical",
            "color": "primary",
            "titulo": f"Examen: {ex.tipo_examen}",
            "detalle": f"Estado: {ex.estado.capitalize()}{(' · Lab: ' + ex.laboratorio_externo) if ex.laboratorio_externo else ''}",
            "url": url_for("historias.examen_detalle", id=ex.id),
        })

    # 10. Remisiones Clínicas Internas
    remisiones = db.session.execute(
        select(RemisionInterna).where(RemisionInterna.mascota_id == mascota.id).order_by(RemisionInterna.fecha_remision.desc())
    ).scalars().all()
    for rem in remisiones:
        vet_nom = rem.veterinario.nombre if rem.veterinario else "Veterinario"
        dest = f" a {rem.centro_medico_destino}" if rem.centro_medico_destino else ""
        eventos.append({
            "fecha": rem.fecha_remision,
            "tipo": "remision",
            "categoria": "Remisión",
            "icono": "bi-send-check-fill",
            "color": "info",
            "titulo": f"Remisión: {rem.especialidad_destino}{dest}",
            "detalle": f"Motivo: {rem.motivo_remision[:70]} · Remitido por: {vet_nom}",
            "url": url_for("historias.ficha_medica", mascota_id=mascota.id, tab="remisiones"),
        })

    # 11. Consentimientos Informados Digitales
    for cons in mascota.consentimientos:
        estado_badge = "Firmado" if cons.esta_firmado else "Pendiente de firma"
        eventos.append({
            "fecha": cons.creado_en,
            "tipo": "consentimiento",
            "categoria": "Consentimiento",
            "icono": "bi-shield-check" if cons.esta_firmado else "bi-file-earmark-medical",
            "color": "danger",
            "titulo": f"Consentimiento: {cons.titulo}",
            "detalle": f"Estado: {estado_badge} · Tipo: {cons.tipo_etiqueta}",
            "url": url_for("historias.ficha_medica", mascota_id=mascota.id, tab="consentimientos"),
        })

    if mascota.fallecido and mascota.fecha_fallecimiento:
        eventos.append({
            "fecha": datetime.combine(mascota.fecha_fallecimiento, time(23, 59), tzinfo=ZONA_BOGOTA),
            "tipo": "fallecimiento",
            "categoria": "Estado",
            "icono": "bi-heart",
            "color": "dark",
            "titulo": "Fallecimiento",
            "detalle": "",
            "url": None,
        })

    eventos.sort(key=lambda evento: evento["fecha"] or datetime.min.replace(tzinfo=ZONA_BOGOTA), reverse=True)
    return eventos


def obtener_resumen_atenciones(mascota: Mascota) -> dict:
    """Calcula las últimas atenciones clave y el conteo de visitas para vista rápida."""
    ultima_consulta = db.session.execute(
        select(ConsultaMedica).where(ConsultaMedica.mascota_id == mascota.id).order_by(ConsultaMedica.fecha_hora.desc()).limit(1)
    ).scalar_one_or_none()

    ultimo_spa = db.session.execute(
        select(CitaSpa).where(CitaSpa.mascota_id == mascota.id).order_by(CitaSpa.fecha_hora.desc()).limit(1)
    ).scalar_one_or_none()

    ultima_cita = db.session.execute(
        select(Cita).where(Cita.mascota_id == mascota.id).order_by(Cita.fecha_hora.desc()).limit(1)
    ).scalar_one_or_none()

    ultima_vacuna = db.session.execute(
        select(VacunaMascota).where(VacunaMascota.mascota_id == mascota.id).order_by(VacunaMascota.fecha_aplicacion.desc()).limit(1)
    ).scalar_one_or_none()

    ultimo_ingreso = db.session.execute(
        select(Hospitalizacion).where(Hospitalizacion.mascota_id == mascota.id).order_by(Hospitalizacion.fecha_ingreso.desc()).limit(1)
    ).scalar_one_or_none()

    total_visitas = (
        db.session.query(ConsultaMedica).filter_by(mascota_id=mascota.id).count()
        + db.session.query(CitaSpa).filter_by(mascota_id=mascota.id).count()
        + db.session.query(Hospitalizacion).filter_by(mascota_id=mascota.id).count()
    )

    return {
        "ultima_consulta": ultima_consulta,
        "ultimo_spa": ultimo_spa,
        "ultima_cita": ultima_cita,
        "ultima_vacuna": ultima_vacuna,
        "ultimo_ingreso": ultimo_ingreso,
        "total_visitas": total_visitas,
    }


# ---------------------------------------------------------------------------
# Listado y creación
# ---------------------------------------------------------------------------


@bp.route("/")
@login_required
def lista():
    texto = request.args.get("q", "").strip()
    especie = request.args.get("especie", "").strip()
    estado = request.args.get("estado", "activas")
    pagina = request.args.get("page", 1, type=int)

    consulta = (
        select(Mascota)
        .join(Mascota.tutor)
        .options(
            selectinload(Mascota.tutor),
            selectinload(Mascota.raza),
            selectinload(Mascota.registros_peso),
        )
    )
    normalizado = normalizar_texto(texto)
    if normalizado:
        consulta = consulta.where(
            Mascota.nombre_busqueda.ilike(f"%{normalizado}%") | Tutor.nombre_busqueda.ilike(f"%{normalizado}%")
        )
    if especie in ESPECIES:
        consulta = consulta.where(Mascota.especie == especie)
    if estado == "activas":
        consulta = consulta.where(Mascota.activo.is_(True), Mascota.fallecido.is_(False))
    elif estado == "inactivas":
        consulta = consulta.where((Mascota.activo.is_(False)) | (Mascota.fallecido.is_(True)))
    consulta = consulta.order_by(Mascota.nombre_busqueda)
    paginacion = db.paginate(consulta, page=pagina, per_page=POR_PAGINA, error_out=False)
    return render_template(
        "mascotas/lista.html",
        pagina=paginacion,
        filtro_texto=texto,
        filtro_especie=especie,
        filtro_estado=estado,
    )


@bp.route("/nueva", methods=["GET", "POST"])
@login_required
@recepcion_required
def nueva():
    form = MascotaForm()
    tutor = None
    if request.method == "GET":
        tutor = _tutor_valido(request.args.get("tutor_id"))
        if tutor is not None:
            form.tutor_id.data = str(tutor.id)
        form.especie.data = form.especie.data or "canino"
    else:
        tutor = _tutor_valido(form.tutor_id.data)
    form.raza_id.choices = _opciones_raza(form.especie.data or "canino")

    if form.validate_on_submit():
        raza = _raza_valida(form.raza_id.data, form.especie.data)
        if tutor is None:
            form.tutor_id.errors.append("Selecciona un tutor activo.")
        elif raza is False:
            form.raza_id.errors.append("La raza no corresponde a la especie elegida.")
        elif _microchip_en_uso(form.microchip.data):
            form.microchip.errors.append("Ya hay una mascota registrada con ese microchip.")
        else:
            nombre_foto = _procesar_foto(form.foto)
            if not form.foto.errors:
                mascota = Mascota(tutor_id=tutor.id, creado_por_id=current_user.id, foto=nombre_foto)
                _aplicar_formulario(mascota, form, raza)
                try:
                    db.session.add(mascota)
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    eliminar_imagen(CARPETA_FOTOS, nombre_foto)
                    current_app.logger.exception("Error al crear mascota")
                    flash("No se pudo guardar la mascota. Inténtalo de nuevo.", "danger")
                else:
                    flash(f"{mascota.nombre} quedó registrado/a.", "success")
                    return redirect(url_for("mascotas.detalle", mascota_id=mascota.id))
    return render_template("mascotas/form.html", form=form, mascota=None, tutor=tutor)


# ---------------------------------------------------------------------------
# Ficha
# ---------------------------------------------------------------------------


@bp.route("/<int:mascota_id>")
@login_required
def detalle(mascota_id):
    mascota = db.session.get(Mascota, mascota_id)
    if mascota is None:
        abort(404)
    datos_peso = [
        {"fecha": peso.fecha.astimezone(ZONA_BOGOTA).strftime("%Y-%m-%d"), "peso": float(peso.peso_kg)}
        for peso in mascota.registros_peso
    ]
    return render_template(
        "mascotas/detalle.html",
        mascota=mascota,
        resumen=obtener_resumen_atenciones(mascota),
        eventos=construir_linea_tiempo(mascota),
        datos_peso=datos_peso,
        form_peso=RegistroPesoForm(fecha=hoy_bogota()),
        form_foto=FotoForm(),
        form_fallecimiento=FallecimientoForm(fecha_fallecimiento=hoy_bogota()),
        form_csrf=SoloCsrfForm(),
    )


@bp.route("/<int:mascota_id>/editar", methods=["GET", "POST"])
@login_required
@recepcion_required
def editar(mascota_id):
    mascota = db.session.get(Mascota, mascota_id)
    if mascota is None:
        abort(404)
    form = MascotaForm(obj=mascota)
    if request.method == "GET":
        form.tutor_id.data = str(mascota.tutor_id)
        form.raza_id.data = mascota.raza_id or 0
        form.tamano.data = mascota.tamano or ""
        form.conoce_fecha.data = not mascota.fecha_nacimiento_estimada
        if mascota.fecha_nacimiento_estimada and mascota.fecha_nacimiento:
            form.edad_anios.data, form.edad_meses.data = divmod(edad_en_meses(mascota.fecha_nacimiento), 12)
            form.fecha_nacimiento.data = None
        tutor = mascota.tutor
    else:
        tutor = _tutor_valido(form.tutor_id.data)
    form.raza_id.choices = _opciones_raza(form.especie.data or mascota.especie)

    if form.validate_on_submit():
        raza = _raza_valida(form.raza_id.data, form.especie.data)
        if tutor is None:
            form.tutor_id.errors.append("Selecciona un tutor activo.")
        elif raza is False:
            form.raza_id.errors.append("La raza no corresponde a la especie elegida.")
        elif _microchip_en_uso(form.microchip.data, excluir_id=mascota.id):
            form.microchip.errors.append("Ya hay otra mascota registrada con ese microchip.")
        else:
            nombre_foto = _procesar_foto(form.foto)
            if not form.foto.errors:
                foto_anterior = mascota.foto
                mascota.tutor_id = tutor.id
                _aplicar_formulario(mascota, form, raza)
                if nombre_foto:
                    mascota.foto = nombre_foto
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                    eliminar_imagen(CARPETA_FOTOS, nombre_foto)
                    current_app.logger.exception("Error al editar mascota %s", mascota_id)
                    flash("No se pudieron guardar los cambios. Inténtalo de nuevo.", "danger")
                else:
                    if nombre_foto and foto_anterior:
                        eliminar_imagen(CARPETA_FOTOS, foto_anterior)
                    flash("Cambios guardados.", "success")
                    return redirect(url_for("mascotas.detalle", mascota_id=mascota.id))
    return render_template("mascotas/form.html", form=form, mascota=mascota, tutor=tutor)


@bp.route("/<int:mascota_id>/foto", methods=["POST"])
@login_required
@recepcion_required
def subir_foto(mascota_id):
    mascota = db.session.get(Mascota, mascota_id)
    if mascota is None:
        abort(404)
    form = FotoForm()
    if form.validate_on_submit():
        nombre_foto = _procesar_foto(form.foto)
        if nombre_foto:
            foto_anterior = mascota.foto
            mascota.foto = nombre_foto
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                eliminar_imagen(CARPETA_FOTOS, nombre_foto)
                current_app.logger.exception("Error al guardar la foto de la mascota %s", mascota_id)
                flash("No se pudo guardar la foto.", "danger")
            else:
                eliminar_imagen(CARPETA_FOTOS, foto_anterior)
                flash("Foto actualizada.", "success")
            return redirect(url_for("mascotas.detalle", mascota_id=mascota.id))
    for errores in form.errors.values():
        for error in errores:
            flash(error, "danger")
    return redirect(url_for("mascotas.detalle", mascota_id=mascota.id))


# ---------------------------------------------------------------------------
# Peso
# ---------------------------------------------------------------------------


@bp.route("/<int:mascota_id>/peso", methods=["POST"])
@login_required
@recepcion_required
def registrar_peso(mascota_id):
    mascota = db.session.get(Mascota, mascota_id)
    if mascota is None:
        abort(404)
    form = RegistroPesoForm()
    if form.validate_on_submit():
        registro = RegistroPeso(
            mascota_id=mascota.id,
            peso_kg=form.peso_kg.data,
            fecha=_fecha_hora_desde_dia(form.fecha.data),
            registrado_por_id=current_user.id,
        )
        try:
            db.session.add(registro)
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al registrar peso de la mascota %s", mascota_id)
            flash("No se pudo registrar el peso.", "danger")
        else:
            flash(f"Peso de {formato_kg(registro.peso_kg)} registrado.", "success")
        return redirect(url_for("mascotas.detalle", mascota_id=mascota.id) + "#peso")
    for errores in form.errors.values():
        for error in errores:
            flash(error, "danger")
    return redirect(url_for("mascotas.detalle", mascota_id=mascota.id) + "#peso")


@bp.route("/<int:mascota_id>/peso/<int:peso_id>/eliminar", methods=["POST"])
@login_required
@admin_required
def eliminar_peso(mascota_id, peso_id):
    """Solo el administrador corrige un peso mal digitado; queda en el log."""
    registro = db.session.get(RegistroPeso, peso_id)
    if registro is None or registro.mascota_id != mascota_id:
        abort(404)
    form = SoloCsrfForm()
    if not form.validate_on_submit():
        abort(400)
    try:
        current_app.logger.info(
            "Peso %s (%s kg del %s) de la mascota %s eliminado por %s",
            registro.id, registro.peso_kg, registro.fecha, mascota_id, current_user.email,
        )
        db.session.delete(registro)
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error al eliminar el peso %s", peso_id)
        flash("No se pudo eliminar el registro.", "danger")
    else:
        flash("Registro de peso eliminado.", "success")
    return redirect(url_for("mascotas.detalle", mascota_id=mascota_id) + "#peso")


# ---------------------------------------------------------------------------
# Estado: fallecimiento y borrado lógico
# ---------------------------------------------------------------------------


@bp.route("/<int:mascota_id>/fallecimiento", methods=["POST"])
@login_required
@recepcion_required
def registrar_fallecimiento(mascota_id):
    mascota = db.session.get(Mascota, mascota_id)
    if mascota is None:
        abort(404)
    form = FallecimientoForm()
    if form.validate_on_submit():
        try:
            mascota.fallecido = True
            mascota.fecha_fallecimiento = form.fecha_fallecimiento.data
            db.session.commit()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error al registrar fallecimiento de la mascota %s", mascota_id)
            flash("No se pudo registrar el fallecimiento.", "danger")
        else:
            current_app.logger.info("Mascota %s marcada como fallecida por %s", mascota.id, current_user.email)
            flash(f"Se registró el fallecimiento de {mascota.nombre}.", "info")
    else:
        for errores in form.errors.values():
            for error in errores:
                flash(error, "danger")
    return redirect(url_for("mascotas.detalle", mascota_id=mascota.id))


@bp.route("/<int:mascota_id>/fallecimiento/deshacer", methods=["POST"])
@login_required
@recepcion_required
def deshacer_fallecimiento(mascota_id):
    mascota = db.session.get(Mascota, mascota_id)
    if mascota is None:
        abort(404)
    form = SoloCsrfForm()
    if not form.validate_on_submit():
        abort(400)
    try:
        mascota.fallecido = False
        mascota.fecha_fallecimiento = None
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error al deshacer fallecimiento de la mascota %s", mascota_id)
        flash("No se pudo deshacer.", "danger")
    else:
        current_app.logger.info("Fallecimiento de la mascota %s deshecho por %s", mascota.id, current_user.email)
        flash("Fallecimiento deshecho.", "success")
    return redirect(url_for("mascotas.detalle", mascota_id=mascota.id))


@bp.route("/<int:mascota_id>/estado", methods=["POST"])
@login_required
@recepcion_required
def cambiar_estado(mascota_id):
    mascota = db.session.get(Mascota, mascota_id)
    if mascota is None:
        abort(404)
    form = SoloCsrfForm()
    if not form.validate_on_submit():
        abort(400)
    try:
        mascota.activo = not mascota.activo
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Error al cambiar estado de la mascota %s", mascota_id)
        flash("No se pudo cambiar el estado.", "danger")
    else:
        accion = "reactivada" if mascota.activo else "desactivada"
        current_app.logger.info("Mascota %s %s por %s", mascota.id, accion, current_user.email)
        flash(f"Ficha {accion}.", "success")
    return redirect(url_for("mascotas.detalle", mascota_id=mascota.id))
