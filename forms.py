"""Formularios Flask-WTF. Todos llevan token CSRF automáticamente."""

from decimal import Decimal

from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import (
    BooleanField,
    DateField,
    DateTimeField,
    TimeField,
    DecimalField,
    HiddenField,
    IntegerField,
    PasswordField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Email, EqualTo, InputRequired, Length, NumberRange, Optional, Regexp, ValidationError

from models import (
    CATEGORIAS_EXAMEN,
    CATEGORIAS_GASTO,
    CATEGORIAS_PRODUCTO,
    ESPECIES,
    ESTADOS_CITA,
    ESTADOS_EXAMEN,
    ROLES,
    SEXOS,
    TAMANOS,
    TIPOS_CITA,
    TIPOS_DOCUMENTO,
    TIPOS_GASTO,
    UNIDADES_MEDIDA,
)
from utils import fecha_desde_edad, hoy_bogota, solo_digitos

LONGITUD_MINIMA_PASSWORD = 8

# Validación de correo sencilla a propósito: el personal puede usar direcciones
# internas como nombre@sandia.local, que los validadores estrictos rechazan.
CORREO_VALIDO = Regexp(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", message="Correo no válido.")


# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------


class LoginForm(FlaskForm):
    email = StringField("Correo electrónico", validators=[DataRequired("Escribe tu correo."), CORREO_VALIDO])
    password = PasswordField("Contraseña", validators=[DataRequired("Escribe tu contraseña.")])
    enviar = SubmitField("Ingresar")


class CambiarPasswordForm(FlaskForm):
    password_actual = PasswordField("Contraseña actual", validators=[DataRequired("Escribe tu contraseña actual.")])
    password_nueva = PasswordField(
        "Nueva contraseña",
        validators=[
            DataRequired("Escribe la nueva contraseña."),
            Length(min=LONGITUD_MINIMA_PASSWORD, message=f"Mínimo {LONGITUD_MINIMA_PASSWORD} caracteres."),
        ],
    )
    password_confirmacion = PasswordField(
        "Confirmar nueva contraseña",
        validators=[DataRequired("Repite la nueva contraseña."), EqualTo("password_nueva", "Las contraseñas no coinciden.")],
    )
    enviar = SubmitField("Cambiar contraseña")


# ---------------------------------------------------------------------------
# Administración de usuarios
# ---------------------------------------------------------------------------


class UsuarioForm(FlaskForm):
    """Edición de un usuario existente: la contraseña es opcional."""

    nombre = StringField("Nombre completo", validators=[DataRequired("El nombre es obligatorio."), Length(max=120)])
    email = StringField("Correo electrónico", validators=[DataRequired("El correo es obligatorio."), CORREO_VALIDO, Length(max=120)])
    telefono = StringField("Teléfono", validators=[Optional(), Length(max=20)])
    tarjeta_profesional = StringField("Tarjeta profesional", validators=[Optional(), Length(max=50)])
    titulo_profesional = StringField("Título profesional (ej. Médica veterinaria)", validators=[Optional(), Length(max=150)])
    especialidad = StringField("Especialidad / Diplomado", validators=[Optional(), Length(max=150)])
    rol = SelectField("Rol", choices=list(ROLES.items()), validators=[DataRequired()])
    activo = BooleanField("Usuario activo", default=True)
    password = PasswordField(
        "Nueva contraseña",
        validators=[Optional(), Length(min=LONGITUD_MINIMA_PASSWORD, message=f"Mínimo {LONGITUD_MINIMA_PASSWORD} caracteres.")],
    )
    password_confirmacion = PasswordField(
        "Confirmar contraseña", validators=[EqualTo("password", "Las contraseñas no coinciden.")]
    )
    enviar = SubmitField("Guardar")


class UsuarioCrearForm(UsuarioForm):
    """Creación: la contraseña es obligatoria."""

    password = PasswordField(
        "Contraseña",
        validators=[
            DataRequired("Define una contraseña."),
            Length(min=LONGITUD_MINIMA_PASSWORD, message=f"Mínimo {LONGITUD_MINIMA_PASSWORD} caracteres."),
        ],
    )


class PerfilMedicoForm(FlaskForm):
    """Formulario especializado para la configuración del Médico Veterinario Principal y su firma."""

    nombre = StringField(
        "Nombre de la doctora / profesional",
        validators=[DataRequired("El nombre es obligatorio."), Length(max=120)],
        default="Dra. Daniela Pulido",
    )
    titulo_profesional = StringField(
        "Título profesional",
        validators=[DataRequired("El título profesional es obligatorio."), Length(max=150)],
        default="Médica veterinaria",
    )
    tarjeta_profesional = StringField(
        "Tarjeta Profesional (T.P.)",
        validators=[DataRequired("La tarjeta profesional es obligatoria."), Length(max=50)],
        default="53214",
    )
    especialidad = StringField(
        "Especialidad / Diplomado",
        validators=[Optional(), Length(max=150)],
        default="Dpl. Dermatología de pequeñas especies",
    )
    telefono = StringField("Teléfono / WhatsApp", validators=[Optional(), Length(max=20)])
    email = StringField("Correo electrónico", validators=[Optional(), CORREO_VALIDO, Length(max=120)])
    firma_archivo = FileField("Subir imagen de firma (PNG transparente, JPG o WEBP)", validators=[Optional()])
    firma_canvas = HiddenField("Trazo de firma canvas")
    enviar = SubmitField("Guardar información y firma")



# ---------------------------------------------------------------------------
# Configuración del sistema (formulario dinámico según tipo de cada clave)
# ---------------------------------------------------------------------------


def _campo_para(item):
    if item.tipo == "bool":
        return BooleanField(item.descripcion, default=bool(item.valor_tipado))
    if item.tipo == "int":
        return IntegerField(item.descripcion, default=item.valor_tipado, validators=[Optional()])
    if item.tipo == "decimal":
        return DecimalField(item.descripcion, default=item.valor_tipado, places=2, validators=[Optional()])
    return StringField(item.descripcion, default=item.valor_tipado or "", validators=[Optional(), Length(max=255)])


def construir_configuracion_form(items):
    """Crea una clase de formulario con un campo por clave de configuración."""

    class ConfiguracionForm(FlaskForm):
        enviar = SubmitField("Guardar cambios")

        def validate_clinica_whatsapp(self, campo):
            valor = (campo.data or "").strip()
            if valor and not valor.isdigit():
                raise ValidationError("Escribe solo dígitos, por ejemplo 573105551234.")

    for item in items:
        setattr(ConfiguracionForm, item.clave, _campo_para(item))
    return ConfiguracionForm()


def valor_de_campo(campo, tipo):
    """Convierte el dato del campo WTForms al valor que se guardará."""
    if tipo == "bool":
        return bool(campo.data)
    if tipo == "int":
        return int(campo.data or 0)
    if tipo == "decimal":
        return Decimal(str(campo.data)) if campo.data is not None else Decimal("0")
    return (campo.data or "").strip()


# ---------------------------------------------------------------------------
# Tutores
# ---------------------------------------------------------------------------


class TutorForm(FlaskForm):
    tipo_documento = SelectField(
        "Tipo de documento",
        choices=[("", "Sin documento")] + list(TIPOS_DOCUMENTO.items()),
        validators=[Optional()],
    )
    numero_documento = StringField("Número de documento", validators=[Optional(), Length(max=30)])
    nombre_completo = StringField("Nombre completo", validators=[DataRequired("El nombre es obligatorio."), Length(max=150)])
    telefono = StringField("Teléfono", validators=[Optional(), Length(max=20)])
    whatsapp = StringField("WhatsApp", validators=[Optional(), Length(max=20)])
    email = StringField("Correo electrónico", validators=[Optional(), CORREO_VALIDO, Length(max=120)])
    direccion = StringField("Dirección", validators=[Optional(), Length(max=200)])
    barrio = StringField("Barrio", validators=[Optional(), Length(max=100)])
    notas = TextAreaField("Notas", validators=[Optional(), Length(max=2000)])
    acepta_recordatorios = BooleanField("Acepta recordatorios por WhatsApp", default=True)
    enviar = SubmitField("Guardar")

    def validate_numero_documento(self, campo):
        if campo.data and not self.tipo_documento.data:
            raise ValidationError("Elige el tipo de documento.")
        if campo.data and not campo.data.replace(".", "").replace("-", "").strip().isalnum():
            raise ValidationError("El número de documento solo admite letras, números, puntos y guiones.")

    def validate_whatsapp(self, campo):
        if campo.data and len(solo_digitos(campo.data)) < 10:
            raise ValidationError("Escribe un número de WhatsApp válido (10 dígitos, por ejemplo 3105551234).")


# ---------------------------------------------------------------------------
# Mascotas
# ---------------------------------------------------------------------------


class MascotaForm(FlaskForm):
    tutor_id = HiddenField(validators=[DataRequired("Selecciona el tutor de la mascota.")])
    nombre = StringField("Nombre", validators=[DataRequired("El nombre es obligatorio."), Length(max=80)])
    especie = SelectField("Especie", choices=list(ESPECIES.items()), validators=[DataRequired()])
    # Las opciones de raza dependen de la especie y se cargan en la vista.
    raza_id = SelectField("Raza", coerce=int, validate_choice=False, validators=[Optional()])
    sexo = SelectField("Sexo", choices=list(SEXOS.items()), default="desconocido")
    conoce_fecha = BooleanField("Conozco la fecha exacta de nacimiento", default=True)
    fecha_nacimiento = DateField("Fecha de nacimiento", validators=[Optional()])
    edad_anios = IntegerField("Años", validators=[Optional(), NumberRange(min=0, max=60)])
    edad_meses = IntegerField("Meses", validators=[Optional(), NumberRange(min=0, max=11)])
    tamano = SelectField("Tamaño", choices=[("", "Sin definir")] + list(TAMANOS.items()), validators=[Optional()])
    color = StringField("Color", validators=[Optional(), Length(max=60)])
    senas_particulares = TextAreaField("Señas particulares", validators=[Optional(), Length(max=2000)])
    microchip = StringField("Microchip", validators=[Optional(), Length(max=30)])
    esterilizado = BooleanField("Esterilizado/a")
    alergias = TextAreaField("Alergias", validators=[Optional(), Length(max=2000)])
    condiciones_preexistentes = TextAreaField("Condiciones preexistentes", validators=[Optional(), Length(max=4000)])
    alimentacion = StringField("Alimentación / Dieta habitual", validators=[Optional(), Length(max=255)])
    foto = FileField("Foto", validators=[Optional()])
    enviar = SubmitField("Guardar")

    def validate_fecha_nacimiento(self, campo):
        if campo.data and campo.data > hoy_bogota():
            raise ValidationError("La fecha de nacimiento no puede ser futura.")

    def validate_edad_meses(self, campo):
        if self.conoce_fecha.data:
            return
        anios = self.edad_anios.data or 0
        meses = campo.data or 0
        if anios == 0 and meses == 0 and (self.edad_anios.data is None and campo.data is None):
            return  # edad desconocida: se permite
        if anios == 0 and meses == 0:
            raise ValidationError("Indica al menos un mes de edad, o deja ambos campos vacíos si no se sabe.")

    def fecha_nacimiento_resuelta(self):
        """Devuelve ``(fecha, estimada)`` según lo diligenciado."""
        if self.conoce_fecha.data:
            return self.fecha_nacimiento.data, False
        if self.edad_anios.data is None and self.edad_meses.data is None:
            return None, False
        return fecha_desde_edad(self.edad_anios.data or 0, self.edad_meses.data or 0), True


class RegistroPesoForm(FlaskForm):
    peso_kg = DecimalField(
        "Peso (kg)",
        places=2,
        validators=[DataRequired("Escribe el peso."), NumberRange(min=Decimal("0.01"), max=Decimal("500"), message="Peso fuera de rango.")],
    )
    fecha = DateField("Fecha", validators=[Optional()])
    enviar = SubmitField("Registrar peso")

    def validate_fecha(self, campo):
        if campo.data and campo.data > hoy_bogota():
            raise ValidationError("La fecha no puede ser futura.")


class FotoForm(FlaskForm):
    foto = FileField("Foto", validators=[DataRequired("Selecciona una foto.")])
    enviar = SubmitField("Subir foto")


class FallecimientoForm(FlaskForm):
    fecha_fallecimiento = DateField("Fecha de fallecimiento", validators=[DataRequired("Indica la fecha.")])
    enviar = SubmitField("Registrar fallecimiento")

    def validate_fecha_fallecimiento(self, campo):
        if campo.data > hoy_bogota():
            raise ValidationError("La fecha no puede ser futura.")


class SoloCsrfForm(FlaskForm):
    """Formulario vacío para acciones POST que solo necesitan el token CSRF."""


# ---------------------------------------------------------------------------
# Catálogo de razas
# ---------------------------------------------------------------------------


class RazaForm(FlaskForm):
    especie = SelectField("Especie", choices=list(ESPECIES.items()), validators=[DataRequired()])
    nombre = StringField("Nombre de la raza", validators=[DataRequired("Escribe el nombre."), Length(max=80)])
    activo = BooleanField("Activa", default=True)
    enviar = SubmitField("Guardar")


# ---------------------------------------------------------------------------
# Inventario
# ---------------------------------------------------------------------------

class ProveedorForm(FlaskForm):
    nit = StringField("NIT / Documento", validators=[Optional(), Length(max=30)])
    nombre = StringField("Nombre o Razón Social", validators=[DataRequired("El nombre del proveedor es obligatorio."), Length(max=120)])
    contacto = StringField("Persona de contacto", validators=[Optional(), Length(max=100)])
    telefono = StringField("Teléfono", validators=[Optional(), Length(max=20)])
    email = StringField("Correo electrónico", validators=[Optional(), CORREO_VALIDO, Length(max=120)])
    direccion = StringField("Dirección", validators=[Optional(), Length(max=200)])
    ciudad = StringField("Ciudad", validators=[Optional(), Length(max=80)])
    notas = TextAreaField("Notas adicionales", validators=[Optional(), Length(max=2000)])
    activo = BooleanField("Proveedor activo", default=True)
    enviar = SubmitField("Guardar proveedor")


class ProductoForm(FlaskForm):
    sku = StringField("SKU / Código interno", validators=[DataRequired("El SKU es obligatorio."), Length(max=40)])
    codigo_barras = StringField("Código de barras", validators=[Optional(), Length(max=50)])
    nombre = StringField("Nombre del producto / servicio", validators=[DataRequired("El nombre es obligatorio."), Length(max=150)])
    descripcion = TextAreaField("Descripción", validators=[Optional(), Length(max=2000)])
    categoria = SelectField("Categoría", choices=list(CATEGORIAS_PRODUCTO.items()), default="otro", validators=[DataRequired()])
    tipo = SelectField("Tipo", choices=[("producto", "Producto físico"), ("servicio", "Servicio")], default="producto", validators=[DataRequired()])
    unidad_medida = SelectField("Unidad de medida", choices=list(UNIDADES_MEDIDA.items()), default="unidad", validators=[DataRequired()])
    precio_costo = DecimalField("Precio de costo (COP)", places=2, validators=[Optional(), NumberRange(min=Decimal("0"))], default=Decimal("0.00"))
    precio_minimo = DecimalField("Precio mínimo (COP)", places=2, validators=[Optional(), NumberRange(min=Decimal("0"))], default=Decimal("0.00"))
    precio_sugerido = DecimalField("Precio sugerido / Venta (COP)", places=2, validators=[Optional(), NumberRange(min=Decimal("0"))], default=Decimal("0.00"))
    stock_minimo = DecimalField("Stock mínimo de alerta", places=2, validators=[Optional(), NumberRange(min=Decimal("0"))], default=Decimal("0.00"))
    proveedor_id = SelectField("Proveedor principal", coerce=int, validate_choice=False, validators=[Optional()])
    controla_lote = BooleanField("Controla lotes y vencimientos (ej. medicamentos / vacunas)")
    requiere_receta = BooleanField("Requiere receta médica para la venta")
    imagen = FileField("Imagen del producto", validators=[Optional()])
    activo = BooleanField("Producto activo", default=True)
    enviar = SubmitField("Guardar producto")

    def validate_precio_minimo(self, campo):
        if campo.data is not None and self.precio_sugerido.data is not None:
            if campo.data > self.precio_sugerido.data:
                raise ValidationError("El precio mínimo no puede ser superior al precio sugerido.")


class VarianteProductoForm(FlaskForm):
    nombre_variante = StringField("Presentación / Nombre de variante", validators=[DataRequired("Escribe el nombre de la variante (ej. 2 kg, Talla M)."), Length(max=100)])
    sku = StringField("SKU propio", validators=[Optional(), Length(max=40)])
    codigo_barras = StringField("Código de barras propio", validators=[Optional(), Length(max=50)])
    precio_costo = DecimalField("Precio de costo (COP)", places=2, validators=[Optional(), NumberRange(min=Decimal("0"))], default=Decimal("0.00"))
    precio_minimo = DecimalField("Precio mínimo (COP)", places=2, validators=[Optional(), NumberRange(min=Decimal("0"))], default=Decimal("0.00"))
    precio_sugerido = DecimalField("Precio sugerido / Venta (COP)", places=2, validators=[Optional(), NumberRange(min=Decimal("0"))], default=Decimal("0.00"))
    stock_minimo = DecimalField("Stock mínimo de alerta", places=2, validators=[Optional(), NumberRange(min=Decimal("0"))], default=Decimal("0.00"))
    activo = BooleanField("Variante activa", default=True)
    enviar = SubmitField("Guardar variante")


class LoteForm(FlaskForm):
    numero_lote = StringField("Número de lote", validators=[DataRequired("El número de lote es obligatorio."), Length(max=60)])
    variante_id = SelectField("Variante (opcional)", coerce=int, validate_choice=False, validators=[Optional()])
    fecha_vencimiento = DateField("Fecha de vencimiento", validators=[DataRequired("La fecha de vencimiento es obligatoria.")])
    cantidad = DecimalField("Cantidad inicial a ingresar", places=2, validators=[DataRequired("Ingresa la cantidad."), NumberRange(min=Decimal("0.01"))])
    proveedor_id = SelectField("Proveedor (opcional)", coerce=int, validate_choice=False, validators=[Optional()])
    enviar = SubmitField("Ingresar lote")

    def validate_fecha_vencimiento(self, campo):
        if campo.data and campo.data < hoy_bogota():
            raise ValidationError("No se puede registrar un lote ya vencido.")


class AjusteStockForm(FlaskForm):
    tipo_movimiento = SelectField(
        "Tipo de ajuste",
        choices=[
            ("entrada", "Entrada por compra"),
            ("salida", "Salida manual"),
            ("ajuste_positivo", "Ajuste positivo (+)"),
            ("ajuste_negativo", "Ajuste negativo (-)"),
        ],
        validators=[DataRequired()],
    )
    variante_id = SelectField("Variante (opcional)", coerce=int, validate_choice=False, validators=[Optional()])
    lote_id = SelectField("Lote afectado (opcional)", coerce=int, validate_choice=False, validators=[Optional()])
    cantidad = DecimalField("Cantidad", places=2, validators=[DataRequired("Ingresa la cantidad."), NumberRange(min=Decimal("0.01"))])
    motivo = TextAreaField("Motivo del ajuste", validators=[DataRequired("Explica el motivo del movimiento."), Length(max=1000)])
    enviar = SubmitField("Registrar ajuste")


class ImportarExcelForm(FlaskForm):
    archivo = FileField("Archivo Excel (.xlsx)", validators=[DataRequired("Selecciona el archivo Excel.")])
    enviar = SubmitField("Cargar e importar")


# ---------------------------------------------------------------------------
# Fase 4: Punto de Venta (POS) y Caja
# ---------------------------------------------------------------------------


class AperturaCajaForm(FlaskForm):
    monto_apertura = DecimalField(
        "Monto de apertura en caja (Efectivo base COP)",
        places=2,
        validators=[InputRequired("Ingresa el monto inicial."), NumberRange(min=Decimal("0"))],
        default=Decimal("0.00"),
    )
    notas = TextAreaField("Notas de apertura (opcional)", validators=[Optional(), Length(max=500)])
    enviar = SubmitField("Abrir turno de caja")


class CierreCajaForm(FlaskForm):
    monto_efectivo = DecimalField("Efectivo en caja (contado)", places=2, validators=[InputRequired("Ingresa el efectivo."), NumberRange(min=Decimal("0"))], default=Decimal("0.00"))
    monto_nequi = DecimalField("Total Nequi (verificado)", places=2, validators=[Optional(), NumberRange(min=Decimal("0"))], default=Decimal("0.00"))
    monto_daviplata = DecimalField("Total Daviplata (verificado)", places=2, validators=[Optional(), NumberRange(min=Decimal("0"))], default=Decimal("0.00"))
    monto_tarjetas = DecimalField("Total Tarjetas (datáfono)", places=2, validators=[Optional(), NumberRange(min=Decimal("0"))], default=Decimal("0.00"))
    monto_transferencia = DecimalField("Total Transferencias (cuenta bancaria)", places=2, validators=[Optional(), NumberRange(min=Decimal("0"))], default=Decimal("0.00"))
    notas = TextAreaField("Notas u observaciones del cierre (opcional)", validators=[Optional(), Length(max=1000)])
    enviar = SubmitField("Cerrar turno y realizar arqueo")


class AnularVentaForm(FlaskForm):
    motivo = TextAreaField(
        "Motivo de anulación",
        validators=[DataRequired("El motivo de anulación es obligatorio."), Length(min=10, max=1000, message="Explica el motivo (mínimo 10 caracteres).")],
    )
    enviar = SubmitField("Confirmar anulación")


class AprobarPrecioForm(FlaskForm):
    precio_aprobado = DecimalField(
        "Precio a autorizar (COP)",
        places=2,
        validators=[DataRequired("Indica el precio a autorizar."), NumberRange(min=Decimal("0"))],
    )
    enviar = SubmitField("Aprobar")


class RechazarPrecioForm(FlaskForm):
    motivo_rechazo = TextAreaField(
        "Motivo del rechazo",
        validators=[DataRequired("Explica brevemente por qué se rechaza."), Length(max=500)],
    )
    enviar = SubmitField("Rechazar")


# ---------------------------------------------------------------------------
# Fase 5: Spa & Peluquería de Mascotas (Grooming)
# ---------------------------------------------------------------------------


class ServicioSpaForm(FlaskForm):
    nombre = StringField("Nombre del servicio (ej. Baño y Corte Comercial)", validators=[DataRequired("El nombre del servicio es obligatorio."), Length(max=120)])
    descripcion = TextAreaField("Descripción del servicio", validators=[Optional(), Length(max=1000)])
    duracion_minutos = IntegerField("Duración estimada (minutos)", validators=[DataRequired(), NumberRange(min=15, max=480)], default=60)
    precio_sugerido = DecimalField("Precio sugerido (COP)", places=2, validators=[DataRequired("Ingresa el precio."), NumberRange(min=Decimal("0"))], default=Decimal("0.00"))
    especie = SelectField("Especie recomendada (opcional)", choices=[("", "Todas las especies")] + list(ESPECIES.items()), validators=[Optional()])
    tamano_mascota = SelectField("Tamaño de mascota recomendado (opcional)", choices=[("", "Todos los tamaños")] + list(TAMANOS.items()), validators=[Optional()])
    activo = BooleanField("Servicio activo", default=True)
    enviar = SubmitField("Guardar servicio")


class CitaSpaForm(FlaskForm):
    tutor_id = SelectField("Tutor / Cliente", coerce=int, validators=[DataRequired("Selecciona el tutor.")])
    mascota_id = SelectField("Mascota", coerce=int, validators=[DataRequired("Selecciona la mascota.")])
    servicio_spa_id = SelectField("Servicio de Spa / Estética", coerce=int, validators=[DataRequired("Selecciona el servicio.")])
    groomer_id = SelectField("Groomer / Responsable (opcional)", coerce=int, validate_choice=False, validators=[Optional()])
    fecha = DateField("Fecha del servicio", validators=[DataRequired("Selecciona la fecha.")])
    hora = TimeField("Hora del servicio", validators=[DataRequired("Selecciona la hora.")])
    duracion_minutos = IntegerField("Duración en minutos", validators=[DataRequired(), NumberRange(min=15, max=480)], default=60)
    notas_ingreso = TextAreaField("Notas de ingreso / Estado inicial (opcional)", validators=[Optional(), Length(max=1000)])
    foto_ingreso = FileField("Foto de ingreso / Antes (opcional)", validators=[Optional()])
    enviar = SubmitField("Agendar cita de grooming")


class CambioEstadoSpaForm(FlaskForm):
    estado = SelectField(
        "Nuevo Estado",
        choices=[
            ("programada", "Programada"),
            ("en_proceso", "En proceso de grooming"),
            ("listo_recogida", "¡Listo para recogida!"),
            ("entregado", "Entregado a tutor"),
            ("cancelada", "Cancelada"),
        ],
        validators=[DataRequired()],
    )
    notas_salida = TextAreaField("Observaciones de salida / entrega (opcional)", validators=[Optional(), Length(max=1000)])
    foto_ingreso = FileField("Foto de ingreso / Antes (opcional)", validators=[Optional()])
    foto_salida = FileField("Foto de salida / Después (opcional)", validators=[Optional()])
    enviar = SubmitField("Actualizar estado")


class FotoSpaModalForm(FlaskForm):
    """Formulario rápido para subir o tomar foto de ingreso o salida desde el detalle de la cita."""

    tipo = HiddenField("Tipo de foto", validators=[DataRequired()])
    foto = FileField("Foto", validators=[DataRequired("Selecciona o toma una foto.")])
    enviar = SubmitField("Guardar foto")


class VincularVentaSpaForm(FlaskForm):
    """Asocia una venta ya cobrada en el POS a la cita de spa (requisito para entregar)."""

    numero_factura = StringField(
        "Número de factura",
        validators=[DataRequired("Escribe el número de factura, por ejemplo VET-20260914-0007.")],
    )
    enviar = SubmitField("Vincular pago")


# ---------------------------------------------------------------------------
# Fase 6: Historias Clínicas, Vacunación y Desparasitación
# ---------------------------------------------------------------------------


class ConsultaMedicaForm(FlaskForm):
    motivo_consulta = StringField("Motivo de consulta", validators=[DataRequired("El motivo de consulta es obligatorio."), Length(max=255)])
    anamnesis = TextAreaField("Anamnesis / Historia previa (Subjetivo - S)", validators=[Optional(), Length(max=2000)])

    # Constantes vitales / Examen físico
    peso_kg = DecimalField("Peso actual (kg)", places=2, validators=[Optional(), NumberRange(min=Decimal("0.01"), max=Decimal("300.00"))])
    temperatura_c = DecimalField("Temperatura (°C)", places=1, validators=[Optional(), NumberRange(min=Decimal("30.0"), max=Decimal("45.0"))])
    frecuencia_cardiaca = IntegerField("FC (lpm)", validators=[Optional(), NumberRange(min=20, max=300)])
    frecuencia_respiratoria = IntegerField("FR (rpm)", validators=[Optional(), NumberRange(min=5, max=150)])
    tllc_segundos = IntegerField("TLLC (segundos)", validators=[Optional(), NumberRange(min=1, max=10)])
    mucosas = SelectField("Mucosas", choices=[("", "-- Seleccionar --"), ("rosadas", "Rosadas (Normal)"), ("palidas", "Pálidas"), ("ictericas", "Ictéricas"), ("cianoticas", "Cianóticas"), ("congestivas", "Congestivas")], validators=[Optional()])
    condicion_corporal = SelectField("Condición Corporal", choices=[("", "-- Seleccionar --"), ("1/5", "1/5 - Muy delgado"), ("2/5", "2/5 - Delgado"), ("3/5", "3/5 - Ideal"), ("4/5", "4/5 - Sobrepeso"), ("5/5", "5/5 - Obeso")], validators=[Optional()])
    examen_sistemas = TextAreaField("Examen por sistemas (Objetivo - O)", validators=[Optional(), Length(max=2000)])

    diagnostico = TextAreaField("Diagnóstico Presuntivo (Avalúo - A)", validators=[DataRequired("El diagnóstico presuntivo es obligatorio."), Length(max=2000)])
    plan_tratamiento = TextAreaField("Plan de Tratamiento / Indicaciones (Plan - P)", validators=[DataRequired("El plan de tratamiento es obligatorio."), Length(max=2000)])
    receta_medica = TextAreaField("Fórmula Médica / Prescripción", validators=[Optional(), Length(max=2000)])
    observaciones = TextAreaField("Observaciones adicionales", validators=[Optional(), Length(max=1000)])

    enviar = SubmitField("Guardar Consulta Médica")


class VacunaMascotaForm(FlaskForm):
    nombre_vacuna = StringField("Nombre de la vacuna / Antígeno", validators=[DataRequired("El nombre de la vacuna es obligatorio."), Length(max=120)])
    lote = StringField("Número de lote (opcional)", validators=[Optional(), Length(max=60)])
    laboratorio = StringField("Laboratorio / Marca", validators=[Optional(), Length(max=100)])
    dosis = StringField("Dosis aplicada", default="1.0 mL", validators=[DataRequired(), Length(max=50)])
    fecha_aplicacion = DateField("Fecha de aplicación", validators=[DataRequired("Ingresa la fecha de aplicación.")])
    fecha_proxima = DateField("Próxima revacunación", validators=[DataRequired("Ingresa la fecha proyectada de revacunación.")])
    observaciones = TextAreaField("Observaciones (opcional)", validators=[Optional(), Length(max=1000)])

    enviar = SubmitField("Registrar Vacuna")


class DesparasitacionMascotaForm(FlaskForm):
    producto = StringField("Producto desparasitante", validators=[DataRequired("El nombre del producto es obligatorio."), Length(max=120)])
    tipo = SelectField("Tipo de desparasitación", choices=[("interna", "Interna (Endoparásitos)"), ("externa", "Externa (Ectoparásitos)"), ("mixta", "Mixta (Interna + Externa)")], default="interna", validators=[DataRequired()])
    dosis = StringField("Dosis administrada", validators=[Optional(), Length(max=50)])
    peso_kg = DecimalField("Peso de la mascota (kg)", places=2, validators=[Optional(), NumberRange(min=Decimal("0.01"), max=Decimal("300.00"))])
    fecha_aplicacion = DateField("Fecha de aplicación", validators=[DataRequired("Ingresa la fecha de aplicación.")])
    fecha_proxima = DateField("Próxima dosis (opcional)", validators=[Optional()])
    observaciones = TextAreaField("Observaciones (opcional)", validators=[Optional(), Length(max=1000)])

    enviar = SubmitField("Registrar Desparasitación")


# ---------------------------------------------------------------------------
# Fase 8: Configuración del Sistema y Parámetros
# ---------------------------------------------------------------------------


class ConfiguracionClinicaForm(FlaskForm):
    clinica_nombre = StringField("Nombre de la Clínica", validators=[DataRequired("El nombre es obligatorio."), Length(max=150)])
    clinica_subtitulo = StringField("Subtítulo / Eslogan", validators=[Optional(), Length(max=200)])
    clinica_nit = StringField("NIT / RUTA / Registro Fiscal", validators=[Optional(), Length(max=50)])
    clinica_direccion = StringField("Dirección", validators=[Optional(), Length(max=200)])
    clinica_ciudad = StringField("Ciudad", validators=[Optional(), Length(max=100)])
    clinica_telefono = StringField("Teléfono Fijo / Móvil", validators=[Optional(), Length(max=50)])
    clinica_whatsapp = StringField("WhatsApp de Atención", validators=[Optional(), Length(max=20)])
    clinica_email = StringField("Correo Electrónico de Contacto", validators=[Optional(), Email("Ingresa un correo electrónico válido."), Length(max=120)])

    enviar = SubmitField("Guardar Configuración")





# ---------------------------------------------------------------------------
# Agenda médica general
# ---------------------------------------------------------------------------


class CitaForm(FlaskForm):
    tutor_id = HiddenField(validators=[DataRequired("Selecciona el tutor.")])
    mascota_id = HiddenField(validators=[DataRequired("Selecciona la mascota.")])
    tipo = SelectField("Tipo de cita", choices=list(TIPOS_CITA.items()), validators=[DataRequired()])
    profesional_id = SelectField("Profesional (opcional)", coerce=int, validate_choice=False, validators=[Optional()])
    fecha = DateField("Fecha", validators=[DataRequired("Selecciona la fecha.")])
    hora = TimeField("Hora", validators=[DataRequired("Selecciona la hora.")])
    duracion_minutos = IntegerField("Duración (minutos)", validators=[DataRequired(), NumberRange(min=10, max=480)], default=30)
    motivo = StringField("Motivo", validators=[Optional(), Length(max=255)])
    notas = TextAreaField("Notas (opcional)", validators=[Optional(), Length(max=1000)])
    enviar = SubmitField("Agendar cita")

    def validate_fecha(self, field):
        if field.data and field.data < hoy_bogota():
            raise ValidationError("No se pueden agendar citas en fechas pasadas.")


class CambiarEstadoCitaForm(FlaskForm):
    estado = SelectField("Nuevo estado", choices=list(ESTADOS_CITA.items()), validators=[DataRequired()])
    enviar = SubmitField("Actualizar estado")


# ---------------------------------------------------------------------------
# Hospitalización
# ---------------------------------------------------------------------------


class HospitalizacionForm(FlaskForm):
    mascota_id = HiddenField(validators=[DataRequired("Selecciona la mascota.")])
    motivo = TextAreaField("Motivo de ingreso", validators=[DataRequired("El motivo es obligatorio."), Length(max=2000)])
    diagnostico = TextAreaField("Diagnóstico (opcional)", validators=[Optional(), Length(max=2000)])
    jaula = StringField("Jaula / Kennel", validators=[Optional(), Length(max=30)])
    costo_dia = DecimalField("Costo por día (COP)", places=2, validators=[Optional(), NumberRange(min=Decimal("0"))], default=Decimal("0.00"))
    enviar = SubmitField("Registrar ingreso")


class EvolucionHospitalariaForm(FlaskForm):
    constantes = TextAreaField("Constantes vitales", validators=[Optional(), Length(max=1000)])
    tratamiento_aplicado = TextAreaField("Tratamiento aplicado", validators=[Optional(), Length(max=1000)])
    alimentacion = StringField("Alimentación", validators=[Optional(), Length(max=120)])
    eliminaciones = StringField("Eliminaciones", validators=[Optional(), Length(max=120)])
    observaciones = TextAreaField("Observaciones", validators=[Optional(), Length(max=1000)])
    enviar = SubmitField("Registrar evolución")


class AltaHospitalizacionForm(FlaskForm):
    estado = SelectField(
        "Estado de egreso",
        choices=[("alta", "De alta"), ("fallecido", "Fallecido"), ("remitido", "Remitido")],
        validators=[DataRequired()],
    )
    enviar = SubmitField("Registrar egreso")


# ---------------------------------------------------------------------------
# Cirugías
# ---------------------------------------------------------------------------


class CirugiaForm(FlaskForm):
    mascota_id = HiddenField(validators=[DataRequired("Selecciona la mascota.")])
    tipo_procedimiento = StringField("Tipo de procedimiento", validators=[DataRequired("Indica el procedimiento."), Length(max=150)])
    fecha = DateField("Fecha", validators=[DataRequired("Selecciona la fecha.")])
    consentimiento_firmado = BooleanField("Consentimiento informado firmado")
    archivo_consentimiento = FileField("Archivo del consentimiento (opcional)", validators=[Optional()])
    notas_prequirurgicas = TextAreaField("Notas prequirúrgicas", validators=[Optional(), Length(max=2000)])
    protocolo_anestesico = TextAreaField("Protocolo anestésico", validators=[Optional(), Length(max=2000)])
    enviar = SubmitField("Registrar cirugía")


class NotasPostquirurgicasForm(FlaskForm):
    notas_postquirurgicas = TextAreaField("Notas postquirúrgicas", validators=[DataRequired("Escribe las notas."), Length(max=2000)])
    enviar = SubmitField("Guardar notas")


# ---------------------------------------------------------------------------
# Exámenes de laboratorio
# ---------------------------------------------------------------------------


class ExamenLaboratorioForm(FlaskForm):
    mascota_id = HiddenField(validators=[DataRequired("Selecciona la mascota.")])
    categoria = SelectField(
        "Categoría de ayuda diagnóstica",
        choices=list(CATEGORIAS_EXAMEN.items()),
        default="laboratorio",
        validators=[DataRequired("Selecciona una categoría.")],
    )
    tipo_examen = StringField("Nombre o tipo de examen / estudio", validators=[DataRequired("Indica el nombre del examen."), Length(max=150)])
    fecha_toma = DateField("Fecha de realización / toma", default=hoy_bogota, validators=[DataRequired("Selecciona la fecha.")])
    laboratorio_externo = StringField("Centro diagnóstico / Laboratorio externo (opcional)", validators=[Optional(), Length(max=150)])
    archivo_resultado = FileField("Adjuntar archivo / reporte (PDF, JPG, PNG, WEBP, DOCX, DICOM)", validators=[Optional()])
    interpretacion = TextAreaField("Comentarios / Hallazgos / Interpretación clínica", validators=[Optional(), Length(max=3000)])
    estado = SelectField("Estado del examen", choices=list(ESTADOS_EXAMEN.items()), default="con_resultado", validators=[DataRequired()])
    enviar = SubmitField("Guardar examen")


class ResultadoExamenForm(FlaskForm):
    categoria = SelectField("Categoría", choices=list(CATEGORIAS_EXAMEN.items()), validators=[Optional()])
    tipo_examen = StringField("Nombre del examen", validators=[Optional(), Length(max=150)])
    laboratorio_externo = StringField("Centro diagnóstico / Laboratorio externo", validators=[Optional(), Length(max=150)])
    archivo_resultado = FileField("Adjuntar o reemplazar archivo (PDF, JPG, PNG, WEBP)", validators=[Optional()])
    interpretacion = TextAreaField("Comentarios / Hallazgos / Interpretación clínica", validators=[Optional(), Length(max=3000)])
    estado = SelectField("Estado", choices=list(ESTADOS_EXAMEN.items()), validators=[DataRequired()])
    enviar = SubmitField("Guardar cambios y resultado")


# ---------------------------------------------------------------------------
# Enmienda de historia clínica
# ---------------------------------------------------------------------------


class EnmiendaConsultaForm(FlaskForm):
    texto = TextAreaField(
        "Nota de enmienda",
        validators=[DataRequired("Explica la corrección."), Length(min=5, max=2000)],
    )
    enviar = SubmitField("Agregar enmienda")


# ---------------------------------------------------------------------------
# Gastos
# ---------------------------------------------------------------------------


class GastoForm(FlaskForm):
    tipo_gasto = SelectField("Tipo", choices=list(TIPOS_GASTO.items()), validators=[DataRequired()])
    categoria = SelectField("Categoría", choices=list(CATEGORIAS_GASTO.items()), validators=[DataRequired()])
    descripcion = StringField("Descripción", validators=[DataRequired("Describe el gasto."), Length(max=255)])
    monto = DecimalField("Monto (COP)", places=2, validators=[DataRequired("Ingresa el monto."), NumberRange(min=Decimal("0.01"))])
    fecha_gasto = DateField("Fecha", validators=[DataRequired("Selecciona la fecha.")])
    comprobante = FileField("Comprobante (opcional)", validators=[Optional()])
    enviar = SubmitField("Registrar gasto")


# ---------------------------------------------------------------------------
# Compras a crédito a proveedores
# ---------------------------------------------------------------------------


class FacturaProveedorForm(FlaskForm):
    proveedor_id = SelectField("Proveedor", coerce=int, validators=[DataRequired("Selecciona el proveedor.")])
    numero_factura = StringField("Número de factura", validators=[DataRequired("Indica el número."), Length(max=60)])
    fecha_factura = DateField("Fecha de factura", validators=[DataRequired()])
    fecha_vencimiento = DateField("Fecha de vencimiento (opcional)", validators=[Optional()])
    monto_total = DecimalField("Monto total (COP)", places=2, validators=[DataRequired("Ingresa el monto."), NumberRange(min=Decimal("0.01"))])
    notas = TextAreaField("Notas (opcional)", validators=[Optional(), Length(max=1000)])
    archivo = FileField("Archivo de la factura (opcional)", validators=[Optional()])
    enviar = SubmitField("Registrar factura")


class PagoProveedorForm(FlaskForm):
    monto = DecimalField("Monto abonado (COP)", places=2, validators=[DataRequired("Ingresa el monto."), NumberRange(min=Decimal("0.01"))])
    metodo_pago = SelectField(
        "Método de pago",
        choices=[("efectivo", "Efectivo"), ("transferencia", "Transferencia"), ("nequi", "Nequi"), ("daviplata", "Daviplata"), ("tarjeta", "Tarjeta")],
        validators=[DataRequired()],
    )
    notas = TextAreaField("Notas (opcional)", validators=[Optional(), Length(max=500)])
    enviar = SubmitField("Registrar abono")


# ---------------------------------------------------------------------------
# Cartera de tutores con crédito
# ---------------------------------------------------------------------------


class CuentaTutorForm(FlaskForm):
    descripcion = StringField("Descripción", validators=[DataRequired("Describe el cargo."), Length(max=255)])
    monto_total = DecimalField("Monto total (COP)", places=2, validators=[DataRequired("Ingresa el monto."), NumberRange(min=Decimal("0.01"))])
    fecha_factura = DateField("Fecha", validators=[DataRequired()])
    fecha_vencimiento = DateField("Fecha de vencimiento (opcional)", validators=[Optional()])
    enviar = SubmitField("Registrar cargo a crédito")


class AbonoCuentaTutorForm(FlaskForm):
    monto = DecimalField("Monto abonado (COP)", places=2, validators=[DataRequired("Ingresa el monto."), NumberRange(min=Decimal("0.01"))])
    metodo_pago = SelectField(
        "Método de pago",
        choices=[("efectivo", "Efectivo"), ("nequi", "Nequi"), ("daviplata", "Daviplata"), ("transferencia", "Transferencia"), ("tarjeta", "Tarjeta")],
        validators=[DataRequired()],
    )
    notas = TextAreaField("Notas (opcional)", validators=[Optional(), Length(max=500)])
    enviar = SubmitField("Registrar abono")


# ---------------------------------------------------------------------------
# Remisiones Clínicas Internas
# ---------------------------------------------------------------------------


class RemisionInternaForm(FlaskForm):
    # 1. Datos de Remisión
    especialidad_destino = StringField(
        "Especialidad o Servicio Requerido",
        validators=[DataRequired("Indica la especialidad o servicio de destino."), Length(max=150)],
    )
    centro_medico_destino = StringField(
        "Centro Médico / Especialista Receptor (Opcional)",
        validators=[Optional(), Length(max=180)],
    )
    motivo_remision = TextAreaField(
        "Motivo Principal de la Remisión",
        validators=[DataRequired("Describe el motivo clínico de la remisión.")],
    )
    observaciones_clinicas = TextAreaField(
        "Hallazgos Clínicos, Sospecha y Observaciones (Opcional)",
        validators=[Optional()],
    )

    # 2. Alimentación y Nutrición
    dieta_marca_tipo = StringField(
        "Alimentación y Dieta Actual",
        validators=[Optional(), Length(max=255)],
    )

    # 3. Antecedentes
    antecedentes_cirugias = TextAreaField(
        "Cirugías y Procedimientos Previos",
        validators=[Optional()],
    )
    antecedentes_enfermedades = TextAreaField(
        "Enfermedades Diagnosticadas y Preexistencias",
        validators=[Optional()],
    )

    # 4. Estatus Preventivo
    desparasitacion_interna_producto = StringField(
        "Desparasitación Interna (Producto)",
        validators=[Optional(), Length(max=120)],
    )
    desparasitacion_interna_fecha = DateField(
        "Fecha Desparasitación Interna",
        validators=[Optional()],
    )
    desparasitacion_externa_producto = StringField(
        "Desparasitación Externa (Antipulgas/Garrapatas)",
        validators=[Optional(), Length(max=120)],
    )
    desparasitacion_externa_fecha = DateField(
        "Fecha Desparasitación Externa",
        validators=[Optional()],
    )
    vacunacion_al_dia = BooleanField(
        "¿Plan de vacunación al día?",
        default=True,
    )
    vacunacion_ultima_fecha = DateField(
        "Fecha Última Vacunación",
        validators=[Optional()],
    )

    enviar = SubmitField("Guardar Remisión Clínica")

