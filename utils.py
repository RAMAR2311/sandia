"""Utilidades transversales de VetCare.

Aquí vive la ÚNICA fuente de hora del sistema (``obtener_hora_bogota``), el
formato de moneda colombiana y los helpers para enlaces de WhatsApp.
"""

import calendar
import re
import unicodedata
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

from flask import current_app
from werkzeug.utils import secure_filename

ZONA_BOGOTA = ZoneInfo("America/Bogota")

MESES_ES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
DIAS_ES = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")


def obtener_hora_bogota() -> datetime:
    """Devuelve la fecha y hora actual en America/Bogota (datetime con zona).

    Todo el código debe usar esta función; nunca ``datetime.now()`` suelto.
    """
    return datetime.now(ZONA_BOGOTA)


def hoy_bogota() -> date:
    """Fecha de hoy según el calendario colombiano."""
    return obtener_hora_bogota().date()


def a_bogota(valor):
    """Normaliza un datetime (con o sin zona) a America/Bogota."""
    if valor is None:
        return None
    if valor.tzinfo is None:
        return valor.replace(tzinfo=ZONA_BOGOTA)
    return valor.astimezone(ZONA_BOGOTA)


def formato_cop(valor) -> str:
    """Formatea un monto en pesos colombianos: ``45000`` -> ``$45.000``.

    Sin decimales y con punto como separador de miles. Acepta Decimal, int,
    str numérico o None (que se muestra como ``$0``).
    """
    if valor is None or valor == "":
        return "$0"
    if not isinstance(valor, Decimal):
        valor = Decimal(str(valor))
    entero = int(valor.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    signo = "-" if entero < 0 else ""
    return f"{signo}${abs(entero):,}".replace(",", ".")


def formato_fecha(valor, con_hora: bool = False) -> str:
    """``12/09/2026`` o ``12/09/2026 3:45 p. m.`` en hora de Bogotá."""
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        valor = a_bogota(valor)
        texto = valor.strftime("%d/%m/%Y")
        if con_hora:
            texto += " " + formato_hora(valor)
        return texto
    return valor.strftime("%d/%m/%Y")


def formato_hora(valor) -> str:
    """``3:45 p. m.`` en hora de Bogotá."""
    if valor is None:
        return ""
    valor = a_bogota(valor)
    hora12 = valor.hour % 12 or 12
    sufijo = "a. m." if valor.hour < 12 else "p. m."
    return f"{hora12}:{valor.minute:02d} {sufijo}"


def fecha_larga(valor) -> str:
    """``lunes, 14 de septiembre de 2026``."""
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        valor = a_bogota(valor)
    return f"{DIAS_ES[valor.weekday()]}, {valor.day} de {MESES_ES[valor.month - 1]} de {valor.year}"


def normalizar_whatsapp(numero: str) -> str:
    """Deja solo dígitos y antepone el indicativo de Colombia si falta.

    ``"310 555 1234"`` -> ``"573105551234"``.
    """
    if not numero:
        return ""
    digitos = "".join(c for c in str(numero) if c.isdigit())
    if len(digitos) == 10 and digitos.startswith("3"):
        digitos = "57" + digitos
    return digitos


def enlace_whatsapp(numero: str, mensaje: str = "") -> str:
    """Construye un enlace ``wa.me`` con el mensaje prellenado (URL-encoded)."""
    digitos = normalizar_whatsapp(numero)
    if not digitos:
        return ""
    enlace = f"https://wa.me/{digitos}"
    if mensaje:
        enlace += "?text=" + quote(mensaje, safe="")
    return enlace


def generar_enlace_google_calendar(
    titulo: str,
    fecha_inicio: datetime | date,
    duracion_minutos: int = 30,
    descripcion: str = "",
    ubicacion: str = "",
) -> str:
    """Genera un enlace para añadir un evento directamente a Google Calendar."""
    if isinstance(fecha_inicio, date) and not isinstance(fecha_inicio, datetime):
        fecha_inicio = datetime.combine(fecha_inicio, datetime.min.time().replace(hour=9))

    fecha_inicio = a_bogota(fecha_inicio)
    fecha_fin = fecha_inicio + timedelta(minutes=duracion_minutos)

    fmt = "%Y%m%dT%H%M%S"
    dates_param = f"{fecha_inicio.strftime(fmt)}/{fecha_fin.strftime(fmt)}"

    params = {
        "action": "TEMPLATE",
        "text": titulo,
        "dates": dates_param,
        "details": descripcion,
        "location": ubicacion,
    }
    return "https://calendar.google.com/calendar/render?" + urlencode(params)


def generar_archivo_ics(
    titulo: str,
    fecha_inicio: datetime | date,
    duracion_minutos: int = 30,
    descripcion: str = "",
    ubicacion: str = "",
    uid: str | None = None,
) -> str:
    """Genera el contenido en formato iCalendar (.ics) compatible con iPhone / Apple Calendar, Outlook y Google."""
    if isinstance(fecha_inicio, date) and not isinstance(fecha_inicio, datetime):
        fecha_inicio = datetime.combine(fecha_inicio, datetime.min.time().replace(hour=9))

    fecha_inicio = a_bogota(fecha_inicio)
    fecha_fin = fecha_inicio + timedelta(minutes=duracion_minutos)

    fmt = "%Y%m%dT%H%M%S"
    uid = uid or f"control-{uuid.uuid4().hex[:12]}@sandiavet.local"
    ahora_utc = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # Limpiar saltos de línea para el estándar ICS
    desc_escapada = descripcion.replace("\r\n", "\\n").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")
    tit_escapado = titulo.replace("\r\n", " ").replace("\n", " ").replace(",", "\\,").replace(";", "\\;")
    loc_escapada = ubicacion.replace("\r\n", " ").replace("\n", " ").replace(",", "\\,").replace(";", "\\;")

    ics_content = (
        "BEGIN:VCALENDAR\r\n"
        "VERSION:2.0\r\n"
        "PRODID:-//Sandia Veterinaria//Control Medico//ES\r\n"
        "CALSCALE:GREGORIAN\r\n"
        "METHOD:PUBLISH\r\n"
        "BEGIN:VEVENT\r\n"
        f"UID:{uid}\r\n"
        f"DTSTAMP:{ahora_utc}\r\n"
        f"DTSTART;TZID=America/Bogota:{fecha_inicio.strftime(fmt)}\r\n"
        f"DTEND;TZID=America/Bogota:{fecha_fin.strftime(fmt)}\r\n"
        f"SUMMARY:{tit_escapado}\r\n"
        f"DESCRIPTION:{desc_escapada}\r\n"
        f"LOCATION:{loc_escapada}\r\n"
        "STATUS:CONFIRMED\r\n"
        "BEGIN:VALARM\r\n"
        "TRIGGER:-PT2H\r\n"
        "ACTION:DISPLAY\r\n"
        f"DESCRIPTION:Recordatorio: {tit_escapado}\r\n"
        "END:VALARM\r\n"
        "END:VEVENT\r\n"
        "END:VCALENDAR\r\n"
    )
    return ics_content



# ---------------------------------------------------------------------------
# Texto y búsqueda
# ---------------------------------------------------------------------------


def normalizar_texto(texto) -> str:
    """Minúsculas, sin tildes y con espacios colapsados: ``"Muñoz  Pérez"`` -> ``"munoz perez"``.

    Se usa para las columnas ``*_busqueda`` y para normalizar lo que escribe el
    usuario, de modo que la búsqueda tolere tildes y mayúsculas.
    """
    if not texto:
        return ""
    descompuesto = unicodedata.normalize("NFKD", str(texto))
    sin_tildes = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


def solo_digitos(texto) -> str:
    return "".join(c for c in str(texto or "") if c.isdigit())


# ---------------------------------------------------------------------------
# Edad
# ---------------------------------------------------------------------------


def edad_texto(fecha_nacimiento, referencia=None) -> str:
    """``"2 años 3 meses"``, ``"5 meses"``, ``"3 semanas"`` o ``"10 días"``."""
    if not fecha_nacimiento:
        return ""
    hoy = referencia or hoy_bogota()
    if fecha_nacimiento > hoy:
        return ""
    anios = hoy.year - fecha_nacimiento.year
    meses = hoy.month - fecha_nacimiento.month
    if hoy.day < fecha_nacimiento.day:
        meses -= 1
    if meses < 0:
        anios -= 1
        meses += 12
    if anios >= 1:
        texto = f"{anios} año" + ("s" if anios != 1 else "")
        if meses:
            texto += f" {meses} mes" + ("es" if meses != 1 else "")
        return texto
    if meses >= 1:
        return f"{meses} mes" + ("es" if meses != 1 else "")
    dias = (hoy - fecha_nacimiento).days
    if dias >= 14:
        return f"{dias // 7} semanas"
    return f"{dias} día" + ("s" if dias != 1 else "")


def edad_en_meses(fecha_nacimiento, referencia=None) -> int:
    """Meses cumplidos entre la fecha de nacimiento y hoy (0 si es futura o None)."""
    if not fecha_nacimiento:
        return 0
    hoy = referencia or hoy_bogota()
    meses = (hoy.year - fecha_nacimiento.year) * 12 + (hoy.month - fecha_nacimiento.month)
    if hoy.day < fecha_nacimiento.day:
        meses -= 1
    return max(meses, 0)


def formato_kg(valor) -> str:
    """``Decimal("4.50")`` -> ``"4,5 kg"``; ``Decimal("10.00")`` -> ``"10 kg"``."""
    if valor is None:
        return ""
    if not isinstance(valor, Decimal):
        valor = Decimal(str(valor))
    texto = f"{valor.normalize():f}".replace(".", ",")
    return f"{texto} kg"


def fecha_desde_edad(anios: int, meses: int, referencia=None) -> date:
    """Fecha de nacimiento aproximada: hoy menos ``anios`` y ``meses``."""
    hoy = referencia or hoy_bogota()
    total_meses = int(anios or 0) * 12 + int(meses or 0)
    anio, mes = hoy.year, hoy.month - total_meses
    while mes <= 0:
        mes += 12
        anio -= 1
    dia = min(hoy.day, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


# ---------------------------------------------------------------------------
# Imágenes subidas (fotos de mascotas)
# ---------------------------------------------------------------------------

EXTENSIONES_IMAGEN = {"jpg", "jpeg", "png", "webp"}
PREFIJO_MINIATURA = "mini_"


def _carpeta_subidas(subcarpeta: str) -> Path:
    carpeta = Path(current_app.config["UPLOAD_FOLDER"]) / subcarpeta
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def guardar_imagen(archivo, subcarpeta: str, lado_maximo: int = 1024, lado_miniatura: int = 300) -> str:
    """Valida, reduce y guarda una imagen subida. Devuelve el nombre generado.

    - Lista blanca de extensiones y verificación real del contenido con Pillow.
    - Nombre único generado por el sistema (nunca el nombre original).
    - Se guarda siempre como JPEG reducido a ``lado_maximo`` px, más una
      miniatura ``mini_<nombre>`` de ``lado_miniatura`` px.
    Lanza ``ValueError`` con un mensaje apto para mostrar al usuario.
    """
    from PIL import Image, ImageOps, UnidentifiedImageError

    nombre_original = secure_filename(archivo.filename or "")
    extension = nombre_original.rsplit(".", 1)[-1].lower() if "." in nombre_original else ""
    if extension not in EXTENSIONES_IMAGEN:
        raise ValueError("Formato no permitido. Usa una foto JPG, PNG o WEBP.")
    try:
        imagen = Image.open(archivo.stream)
        imagen.verify()
        archivo.stream.seek(0)
        imagen = Image.open(archivo.stream)
        imagen.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError("El archivo no es una imagen válida.") from exc

    imagen = ImageOps.exif_transpose(imagen)  # respeta la orientación de la cámara del celular
    if imagen.mode in ("RGBA", "LA", "P"):
        fondo = Image.new("RGB", imagen.size, (255, 255, 255))
        fondo.paste(imagen.convert("RGBA"), mask=imagen.convert("RGBA").getchannel("A"))
        imagen = fondo
    elif imagen.mode != "RGB":
        imagen = imagen.convert("RGB")
    imagen.thumbnail((lado_maximo, lado_maximo))

    carpeta = _carpeta_subidas(subcarpeta)
    nombre = f"{uuid.uuid4().hex}.jpg"
    imagen.save(carpeta / nombre, "JPEG", quality=85, optimize=True)
    miniatura = imagen.copy()
    miniatura.thumbnail((lado_miniatura, lado_miniatura))
    miniatura.save(carpeta / f"{PREFIJO_MINIATURA}{nombre}", "JPEG", quality=80, optimize=True)
    return nombre


def eliminar_imagen(subcarpeta: str, nombre: str) -> None:
    """Borra la imagen y su miniatura si existen (los errores no interrumpen el flujo)."""
    if not nombre:
        return
    carpeta = Path(current_app.config["UPLOAD_FOLDER"]) / subcarpeta
    for ruta in (carpeta / nombre, carpeta / f"{PREFIJO_MINIATURA}{nombre}"):
        try:
            ruta.unlink(missing_ok=True)
        except OSError:
            current_app.logger.warning("No se pudo borrar la imagen %s", ruta)


EXTENSIONES_DOCUMENTO = {"pdf", "jpg", "jpeg", "png", "webp", "doc", "docx", "dcm", "dicom", "txt"}


def guardar_documento(archivo, subcarpeta: str) -> str:
    """Guarda un documento adjunto (consentimientos, resultados, comprobantes,
    facturas de proveedor) con lista blanca de extensiones y nombre generado
    por el sistema. Devuelve el nombre guardado. Lanza ``ValueError`` con un
    mensaje apto para mostrar al usuario si el archivo no es válido."""
    nombre_original = secure_filename(archivo.filename or "")
    extension = nombre_original.rsplit(".", 1)[-1].lower() if "." in nombre_original else ""
    if extension not in EXTENSIONES_DOCUMENTO:
        raise ValueError("Formato no permitido. Usa PDF, JPG, PNG, WEBP, DOCX o DICOM.")
    carpeta = Path(current_app.config["UPLOAD_FOLDER"]) / subcarpeta
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = f"{uuid.uuid4().hex}.{extension}"
    archivo.save(carpeta / nombre)
    return nombre


def eliminar_documento(subcarpeta: str, nombre: str) -> None:
    """Borra un documento adjunto si existe (los errores no interrumpen el flujo)."""
    if not nombre:
        return
    ruta = Path(current_app.config["UPLOAD_FOLDER"]) / subcarpeta / nombre
    try:
        ruta.unlink(missing_ok=True)
    except OSError:
        current_app.logger.warning("No se pudo borrar el documento %s", ruta)


def guardar_firma_digital(origen, subcarpeta: str = "firmas") -> str:
    """Guarda una firma digital (desde archivo subido o base64 canvas) como PNG transparente.

    Retorna el nombre del archivo generado dentro de `subcarpeta`.
    """
    import base64
    import io
    from PIL import Image, ImageOps, UnidentifiedImageError

    carpeta = _carpeta_subidas(subcarpeta)
    nombre = f"firma_{uuid.uuid4().hex}.png"
    destino = carpeta / nombre

    if isinstance(origen, str) and origen.startswith("data:image"):
        # Viene como Data URL de canvas
        try:
            encabezado, data_b64 = origen.split(",", 1)
            datos_bytes = base64.b64decode(data_b64)
            img = Image.open(io.BytesIO(datos_bytes))
            img = img.convert("RGBA")
            # Reducir si es muy grande pero preservando calidad
            img.thumbnail((800, 400))
            img.save(destino, "PNG", optimize=True)
            return nombre
        except Exception as exc:
            raise ValueError("No se pudo procesar el trazo de la firma digital.") from exc
    elif hasattr(origen, "stream") or hasattr(origen, "read"):
        # Viene como archivo subido (FileStorage)
        nombre_orig = secure_filename(getattr(origen, "filename", "") or "")
        ext = nombre_orig.rsplit(".", 1)[-1].lower() if "." in nombre_orig else ""
        if ext not in EXTENSIONES_IMAGEN:
            raise ValueError("Formato de firma no permitido. Usa una imagen PNG, JPG o WEBP.")
        try:
            img = Image.open(origen.stream)
            img.load()
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGBA", "RGB"):
                img = img.convert("RGBA")
            img.thumbnail((900, 450))
            img.save(destino, "PNG", optimize=True)
            return nombre
        except Exception as exc:
            raise ValueError("El archivo subido no es una imagen válida.") from exc
    else:
        raise ValueError("Origen de firma inválido.")


def eliminar_firma_digital(nombre: str, subcarpeta: str = "firmas") -> None:
    """Elimina el archivo de firma física si existe."""
    if not nombre or nombre.startswith("data:") or "/" in nombre or "\\" in nombre:
        return
    ruta = Path(current_app.config["UPLOAD_FOLDER"]) / subcarpeta / nombre
    try:
        ruta.unlink(missing_ok=True)
    except OSError:
        current_app.logger.warning("No se pudo borrar la firma %s", ruta)

