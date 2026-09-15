"""Modelos SQLAlchemy de VetCare.

Convenciones:
- Tablas en plural y snake_case.
- Dinero en ``Numeric(12, 2)`` (Decimal), nunca float.
- Fechas con zona (``DateTime(timezone=True)``) generadas con ``obtener_hora_bogota``.
- Roles y estados como ``String`` validados en Python, no como ENUM nativo de
  PostgreSQL (cada valor nuevo exigiría un ``ALTER TYPE`` en migración).
"""

from datetime import timedelta
from decimal import Decimal, InvalidOperation

from flask import g, has_app_context, has_request_context, url_for
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import MetaData, func, select, text
from sqlalchemy.orm import validates
from werkzeug.security import check_password_hash, generate_password_hash

from utils import edad_texto, enlace_whatsapp, hoy_bogota, normalizar_texto, normalizar_whatsapp, obtener_hora_bogota

def _generar_url_segura(endpoint: str, **values) -> str:
    """Genera URL absoluta o relativa sin fallar si está fuera de contexto web."""
    try:
        if has_request_context():
            return url_for(endpoint, _external=True, **values)
        if has_app_context():
            try:
                return url_for(endpoint, _external=True, **values)
            except Exception:
                return url_for(endpoint, _external=False, **values)
    except Exception:
        pass
    if endpoint == "historias.consulta_documento_publico":
        return f"/historias/consulta/{values.get('id')}/documento"
    elif endpoint == "pos.venta_pdf":
        return f"/pos/venta/{values.get('id')}/pdf"
    elif endpoint in ("spa.cita_spa_pdf", "spa.cita_pdf"):
        return f"/spa/cita/{values.get('id')}/pdf"
    return "/"


# Nombres predecibles para índices y restricciones (facilita las migraciones).
CONVENCION_NOMBRES = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

db = SQLAlchemy(metadata=MetaData(naming_convention=CONVENCION_NOMBRES))


class BaseModel(db.Model):
    """Clase base abstracta para todos los modelos de VetCare.

    Proporciona soporte de inicialización con kwargs para analizadores
    estáticos (PyLance/Pyright).
    """

    __abstract__ = True

    def __init__(self, **kwargs):
        super().__init__(**kwargs)


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------

ROLES = {
    "admin": "Administrador",
    "veterinario": "Veterinario/a",
    "auxiliar": "Auxiliar",
    "groomer": "Groomer",
    "cajero": "Cajero/a",
    "recepcion": "Recepción",
}
ROLES_TODOS = tuple(ROLES.keys())


class Usuario(UserMixin, BaseModel):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    telefono = db.Column(db.String(20))
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    fecha_registro = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)
    ultimo_acceso = db.Column(db.DateTime(timezone=True))

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @validates("rol")
    def _validar_rol(self, _clave, valor):
        if valor not in ROLES:
            raise ValueError(f"Rol inválido: {valor!r}")
        return valor

    @validates("email")
    def _normalizar_email(self, _clave, valor):
        return (valor or "").strip().lower()

    # Flask-Login consulta ``is_active`` antes de permitir el inicio de sesión.
    @property
    def is_active(self):
        return bool(self.activo)

    def establecer_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def verificar_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password or "")

    def tiene_rol(self, *roles) -> bool:
        return self.rol in roles

    @property
    def es_admin(self) -> bool:
        return self.rol == "admin"

    @property
    def rol_etiqueta(self) -> str:
        return ROLES.get(self.rol, self.rol)

    def __repr__(self):
        return f"<Usuario {self.email} ({self.rol})>"


# ---------------------------------------------------------------------------
# Configuración del sistema (clave-valor tipado)
# ---------------------------------------------------------------------------

# Claves que existen desde la primera migración. ``models.py`` las usa como
# valor por defecto si la fila no existe; la migración inicial las siembra.
CONFIGURACION_INICIAL = [
    # (clave, valor, tipo, descripción, grupo)
    ("clinica_nombre", "Sandía", "str", "Nombre de la clínica", "clinica"),
    ("clinica_subtitulo", "Medicina y Spa Veterinario", "str", "Subtítulo o eslogan", "clinica"),
    ("clinica_nit", "", "str", "NIT", "clinica"),
    ("clinica_direccion", "", "str", "Dirección", "clinica"),
    ("clinica_ciudad", "", "str", "Ciudad", "clinica"),
    ("clinica_telefono", "", "str", "Teléfono fijo o celular", "clinica"),
    ("clinica_whatsapp", "", "str", "WhatsApp (solo dígitos, con indicativo 57)", "clinica"),
    ("clinica_email", "", "str", "Correo electrónico", "clinica"),
    ("descontar_stock_ventas", "true", "bool", "Descontar inventario automáticamente al registrar una venta", "ventas"),
]

GRUPOS_CONFIGURACION = {
    "clinica": "Datos de la clínica",
    "ventas": "Ventas e inventario",
}


class ConfiguracionSistema(BaseModel):
    __tablename__ = "configuracion_sistema"

    TIPOS = ("bool", "int", "decimal", "str")

    id = db.Column(db.Integer, primary_key=True)
    clave = db.Column(db.String(80), unique=True, nullable=False)
    valor = db.Column(db.Text)
    tipo = db.Column(db.String(10), nullable=False, default="str")
    descripcion = db.Column(db.String(255))
    grupo = db.Column(db.String(40), nullable=False, default="general")
    actualizado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    fecha_actualizacion = db.Column(db.DateTime(timezone=True))

    actualizado_por = db.relationship("Usuario", foreign_keys=[actualizado_por_id])

    @validates("tipo")
    def _validar_tipo(self, _clave, valor):
        if valor not in self.TIPOS:
            raise ValueError(f"Tipo de configuración inválido: {valor!r}")
        return valor

    # -- conversión de tipos ------------------------------------------------

    @staticmethod
    def convertir(valor, tipo):
        """Convierte el texto almacenado al tipo Python correspondiente."""
        if valor is None:
            return None
        if tipo == "bool":
            return str(valor).strip().lower() in ("1", "true", "si", "sí", "verdadero", "on")
        if tipo == "int":
            try:
                return int(str(valor).strip())
            except ValueError:
                return 0
        if tipo == "decimal":
            try:
                return Decimal(str(valor).strip())
            except InvalidOperation:
                return Decimal("0")
        return str(valor)

    @staticmethod
    def a_texto(valor, tipo):
        """Serializa un valor Python al texto que se guarda en la tabla."""
        if valor is None:
            return ""
        if tipo == "bool":
            return "true" if valor else "false"
        return str(valor)

    @property
    def valor_tipado(self):
        return self.convertir(self.valor, self.tipo)

    # -- acceso con caché por petición -------------------------------------

    @classmethod
    def _cache(cls):
        """Carga todas las filas una sola vez por petición (o contexto de app)."""
        if not has_app_context():
            return {fila.clave: fila for fila in db.session.execute(select(cls)).scalars()}
        cache = getattr(g, "_configuracion_cache", None)
        if cache is None:
            cache = {fila.clave: fila for fila in db.session.execute(select(cls)).scalars()}
            g._configuracion_cache = cache
        return cache

    @classmethod
    def invalidar_cache(cls):
        if has_app_context():
            g.pop("_configuracion_cache", None)

    @classmethod
    def obtener(cls, clave, predeterminado=None):
        """Devuelve el valor tipado de ``clave``; si no existe, el valor inicial."""
        fila = cls._cache().get(clave)
        if fila is not None:
            return fila.valor_tipado
        for clave_inicial, valor, tipo, _descripcion, _grupo in CONFIGURACION_INICIAL:
            if clave_inicial == clave:
                return cls.convertir(valor, tipo)
        return predeterminado

    @classmethod
    def establecer(cls, clave, valor, usuario=None):
        """Guarda ``valor`` en ``clave`` (crea la fila si no existe). No hace commit."""
        fila = cls._cache().get(clave)
        if fila is None:
            fila = db.session.execute(select(cls).filter_by(clave=clave)).scalar_one_or_none()
        if fila is None:
            definicion = next((d for d in CONFIGURACION_INICIAL if d[0] == clave), None)
            if definicion is None:
                raise KeyError(f"Clave de configuración desconocida: {clave}")
            fila = cls(clave=clave, tipo=definicion[2], descripcion=definicion[3], grupo=definicion[4])
            db.session.add(fila)
        fila.valor = cls.a_texto(valor, fila.tipo)
        fila.fecha_actualizacion = obtener_hora_bogota()
        fila.actualizado_por_id = usuario.id if usuario is not None else None
        cls._cache()[clave] = fila
        return fila

    @classmethod
    def listar(cls):
        """Todas las claves conocidas, con su fila real o una fila virtual por defecto."""
        cache = cls._cache()
        resultado = []
        for clave, valor, tipo, descripcion, grupo in CONFIGURACION_INICIAL:
            fila = cache.get(clave)
            if fila is None:
                fila = cls(clave=clave, valor=valor, tipo=tipo, descripcion=descripcion, grupo=grupo)
            resultado.append(fila)
        return resultado

    @classmethod
    def datos_clinica(cls):
        """Diccionario con los datos de la clínica para plantillas e impresos."""
        return {
            "nombre": cls.obtener("clinica_nombre"),
            "subtitulo": cls.obtener("clinica_subtitulo"),
            "nit": cls.obtener("clinica_nit"),
            "direccion": cls.obtener("clinica_direccion"),
            "ciudad": cls.obtener("clinica_ciudad"),
            "telefono": cls.obtener("clinica_telefono"),
            "whatsapp": cls.obtener("clinica_whatsapp"),
            "email": cls.obtener("clinica_email"),
        }

    def __repr__(self):
        return f"<Configuracion {self.clave}={self.valor!r}>"


# ---------------------------------------------------------------------------
# Límite de intentos de inicio de sesión
# ---------------------------------------------------------------------------


class IntentoLogin(BaseModel):
    __tablename__ = "intentos_login"
    __table_args__ = (db.Index("ix_intentos_login_ip_fecha", "ip", "fecha"),)

    LIMITE_INTENTOS = 5
    VENTANA_MINUTOS = 15

    id = db.Column(db.Integer, primary_key=True)
    ip = db.Column(db.String(45), nullable=False)
    email = db.Column(db.String(120))
    exitoso = db.Column(db.Boolean, nullable=False, default=False)
    fecha = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)

    @classmethod
    def fallidos_recientes(cls, ip: str) -> int:
        desde = obtener_hora_bogota() - timedelta(minutes=cls.VENTANA_MINUTOS)
        consulta = select(func.count(cls.id)).where(cls.ip == ip, cls.exitoso.is_(False), cls.fecha >= desde)
        return db.session.execute(consulta).scalar_one()

    @classmethod
    def bloqueado(cls, ip: str) -> bool:
        return cls.fallidos_recientes(ip) >= cls.LIMITE_INTENTOS

    @classmethod
    def registrar(cls, ip: str, email: str, exitoso: bool):
        """Agrega el intento a la sesión (sin commit)."""
        intento = cls(ip=ip, email=(email or "")[:120], exitoso=exitoso, fecha=obtener_hora_bogota())
        db.session.add(intento)
        return intento

    @classmethod
    def limpiar_antiguos(cls, dias: int = 1) -> None:
        """Borra intentos de más de ``dias`` días para que la tabla no crezca sin control."""
        limite = obtener_hora_bogota() - timedelta(days=dias)
        db.session.execute(db.delete(cls).where(cls.fecha < limite))


# ---------------------------------------------------------------------------
# Catálogos de mascotas
# ---------------------------------------------------------------------------

ESPECIES = {
    "canino": "Canino",
    "felino": "Felino",
    "ave": "Ave",
    "roedor": "Roedor",
    "otro": "Otro",
}
ESPECIE_EMOJIS = {"canino": "🐶", "felino": "🐱", "ave": "🐦", "roedor": "🐹", "otro": "🐾"}
SEXOS = {"macho": "Macho", "hembra": "Hembra", "desconocido": "No determinado"}
TAMANOS = {"pequeno": "Pequeño", "mediano": "Mediano", "grande": "Grande", "gigante": "Gigante"}
TIPOS_DOCUMENTO = {
    "CC": "Cédula de ciudadanía",
    "CE": "Cédula de extranjería",
    "TI": "Tarjeta de identidad",
    "PA": "Pasaporte",
    "PPT": "Permiso por protección temporal",
    "NIT": "NIT",
    "OTRO": "Otro",
}


class Raza(BaseModel):
    __tablename__ = "razas"
    __table_args__ = (db.UniqueConstraint("especie", "nombre", name="uq_razas_especie_nombre"),)

    id = db.Column(db.Integer, primary_key=True)
    especie = db.Column(db.String(20), nullable=False)
    nombre = db.Column(db.String(80), nullable=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)

    @validates("especie")
    def _validar_especie(self, _clave, valor):
        if valor not in ESPECIES:
            raise ValueError(f"Especie inválida: {valor!r}")
        return valor

    @validates("nombre")
    def _limpiar_nombre(self, _clave, valor):
        return " ".join((valor or "").split())

    @property
    def especie_etiqueta(self):
        return ESPECIES.get(self.especie, self.especie)

    def __repr__(self):
        return f"<Raza {self.especie}:{self.nombre}>"


# ---------------------------------------------------------------------------
# Tutores (dueños de las mascotas)
# ---------------------------------------------------------------------------


class Tutor(BaseModel):
    __tablename__ = "tutores"
    __table_args__ = (
        db.Index("ix_tutores_nombre_busqueda", "nombre_busqueda"),
        # Único solo cuando hay documento: muchos tutores se registran sin él.
        db.Index(
            "ix_tutores_numero_documento",
            "numero_documento",
            unique=True,
            postgresql_where=text("numero_documento IS NOT NULL"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    tipo_documento = db.Column(db.String(5))
    numero_documento = db.Column(db.String(30))
    nombre_completo = db.Column(db.String(150), nullable=False)
    nombre_busqueda = db.Column(db.String(150), nullable=False, default="")
    telefono = db.Column(db.String(20))
    whatsapp = db.Column(db.String(20))
    email = db.Column(db.String(120))
    direccion = db.Column(db.String(200))
    barrio = db.Column(db.String(100))
    notas = db.Column(db.Text)
    acepta_recordatorios = db.Column(db.Boolean, nullable=False, default=True)
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    fecha_registro = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)
    activo = db.Column(db.Boolean, nullable=False, default=True)

    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])
    mascotas = db.relationship("Mascota", back_populates="tutor", order_by="Mascota.nombre")

    @validates("nombre_completo")
    def _indexar_nombre(self, _clave, valor):
        valor = " ".join((valor or "").split())
        self.nombre_busqueda = normalizar_texto(valor)
        return valor

    @validates("tipo_documento")
    def _validar_tipo_documento(self, _clave, valor):
        valor = (valor or "").strip().upper() or None
        if valor is not None and valor not in TIPOS_DOCUMENTO:
            raise ValueError(f"Tipo de documento inválido: {valor!r}")
        return valor

    @validates("numero_documento", "telefono", "email", "direccion", "barrio")
    def _limpiar_texto(self, clave, valor):
        valor = (valor or "").strip() or None
        if clave == "email" and valor:
            valor = valor.lower()
        return valor

    @validates("whatsapp")
    def _normalizar_whatsapp(self, _clave, valor):
        return normalizar_whatsapp(valor) or None

    @property
    def documento_texto(self) -> str:
        if not self.numero_documento:
            return ""
        return f"{self.tipo_documento or ''} {self.numero_documento}".strip()

    @property
    def whatsapp_efectivo(self) -> str:
        """WhatsApp registrado o, en su defecto, el teléfono si parece celular."""
        return self.whatsapp or normalizar_whatsapp(self.telefono or "")

    def enlace_whatsapp(self, mensaje: str = "") -> str:
        return enlace_whatsapp(self.whatsapp_efectivo, mensaje)

    @property
    def mascotas_activas(self):
        return [m for m in self.mascotas if m.activo]

    def __repr__(self):
        return f"<Tutor {self.id} {self.nombre_completo}>"


# ---------------------------------------------------------------------------
# Mascotas
# ---------------------------------------------------------------------------


class Mascota(BaseModel):
    __tablename__ = "mascotas"
    __table_args__ = (
        db.Index("ix_mascotas_nombre_busqueda", "nombre_busqueda"),
        db.Index("ix_mascotas_microchip", "microchip", unique=True, postgresql_where=text("microchip IS NOT NULL")),
    )

    id = db.Column(db.Integer, primary_key=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey("tutores.id"), nullable=False, index=True)
    nombre = db.Column(db.String(80), nullable=False)
    nombre_busqueda = db.Column(db.String(80), nullable=False, default="")
    especie = db.Column(db.String(20), nullable=False)
    raza_id = db.Column(db.Integer, db.ForeignKey("razas.id"))
    sexo = db.Column(db.String(12), nullable=False, default="desconocido")
    fecha_nacimiento = db.Column(db.Date)
    fecha_nacimiento_estimada = db.Column(db.Boolean, nullable=False, default=False)
    color = db.Column(db.String(60))
    senas_particulares = db.Column(db.Text)
    microchip = db.Column(db.String(30))
    esterilizado = db.Column(db.Boolean, nullable=False, default=False)
    tamano = db.Column(db.String(10))
    alergias = db.Column(db.Text)
    condiciones_preexistentes = db.Column(db.Text)
    foto = db.Column(db.String(255))
    activo = db.Column(db.Boolean, nullable=False, default=True)
    fallecido = db.Column(db.Boolean, nullable=False, default=False)
    fecha_fallecimiento = db.Column(db.Date)
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    fecha_registro = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)

    tutor = db.relationship("Tutor", back_populates="mascotas")
    raza = db.relationship("Raza")
    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])
    registros_peso = db.relationship(
        "RegistroPeso", back_populates="mascota", order_by="RegistroPeso.fecha", cascade="all, delete-orphan"
    )

    @validates("nombre")
    def _indexar_nombre(self, _clave, valor):
        valor = " ".join((valor or "").split())
        self.nombre_busqueda = normalizar_texto(valor)
        return valor

    @validates("especie")
    def _validar_especie(self, _clave, valor):
        if valor not in ESPECIES:
            raise ValueError(f"Especie inválida: {valor!r}")
        return valor

    @validates("sexo")
    def _validar_sexo(self, _clave, valor):
        valor = valor or "desconocido"
        if valor not in SEXOS:
            raise ValueError(f"Sexo inválido: {valor!r}")
        return valor

    @validates("tamano")
    def _validar_tamano(self, _clave, valor):
        valor = valor or None
        if valor is not None and valor not in TAMANOS:
            raise ValueError(f"Tamaño inválido: {valor!r}")
        return valor

    @validates("microchip", "color")
    def _limpiar_texto(self, _clave, valor):
        return (valor or "").strip() or None

    # -- presentación -------------------------------------------------------

    @property
    def especie_etiqueta(self):
        return ESPECIES.get(self.especie, self.especie)

    @property
    def especie_emoji(self):
        return ESPECIE_EMOJIS.get(self.especie, "🐾")

    @property
    def sexo_etiqueta(self):
        return SEXOS.get(self.sexo, self.sexo)

    @property
    def tamano_etiqueta(self):
        return TAMANOS.get(self.tamano, "") if self.tamano else ""

    @property
    def edad(self) -> str:
        """``"2 años 3 meses"`` o ``"≈ 2 años"`` si la fecha es estimada."""
        texto = edad_texto(self.fecha_nacimiento)
        if texto and self.fecha_nacimiento_estimada:
            return f"≈ {texto}"
        return texto

    @property
    def peso_actual(self):
        return self.registros_peso[-1] if self.registros_peso else None

    @peso_actual.setter
    def peso_actual(self, valor):
        if valor is not None:
            reg = RegistroPeso(mascota=self, peso_kg=valor, fecha=obtener_hora_bogota())
            db.session.add(reg)

    @property
    def estado_texto(self) -> str:
        if self.fallecido:
            return "Fallecido"
        return "Activo" if self.activo else "Inactivo"

    def __repr__(self):
        return f"<Mascota {self.id} {self.nombre}>"


class RegistroPeso(BaseModel):
    __tablename__ = "registros_peso"

    id = db.Column(db.Integer, primary_key=True)
    mascota_id = db.Column(db.Integer, db.ForeignKey("mascotas.id"), nullable=False, index=True)
    peso_kg = db.Column(db.Numeric(6, 2), nullable=False)
    fecha = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)
    registrado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))

    mascota = db.relationship("Mascota", back_populates="registros_peso")
    registrado_por = db.relationship("Usuario", foreign_keys=[registrado_por_id])

    def __str__(self):
        return f"{self.peso_kg}"

    def __float__(self):
        return float(self.peso_kg)

    def __repr__(self):
        return f"<RegistroPeso {self.mascota_id} {self.peso_kg} kg>"


# ---------------------------------------------------------------------------
# Inventario y Tienda
# ---------------------------------------------------------------------------

CATEGORIAS_PRODUCTO = {
    "alimento": "Alimento",
    "medicamento": "Medicamento",
    "accesorio": "Accesorio",
    "juguete": "Juguete",
    "servicio": "Servicio",
    "higiene": "Higiene / Estética",
    "otro": "Otro",
}

TIPOS_PRODUCTO = {
    "producto": "Producto físico",
    "servicio": "Servicio",
}

TIPOS_MOVIMIENTO = {
    "entrada": "Entrada por compra",
    "salida": "Salida manual",
    "ajuste_positivo": "Ajuste positivo (+)",
    "ajuste_negativo": "Ajuste negativo (-)",
    "venta": "Venta POS",
    "devolucion": "Devolución",
    "inicial": "Inventario inicial",
}

UNIDADES_MEDIDA = {
    "unidad": "Unidad (un)",
    "kg": "Kilogramo (kg)",
    "g": "Gramo (g)",
    "ml": "Mililitro (ml)",
    "l": "Litro (l)",
    "frasco": "Frasco",
    "caja": "Caja",
    "tableta": "Tableta / Pastilla",
    "ampolla": "Ampolla",
    "bulto": "Bulto / Saco",
    "dosis": "Dosis",
}


class Proveedor(BaseModel):
    __tablename__ = "proveedores"

    id = db.Column(db.Integer, primary_key=True)
    nit = db.Column(db.String(30))
    nombre = db.Column(db.String(120), nullable=False)
    nombre_busqueda = db.Column(db.String(120), nullable=False, default="")
    contacto = db.Column(db.String(100))
    telefono = db.Column(db.String(20))
    email = db.Column(db.String(120))
    direccion = db.Column(db.String(200))
    ciudad = db.Column(db.String(80))
    notas = db.Column(db.Text)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    fecha_registro = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)

    productos = db.relationship("Producto", back_populates="proveedor")

    @validates("nombre")
    def _indexar_nombre(self, _clave, valor):
        valor = " ".join((valor or "").split())
        self.nombre_busqueda = normalizar_texto(valor)
        return valor

    @validates("nit", "telefono", "email", "contacto", "direccion", "ciudad")
    def _limpiar_texto(self, clave, valor):
        valor = (valor or "").strip() or None
        if clave == "email" and valor:
            valor = valor.lower()
        return valor

    def __repr__(self):
        return f"<Proveedor {self.id} {self.nombre}>"


class Producto(BaseModel):
    __tablename__ = "productos"
    __table_args__ = (
        db.Index("ix_productos_sku", "sku", unique=True),
        db.Index("ix_productos_codigo_barras", "codigo_barras", unique=True, postgresql_where=text("codigo_barras IS NOT NULL")),
        db.Index("ix_productos_nombre_busqueda", "nombre_busqueda"),
    )

    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(40), nullable=False)
    codigo_barras = db.Column(db.String(50))
    nombre = db.Column(db.String(150), nullable=False)
    nombre_busqueda = db.Column(db.String(150), nullable=False, default="")
    descripcion = db.Column(db.Text)
    categoria = db.Column(db.String(30), nullable=False, default="otro")
    tipo = db.Column(db.String(20), nullable=False, default="producto")
    requiere_receta = db.Column(db.Boolean, nullable=False, default=False)
    unidad_medida = db.Column(db.String(30), nullable=False, default="unidad")
    precio_costo = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    precio_minimo = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    precio_sugerido = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    cantidad_stock = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    stock_minimo = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    imagen = db.Column(db.String(255))
    proveedor_id = db.Column(db.Integer, db.ForeignKey("proveedores.id"))
    controla_lote = db.Column(db.Boolean, nullable=False, default=False)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    fecha_registro = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)

    proveedor = db.relationship("Proveedor", back_populates="productos")
    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])
    variantes = db.relationship("VarianteProducto", back_populates="producto", order_by="VarianteProducto.id", cascade="all, delete-orphan")
    lotes = db.relationship("Lote", back_populates="producto", order_by="Lote.fecha_vencimiento", cascade="all, delete-orphan")
    movimientos = db.relationship("MovimientoStock", back_populates="producto", order_by="MovimientoStock.fecha.desc()", cascade="all, delete-orphan")

    @validates("nombre")
    def _indexar_nombre(self, _clave, valor):
        valor = " ".join((valor or "").split())
        self.nombre_busqueda = normalizar_texto(valor)
        return valor

    @validates("sku")
    def _limpiar_sku(self, _clave, valor):
        return (valor or "").strip().upper()

    @validates("codigo_barras")
    def _limpiar_codigo_barras(self, _clave, valor):
        return (valor or "").strip() or None

    @validates("categoria")
    def _validar_categoria(self, _clave, valor):
        valor = valor or "otro"
        if valor not in CATEGORIAS_PRODUCTO:
            raise ValueError(f"Categoría inválida: {valor!r}")
        return valor

    @validates("tipo")
    def _validar_tipo(self, _clave, valor):
        valor = valor or "producto"
        if valor not in TIPOS_PRODUCTO:
            raise ValueError(f"Tipo de producto inválido: {valor!r}")
        return valor

    @property
    def categoria_etiqueta(self):
        return CATEGORIAS_PRODUCTO.get(self.categoria, self.categoria)

    @property
    def tiene_variantes(self) -> bool:
        return len([v for v in self.variantes if v.activo]) > 0

    @property
    def stock_total(self) -> Decimal:
        if self.tiene_variantes:
            return sum((v.cantidad_stock for v in self.variantes if v.activo), Decimal("0"))
        return self.cantidad_stock

    @property
    def stock_bajo(self) -> bool:
        if self.tipo == "servicio":
            return False
        return self.stock_total <= self.stock_minimo

    @property
    def lotes_disponibles(self):
        """Lotes activos con cantidad > 0 no vencidos, ordenados FEFO."""
        hoy = hoy_bogota()
        return [l for l in self.lotes if l.cantidad_disponible > 0 and l.fecha_vencimiento >= hoy]

    def __repr__(self):
        return f"<Producto {self.id} {self.sku} {self.nombre}>"


class VarianteProducto(BaseModel):
    __tablename__ = "variantes_producto"
    __table_args__ = (
        db.Index("ix_variantes_sku", "sku", unique=True, postgresql_where=text("sku IS NOT NULL")),
        db.Index("ix_variantes_codigo_barras", "codigo_barras", unique=True, postgresql_where=text("codigo_barras IS NOT NULL")),
    )

    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=False, index=True)
    nombre_variante = db.Column(db.String(100), nullable=False)
    sku = db.Column(db.String(40))
    codigo_barras = db.Column(db.String(50))
    precio_costo = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    precio_minimo = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    precio_sugerido = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    cantidad_stock = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    stock_minimo = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    activo = db.Column(db.Boolean, nullable=False, default=True)

    producto = db.relationship("Producto", back_populates="variantes")

    @validates("sku")
    def _limpiar_sku(self, _clave, valor):
        return (valor or "").strip().upper() or None

    @validates("codigo_barras")
    def _limpiar_codigo(self, _clave, valor):
        return (valor or "").strip() or None

    @property
    def stock_bajo(self) -> bool:
        return self.cantidad_stock <= self.stock_minimo

    def __repr__(self):
        return f"<VarianteProducto {self.id} {self.nombre_variante}>"


class Lote(BaseModel):
    __tablename__ = "lotes"
    __table_args__ = (
        db.Index("ix_lotes_producto_vencimiento", "producto_id", "fecha_vencimiento"),
    )

    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=False, index=True)
    variante_id = db.Column(db.Integer, db.ForeignKey("variantes_producto.id"))
    numero_lote = db.Column(db.String(60), nullable=False)
    fecha_vencimiento = db.Column(db.Date, nullable=False)
    cantidad_inicial = db.Column(db.Numeric(12, 2), nullable=False)
    cantidad_disponible = db.Column(db.Numeric(12, 2), nullable=False)
    proveedor_id = db.Column(db.Integer, db.ForeignKey("proveedores.id"))
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    fecha_ingreso = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)

    producto = db.relationship("Producto", back_populates="lotes")
    variante = db.relationship("VarianteProducto")
    proveedor = db.relationship("Proveedor")
    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])

    @property
    def vencido(self) -> bool:
        return self.fecha_vencimiento < hoy_bogota()

    @property
    def dias_para_vencer(self) -> int:
        return (self.fecha_vencimiento - hoy_bogota()).days

    def __repr__(self):
        return f"<Lote {self.id} {self.numero_lote} vence {self.fecha_vencimiento}>"


class MovimientoStock(BaseModel):
    __tablename__ = "movimientos_stock"
    __table_args__ = (
        db.Index("ix_movimientos_producto_fecha", "producto_id", "fecha"),
    )

    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=False, index=True)
    variante_id = db.Column(db.Integer, db.ForeignKey("variantes_producto.id"))
    lote_id = db.Column(db.Integer, db.ForeignKey("lotes.id"))
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    tipo_movimiento = db.Column(db.String(30), nullable=False)
    cantidad = db.Column(db.Numeric(12, 2), nullable=False)
    stock_anterior = db.Column(db.Numeric(12, 2), nullable=False)
    stock_nuevo = db.Column(db.Numeric(12, 2), nullable=False)
    motivo = db.Column(db.Text)
    referencia = db.Column(db.String(100))
    fecha = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)

    producto = db.relationship("Producto", back_populates="movimientos")
    variante = db.relationship("VarianteProducto")
    lote = db.relationship("Lote")
    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])

    @property
    def tipo_etiqueta(self):
        return TIPOS_MOVIMIENTO.get(self.tipo_movimiento, self.tipo_movimiento)

    def __repr__(self):
        return f"<MovimientoStock {self.id} {self.tipo_movimiento} {self.cantidad}>"


# ---------------------------------------------------------------------------
# Fase 4: Punto de Venta (POS) y Caja
# ---------------------------------------------------------------------------

METODOS_PAGO = {
    "efectivo": "Efectivo",
    "nequi": "Nequi",
    "daviplata": "Daviplata",
    "tarjeta_debito": "Tarjeta Débito",
    "tarjeta_credito": "Tarjeta Crédito",
    "transferencia": "Transferencia Bancaria",
}

ESTADOS_VENTA = {
    "completada": "Completada",
    "anulada": "Anulada",
}

ESTADOS_APROBACION_PRECIO = {
    "pendiente": "Pendiente",
    "aprobado": "Aprobado",
    "rechazado": "Rechazado",
    "utilizada": "Utilizada",
    "cancelada": "Cancelada",
}


class AprobacionPrecio(BaseModel):
    """Solicitud de excepción cuando un cajero intenta vender bajo el precio mínimo.

    El cajero no puede completar la venta hasta que un admin apruebe (con el
    precio solicitado o una contraoferta) o rechace la solicitud. Una vez usada
    en una venta, queda marcada ``utilizada`` y no puede reutilizarse.
    """

    __tablename__ = "aprobaciones_precio"
    __table_args__ = (
        db.Index("ix_aprobaciones_precio_estado", "estado"),
    )

    id = db.Column(db.Integer, primary_key=True)
    solicitante_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"), nullable=False)
    variante_id = db.Column(db.Integer, db.ForeignKey("variantes_producto.id"))
    descripcion = db.Column(db.String(180), nullable=False)

    precio_original = db.Column(db.Numeric(12, 2), nullable=False)  # precio_minimo vigente al solicitar
    precio_solicitado = db.Column(db.Numeric(12, 2), nullable=False)  # lo que el cajero quiere cobrar
    precio_aprobado = db.Column(db.Numeric(12, 2))  # lo que el admin autoriza (puede ser una contraoferta)

    estado = db.Column(db.String(20), nullable=False, default="pendiente")
    admin_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    motivo = db.Column(db.Text)
    motivo_rechazo = db.Column(db.Text)

    fecha_solicitud = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)
    fecha_resolucion = db.Column(db.DateTime(timezone=True))
    venta_id = db.Column(db.Integer, db.ForeignKey("ventas.id"))

    solicitante = db.relationship("Usuario", foreign_keys=[solicitante_id])
    admin = db.relationship("Usuario", foreign_keys=[admin_id])
    producto = db.relationship("Producto")
    variante = db.relationship("VarianteProducto")
    venta = db.relationship("Venta")

    @validates("estado")
    def _validar_estado(self, _clave, valor):
        if valor not in ESTADOS_APROBACION_PRECIO:
            raise ValueError(f"Estado de aprobación inválido: {valor!r}")
        return valor

    @property
    def estado_etiqueta(self):
        return ESTADOS_APROBACION_PRECIO.get(self.estado, self.estado)

    def __repr__(self):
        return f"<AprobacionPrecio {self.id} {self.descripcion} estado={self.estado}>"


class TurnoCaja(BaseModel):
    __tablename__ = "turnos_caja"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    monto_apertura = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    monto_cierre_esperado = db.Column(db.Numeric(12, 2))
    monto_cierre_real = db.Column(db.Numeric(12, 2))
    diferencia = db.Column(db.Numeric(12, 2))
    estado = db.Column(db.String(20), nullable=False, default="abierta")
    fecha_apertura = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)
    fecha_cierre = db.Column(db.DateTime(timezone=True))
    notas_apertura = db.Column(db.Text)
    notas_cierre = db.Column(db.Text)

    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])
    ventas = db.relationship("Venta", back_populates="turno_caja", lazy="dynamic")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    @property
    def esta_abierta(self) -> bool:
        return self.estado == "abierta"

    def __repr__(self):
        return f"<TurnoCaja {self.id} usuario={self.usuario_id} estado={self.estado}>"


class Venta(BaseModel):
    __tablename__ = "ventas"
    __table_args__ = (
        db.Index("ix_ventas_numero_factura", "numero_factura", unique=True),
        db.Index("ix_ventas_fecha", "fecha_venta"),
    )

    id = db.Column(db.Integer, primary_key=True)
    numero_factura = db.Column(db.String(40), nullable=False)
    turno_caja_id = db.Column(db.Integer, db.ForeignKey("turnos_caja.id"), nullable=False, index=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey("tutores.id"), index=True)
    mascota_id = db.Column(db.Integer, db.ForeignKey("mascotas.id"), index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)

    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    descuento_monto = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    impuesto_monto = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    total = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))

    estado = db.Column(db.String(20), nullable=False, default="completada")
    motivo_anulacion = db.Column(db.Text)
    anulada_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    fecha_venta = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)
    fecha_anulacion = db.Column(db.DateTime(timezone=True))

    turno_caja = db.relationship("TurnoCaja", back_populates="ventas")
    tutor = db.relationship("Tutor")
    mascota = db.relationship("Mascota")
    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])
    anulada_por = db.relationship("Usuario", foreign_keys=[anulada_por_id])
    detalles = db.relationship("DetalleVenta", back_populates="venta", cascade="all, delete-orphan")
    pagos = db.relationship("PagoVenta", back_populates="venta", cascade="all, delete-orphan")

    @property
    def estado_etiqueta(self):
        return ESTADOS_VENTA.get(self.estado, self.estado)

    @property
    def mensaje_whatsapp(self) -> str:
        """Mensaje pre-redactado con el documento oficial de factura para enviar por WhatsApp."""
        nombre_tutor = self.tutor.nombre_completo if self.tutor else "Estimado/a cliente"
        nombre_mascota = f" (Mascota: {self.mascota.nombre})" if self.mascota else ""
        total_str = f"${int(self.total):,}".replace(",", ".")
        fecha_str = self.fecha_venta.strftime('%d/%m/%Y %I:%M %p') if hasattr(self.fecha_venta, 'strftime') else str(self.fecha_venta)
        url_factura = _generar_url_segura("pos.venta_pdf", id=self.id)

        return (
            f"🐾 *Sandía · Medicina & Spa Veterinario* 🍉\n"
            f"🧾 *COMPROBANTE OFICIAL DE PAGO #{self.numero_factura}*\n\n"
            f"Hola *{nombre_tutor}*{nombre_mascota},\n"
            f"Te compartimos el comprobante de pago oficial de tu visita ({fecha_str}).\n\n"
            f"💰 *TOTAL PAGADO:* {total_str}\n\n"
            f"📄 *Descargar Factura Oficial en PDF:*\n"
            f"👉 {url_factura}\n\n"
            f"¡Muchas gracias por tu visita y por confiar en nosotros! 🐾❤️\n"
            f"_Sandía Medicina & Spa Veterinario_"
        )

    @property
    def enlace_whatsapp(self) -> str:
        if not self.tutor:
            return ""
        tel = self.tutor.whatsapp or self.tutor.telefono
        if not tel:
            return ""
        return enlace_whatsapp(tel, self.mensaje_whatsapp)

    def __repr__(self):
        return f"<Venta {self.id} {self.numero_factura} total={self.total}>"


class DetalleVenta(BaseModel):
    __tablename__ = "detalles_venta"

    id = db.Column(db.Integer, primary_key=True)
    venta_id = db.Column(db.Integer, db.ForeignKey("ventas.id"), nullable=False, index=True)
    producto_id = db.Column(db.Integer, db.ForeignKey("productos.id"))
    variante_id = db.Column(db.Integer, db.ForeignKey("variantes_producto.id"))
    lote_id = db.Column(db.Integer, db.ForeignKey("lotes.id"))

    descripcion = db.Column(db.String(180), nullable=False)
    tipo_item = db.Column(db.String(20), nullable=False, default="producto")
    cantidad = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("1.00"))
    precio_unitario = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    descuento = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    total_linea = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))

    venta = db.relationship("Venta", back_populates="detalles")
    producto = db.relationship("Producto")
    variante = db.relationship("VarianteProducto")
    lote = db.relationship("Lote")

    def __repr__(self):
        return f"<DetalleVenta {self.id} {self.descripcion} qty={self.cantidad}>"


class PagoVenta(BaseModel):
    __tablename__ = "pagos_venta"

    id = db.Column(db.Integer, primary_key=True)
    venta_id = db.Column(db.Integer, db.ForeignKey("ventas.id"), nullable=False, index=True)
    metodo_pago = db.Column(db.String(30), nullable=False)
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    referencia_transaccion = db.Column(db.String(100))
    fecha_pago = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)

    venta = db.relationship("Venta", back_populates="pagos")

    @property
    def metodo_etiqueta(self):
        return METODOS_PAGO.get(self.metodo_pago, self.metodo_pago)

    def __repr__(self):
        return f"<PagoVenta {self.id} {self.metodo_pago} monto={self.monto}>"


# ---------------------------------------------------------------------------
# Fase 5: Spa & Peluquería de Mascotas (Grooming)
# ---------------------------------------------------------------------------

ESTADOS_SPA = {
    "programada": "Programada",
    "en_proceso": "En proceso de grooming",
    "listo_recogida": "¡Listo para recogida!",
    "entregado": "Entregado a tutor",
    "cancelada": "Cancelada",
}


class ServicioSpa(BaseModel):
    __tablename__ = "servicios_spa"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    descripcion = db.Column(db.Text)
    duracion_minutos = db.Column(db.Integer, nullable=False, default=60)
    precio_sugerido = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    especie = db.Column(db.String(20))
    tamano_mascota = db.Column(db.String(20))
    activo = db.Column(db.Boolean, nullable=False, default=True)

    def __repr__(self):
        return f"<ServicioSpa {self.id} {self.nombre}>"


class CitaSpa(BaseModel):
    __tablename__ = "citas_spa"
    __table_args__ = (
        db.Index("ix_citas_spa_fecha", "fecha_hora"),
        db.Index("ix_citas_spa_estado", "estado"),
    )

    id = db.Column(db.Integer, primary_key=True)
    mascota_id = db.Column(db.Integer, db.ForeignKey("mascotas.id"), nullable=False, index=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey("tutores.id"), nullable=False, index=True)
    groomer_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), index=True)
    servicio_spa_id = db.Column(db.Integer, db.ForeignKey("servicios_spa.id"), nullable=False)

    fecha_hora = db.Column(db.DateTime(timezone=True), nullable=False)
    duracion_minutos = db.Column(db.Integer, nullable=False, default=60)
    estado = db.Column(db.String(20), nullable=False, default="programada")

    notas_ingreso = db.Column(db.Text)
    notas_salida = db.Column(db.Text)
    foto_ingreso = db.Column(db.String(255))
    foto_salida = db.Column(db.String(255))
    notificado_whatsapp = db.Column(db.Boolean, nullable=False, default=False)
    fecha_listo = db.Column(db.DateTime(timezone=True))
    venta_id = db.Column(db.Integer, db.ForeignKey("ventas.id"))

    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    fecha_registro = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)

    mascota = db.relationship("Mascota")
    tutor = db.relationship("Tutor")
    groomer = db.relationship("Usuario", foreign_keys=[groomer_id])
    servicio_spa = db.relationship("ServicioSpa")
    venta = db.relationship("Venta")
    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])

    @property
    def url_foto_ingreso(self) -> str | None:
        if not self.foto_ingreso:
            return None
        return url_for("static", filename=f"uploads/spa/{self.foto_ingreso}")

    @property
    def url_mini_ingreso(self) -> str | None:
        if not self.foto_ingreso:
            return None
        return url_for("static", filename=f"uploads/spa/mini_{self.foto_ingreso}")

    @property
    def url_foto_salida(self) -> str | None:
        if not self.foto_salida:
            return None
        return url_for("static", filename=f"uploads/spa/{self.foto_salida}")

    @property
    def url_mini_salida(self) -> str | None:
        if not self.foto_salida:
            return None
        return url_for("static", filename=f"uploads/spa/mini_{self.foto_salida}")

    @property
    def tiene_fotos(self) -> bool:
        return bool(self.foto_ingreso or self.foto_salida)

    @property
    def estado_etiqueta(self):
        return ESTADOS_SPA.get(self.estado, self.estado)

    @property
    def mensaje_whatsapp(self) -> str:
        """Mensaje pre-redactado de aviso de finalización de grooming con documento."""
        nombre_tutor = self.tutor.nombre_completo if self.tutor else "Estimado/a cliente"
        nombre_mascota = self.mascota.nombre if self.mascota else "su mascota"
        nombre_servicio = self.servicio_spa.nombre if self.servicio_spa else "Spa"
        url_doc = _generar_url_segura("spa.cita_spa_pdf", id=self.id)

        observaciones = f"✏️ *Observaciones del estilista:*\n_{self.notas_salida}_\n\n" if self.notas_salida else ""

        return (
            f"🐾 *Sandía · Medicina & Spa Veterinario* ✂️🧼\n"
            f"✨ *¡{nombre_mascota} ESTÁ LISTO/A PARA RECOGIDA!*\n\n"
            f"Hola *{nombre_tutor}*,\n"
            f"Te informamos que *{nombre_mascota}* ha terminado su servicio de *{nombre_servicio}* y ya está listo/a y hermoso/a para su recogida.\n\n"
            f"{observaciones}"
            f"📄 *Descargar Certificado de Spa en PDF:*\n"
            f"👉 {url_doc}\n\n"
            f"¡Te esperamos pronto! 🐾❤️\n"
            f"_Sandía Spa & Grooming_"
        )

    @property
    def enlace_whatsapp(self) -> str | None:
        if not self.tutor or not self.tutor.telefono:
            return None
        return enlace_whatsapp(self.tutor.telefono, self.mensaje_whatsapp)

    def __repr__(self):
        return f"<CitaSpa {self.id} mascota={self.mascota_id} estado={self.estado}>"


# ---------------------------------------------------------------------------
# Fase 6: Historias Clínicas, Vacunación y Desparasitación
# ---------------------------------------------------------------------------


class ConsultaMedica(BaseModel):
    __tablename__ = "consultas_medicas"
    __table_args__ = (
        db.Index("ix_consultas_medicas_mascota_fecha", "mascota_id", "fecha_hora"),
    )

    id = db.Column(db.Integer, primary_key=True)
    mascota_id = db.Column(db.Integer, db.ForeignKey("mascotas.id"), nullable=False, index=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey("tutores.id"), nullable=False, index=True)
    veterinario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    fecha_hora = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)

    # SOAP
    motivo_consulta = db.Column(db.String(255), nullable=False)
    anamnesis = db.Column(db.Text)  # Subjetivo (S)

    # Examen físico / Constantes vitales (Objetivo - O)
    peso_kg = db.Column(db.Numeric(6, 2))
    temperatura_c = db.Column(db.Numeric(4, 1))
    frecuencia_cardiaca = db.Column(db.Integer)
    frecuencia_respiratoria = db.Column(db.Integer)
    tllc_segundos = db.Column(db.Integer)
    mucosas = db.Column(db.String(50))
    condicion_corporal = db.Column(db.String(20))
    examen_sistemas = db.Column(db.Text)  # Hallazgos de examen físico por sistemas

    diagnostico = db.Column(db.Text, nullable=False)  # Avalúo / Diagnóstico (A)
    plan_tratamiento = db.Column(db.Text, nullable=False)  # Plan / Tratamiento (P)
    receta_medica = db.Column(db.Text)
    observaciones = db.Column(db.Text)

    venta_id = db.Column(db.Integer, db.ForeignKey("ventas.id"))
    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    fecha_registro = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)

    mascota = db.relationship("Mascota", backref=db.backref("consultas", order_by="desc(ConsultaMedica.fecha_hora)"))
    tutor = db.relationship("Tutor")
    veterinario = db.relationship("Usuario", foreign_keys=[veterinario_id])
    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])
    venta = db.relationship("Venta")
    enmiendas = db.relationship(
        "EnmiendaConsulta", back_populates="consulta", order_by="EnmiendaConsulta.fecha", cascade="all, delete-orphan"
    )

    @property
    def mensaje_whatsapp(self) -> str:
        nombre_tutor = self.tutor.nombre_completo if self.tutor else "Estimado/a cliente"
        nombre_mascota = self.mascota.nombre if self.mascota else "su mascota"
        fecha_str = self.fecha_hora.strftime("%d/%m/%Y") if hasattr(self.fecha_hora, "strftime") else str(self.fecha_hora)
        url_doc = _generar_url_segura("historias.consulta_documento_publico", id=self.id)

        msg = f"🐾 *Sandía · Medicina & Spa Veterinario* 🍉\n"
        msg += f"📋 *INFORME MÉDICO OFICIAL & RECETA (SOAP)*\n\n"
        msg += f"Hola *{nombre_tutor}*, te compartimos el documento oficial correspondiente a la consulta de *{nombre_mascota}* ({fecha_str}).\n\n"
        msg += f"• *Diagnóstico:* {self.diagnostico}\n"
        msg += f"\n📄 *Ver / Descargar Documento Oficial en PDF:*\n"
        msg += f"👉 {url_doc}\n\n"
        msg += f"¡Muchas gracias por confiar en nosotros! 🐾❤️\n"
        msg += f"_Sandía Medicina & Spa Veterinario_"
        return msg

    @property
    def enlace_whatsapp(self) -> str | None:
        if not self.tutor or not self.tutor.whatsapp_efectivo:
            return None
        return enlace_whatsapp(self.tutor.whatsapp_efectivo, self.mensaje_whatsapp)

    @property
    def sistemas_evaluados(self) -> dict | None:
        """Devuelve el diccionario de sistemas estructurado si examen_sistemas es JSON valido."""
        if not self.examen_sistemas:
            return None
        try:
            import json
            data = json.loads(self.examen_sistemas)
            if isinstance(data, dict) and "sistemas" in data and isinstance(data["sistemas"], dict):
                return data["sistemas"]
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return None

    @property
    def resumen_sistemas(self) -> dict:
        """Devuelve un resumen con conteos de sistemas normales y anormales."""
        sistemas = self.sistemas_evaluados
        if not sistemas:
            return {"total": 0, "normales": 0, "anormales": 0, "anormales_lista": []}
        normales = sum(1 for s in sistemas.values() if isinstance(s, dict) and s.get("estado") == "normal")
        anormales = [s.get("nombre") or k for k, s in sistemas.items() if isinstance(s, dict) and s.get("estado") == "anormal"]
        return {
            "total": len(sistemas),
            "normales": normales,
            "anormales": len(anormales),
            "anormales_lista": anormales,
        }

    def __repr__(self):
        return f"<ConsultaMedica {self.id} mascota={self.mascota_id} fecha={self.fecha_hora}>"


class EnmiendaConsulta(BaseModel):
    """Corrección de una consulta ya firmada: la consulta original nunca se
    edita ni se borra (rule 8); toda corrección queda registrada aparte,
    con autor y fecha, y se muestra anexada al final del reporte."""

    __tablename__ = "enmiendas_consulta"

    id = db.Column(db.Integer, primary_key=True)
    consulta_id = db.Column(db.Integer, db.ForeignKey("consultas_medicas.id"), nullable=False, index=True)
    autor_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    texto = db.Column(db.Text, nullable=False)
    fecha = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)

    consulta = db.relationship("ConsultaMedica", back_populates="enmiendas")
    autor = db.relationship("Usuario", foreign_keys=[autor_id])

    def __repr__(self):
        return f"<EnmiendaConsulta {self.id} consulta={self.consulta_id}>"


class VacunaMascota(BaseModel):
    __tablename__ = "vacunas_mascotas"
    __table_args__ = (
        db.Index("ix_vacunas_mascotas_mascota_proxima", "mascota_id", "fecha_proxima"),
    )

    id = db.Column(db.Integer, primary_key=True)
    mascota_id = db.Column(db.Integer, db.ForeignKey("mascotas.id"), nullable=False, index=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey("tutores.id"), nullable=False, index=True)
    veterinario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))

    nombre_vacuna = db.Column(db.String(120), nullable=False)
    lote = db.Column(db.String(60))
    laboratorio = db.Column(db.String(100))
    dosis = db.Column(db.String(50), default="1.0 mL")
    fecha_aplicacion = db.Column(db.Date, nullable=False)
    fecha_proxima = db.Column(db.Date, nullable=False)
    observaciones = db.Column(db.Text)

    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    fecha_registro = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)

    mascota = db.relationship("Mascota", backref=db.backref("vacunas", order_by="desc(VacunaMascota.fecha_aplicacion)"))
    tutor = db.relationship("Tutor")
    veterinario = db.relationship("Usuario", foreign_keys=[veterinario_id])
    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])

    @property
    def estado_vencimiento(self) -> str:
        """Devuelve 'al_dia', 'proxima_vencer' (<= 15 días), o 'vencida'."""
        hoy = hoy_bogota()
        if self.fecha_proxima < hoy:
            return "vencida"
        elif (self.fecha_proxima - hoy).days <= 15:
            return "proxima_vencer"
        return "al_dia"

    @property
    def mensaje_whatsapp(self) -> str:
        """Mensaje pre-redactado de recordatorio de vacunación."""
        nombre_tutor = self.tutor.nombre_completo if self.tutor else "Estimado/a cliente"
        nombre_mascota = self.mascota.nombre if self.mascota else "su mascota"
        return (
            f"Hola {nombre_tutor}, te recordamos desde VetCare que a {nombre_mascota} le corresponde "
            f"la vacuna {self.nombre_vacuna} ({self.fecha_proxima.strftime('%d/%m/%Y')}). "
            "Agenda cuando puedas. 🐾💉"
        )

    @property
    def enlace_whatsapp(self) -> str | None:
        if not self.tutor or not self.tutor.telefono:
            return None
        return enlace_whatsapp(self.tutor.telefono, self.mensaje_whatsapp)

    def __repr__(self):
        return f"<VacunaMascota {self.id} mascota={self.mascota_id} vacuna={self.nombre_vacuna!r}>"


class DesparasitacionMascota(BaseModel):
    __tablename__ = "desparasitaciones_mascotas"
    __table_args__ = (
        db.Index("ix_desparasitaciones_mascotas_mascota", "mascota_id", "fecha_aplicacion"),
    )

    id = db.Column(db.Integer, primary_key=True)
    mascota_id = db.Column(db.Integer, db.ForeignKey("mascotas.id"), nullable=False, index=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey("tutores.id"), nullable=False, index=True)
    veterinario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))

    producto = db.Column(db.String(120), nullable=False)
    tipo = db.Column(db.String(20), nullable=False, default="interna")  # interna, externa, mixta
    dosis = db.Column(db.String(50))
    peso_kg = db.Column(db.Numeric(6, 2))
    fecha_aplicacion = db.Column(db.Date, nullable=False)
    fecha_proxima = db.Column(db.Date)
    observaciones = db.Column(db.Text)

    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    fecha_registro = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)

    mascota = db.relationship("Mascota", backref=db.backref("desparasitaciones", order_by="desc(DesparasitacionMascota.fecha_aplicacion)"))
    tutor = db.relationship("Tutor")
    veterinario = db.relationship("Usuario", foreign_keys=[veterinario_id])
    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])

    @property
    def estado_vencimiento(self) -> str:
        if not self.fecha_proxima:
            return "al_dia"
        hoy = hoy_bogota()
        if self.fecha_proxima < hoy:
            return "vencida"
        elif (self.fecha_proxima - hoy).days <= 15:
            return "proxima_vencer"
        return "al_dia"

    @property
    def mensaje_whatsapp(self) -> str:
        nombre_tutor = self.tutor.nombre_completo if self.tutor else "Estimado/a cliente"
        nombre_mascota = self.mascota.nombre if self.mascota else "su mascota"
        proxima_str = self.fecha_proxima.strftime("%d/%m/%Y") if self.fecha_proxima and hasattr(self.fecha_proxima, "strftime") else "próximamente"
        return (
            f"Hola {nombre_tutor}, te enviamos el registro de desparasitación de {nombre_mascota}:\n"
            f"• Producto: {self.producto} ({self.tipo.capitalize()})\n"
            f"• Próxima dosis: {proxima_str}\n"
            "¡Gracias por cuidar la salud de tu mascota con Sandía VetCare! 🐾"
        )

    @property
    def enlace_whatsapp(self) -> str | None:
        if not self.tutor or not self.tutor.whatsapp_efectivo:
            return None
        return enlace_whatsapp(self.tutor.whatsapp_efectivo, self.mensaje_whatsapp)

    def __repr__(self):
        return f"<DesparasitacionMascota {self.id} mascota={self.mascota_id} producto={self.producto!r}>"






# ---------------------------------------------------------------------------
# Agenda médica general (consultas, vacunación, cirugía, control)
# ---------------------------------------------------------------------------

TIPOS_CITA = {
    "consulta": "Consulta",
    "vacunacion": "Vacunación",
    "cirugia": "Cirugía",
    "control": "Control",
    "otro": "Otro",
}

ESTADOS_CITA = {
    "programada": "Programada",
    "confirmada": "Confirmada",
    "en_atencion": "En atención",
    "cumplida": "Cumplida",
    "no_asistio": "No asistió",
    "cancelada": "Cancelada",
}


class Cita(BaseModel):
    """Agenda médica general: consultas, vacunación, cirugía y controles.
    Es independiente de ``CitaSpa`` (agenda de grooming)."""

    __tablename__ = "citas"
    __table_args__ = (
        db.Index("ix_citas_fecha_hora", "fecha_hora"),
        db.Index("ix_citas_estado", "estado"),
    )

    id = db.Column(db.Integer, primary_key=True)
    mascota_id = db.Column(db.Integer, db.ForeignKey("mascotas.id"), nullable=False, index=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey("tutores.id"), nullable=False, index=True)
    profesional_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), index=True)

    tipo = db.Column(db.String(20), nullable=False, default="consulta")
    fecha_hora = db.Column(db.DateTime(timezone=True), nullable=False)
    duracion_minutos = db.Column(db.Integer, nullable=False, default=30)
    estado = db.Column(db.String(20), nullable=False, default="programada")
    motivo = db.Column(db.String(255))
    notas = db.Column(db.Text)
    recordatorio_enviado = db.Column(db.Boolean, nullable=False, default=False)

    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    fecha_registro = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)

    mascota = db.relationship("Mascota")
    tutor = db.relationship("Tutor")
    profesional = db.relationship("Usuario", foreign_keys=[profesional_id])
    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])

    @validates("tipo")
    def _validar_tipo(self, _clave, valor):
        valor = valor or "consulta"
        if valor not in TIPOS_CITA:
            raise ValueError(f"Tipo de cita inválido: {valor!r}")
        return valor

    @validates("estado")
    def _validar_estado(self, _clave, valor):
        valor = valor or "programada"
        if valor not in ESTADOS_CITA:
            raise ValueError(f"Estado de cita inválido: {valor!r}")
        return valor

    @property
    def tipo_etiqueta(self):
        return TIPOS_CITA.get(self.tipo, self.tipo)

    @property
    def estado_etiqueta(self):
        return ESTADOS_CITA.get(self.estado, self.estado)

    @property
    def mensaje_whatsapp(self) -> str:
        nombre_tutor = self.tutor.nombre_completo if self.tutor else "Estimado/a cliente"
        nombre_mascota = self.mascota.nombre if self.mascota else "su mascota"
        return (
            f"¡Hola {nombre_tutor}! 👋🍉 Te recordamos con mucho cariño desde *Sandía Medicina & Spa Veterinario* la cita de *{nombre_mascota}* "
            f"({self.tipo_etiqueta}) programada para el {self.fecha_hora.strftime('%d/%m/%Y')} a las "
            f"{self.fecha_hora.strftime('%I:%M %p')}. ¡Te esperamos! 🐾✨"
        )

    @property
    def enlace_whatsapp(self) -> str | None:
        if not self.tutor or not self.tutor.telefono:
            return None
        return enlace_whatsapp(self.tutor.telefono, self.mensaje_whatsapp)

    def __repr__(self):
        return f"<Cita {self.id} {self.tipo} {self.fecha_hora}>"


# ---------------------------------------------------------------------------
# Hospitalización
# ---------------------------------------------------------------------------

ESTADOS_HOSPITALIZACION = {
    "activa": "Activa",
    "alta": "De alta",
    "fallecido": "Fallecido",
    "remitido": "Remitido",
}


class Hospitalizacion(BaseModel):
    __tablename__ = "hospitalizaciones"
    __table_args__ = (db.Index("ix_hospitalizaciones_estado", "estado"),)

    id = db.Column(db.Integer, primary_key=True)
    mascota_id = db.Column(db.Integer, db.ForeignKey("mascotas.id"), nullable=False, index=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey("tutores.id"), nullable=False)
    veterinario_responsable_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))

    fecha_ingreso = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)
    fecha_egreso = db.Column(db.DateTime(timezone=True))
    motivo = db.Column(db.Text, nullable=False)
    diagnostico = db.Column(db.Text)
    jaula = db.Column(db.String(30))
    estado = db.Column(db.String(20), nullable=False, default="activa")
    costo_dia = db.Column(db.Numeric(12, 2), nullable=False, default=Decimal("0.00"))
    venta_id = db.Column(db.Integer, db.ForeignKey("ventas.id"))

    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    fecha_registro = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)

    mascota = db.relationship("Mascota")
    tutor = db.relationship("Tutor")
    veterinario_responsable = db.relationship("Usuario", foreign_keys=[veterinario_responsable_id])
    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])
    venta = db.relationship("Venta")
    evoluciones = db.relationship(
        "EvolucionHospitalaria", back_populates="hospitalizacion",
        order_by="desc(EvolucionHospitalaria.fecha_hora)", cascade="all, delete-orphan",
    )

    @validates("estado")
    def _validar_estado(self, _clave, valor):
        valor = valor or "activa"
        if valor not in ESTADOS_HOSPITALIZACION:
            raise ValueError(f"Estado de hospitalización inválido: {valor!r}")
        return valor

    @property
    def estado_etiqueta(self):
        return ESTADOS_HOSPITALIZACION.get(self.estado, self.estado)

    @property
    def dias_hospitalizado(self) -> int:
        fin = self.fecha_egreso or obtener_hora_bogota()
        return max(1, (fin.date() - self.fecha_ingreso.date()).days + 1)

    @property
    def costo_estimado(self):
        return self.costo_dia * self.dias_hospitalizado

    def __repr__(self):
        return f"<Hospitalizacion {self.id} mascota={self.mascota_id} estado={self.estado}>"


class EvolucionHospitalaria(BaseModel):
    __tablename__ = "evoluciones_hospitalarias"

    id = db.Column(db.Integer, primary_key=True)
    hospitalizacion_id = db.Column(db.Integer, db.ForeignKey("hospitalizaciones.id"), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    fecha_hora = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)
    constantes = db.Column(db.Text)
    tratamiento_aplicado = db.Column(db.Text)
    observaciones = db.Column(db.Text)
    alimentacion = db.Column(db.String(120))
    eliminaciones = db.Column(db.String(120))

    hospitalizacion = db.relationship("Hospitalizacion", back_populates="evoluciones")
    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])

    def __repr__(self):
        return f"<EvolucionHospitalaria {self.id} hosp={self.hospitalizacion_id}>"


# ---------------------------------------------------------------------------
# Cirugías
# ---------------------------------------------------------------------------


class Cirugia(BaseModel):
    __tablename__ = "cirugias"

    id = db.Column(db.Integer, primary_key=True)
    mascota_id = db.Column(db.Integer, db.ForeignKey("mascotas.id"), nullable=False, index=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey("tutores.id"), nullable=False)
    veterinario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)

    tipo_procedimiento = db.Column(db.String(150), nullable=False)
    fecha = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)
    consentimiento_firmado = db.Column(db.Boolean, nullable=False, default=False)
    archivo_consentimiento = db.Column(db.String(255))
    notas_prequirurgicas = db.Column(db.Text)
    protocolo_anestesico = db.Column(db.Text)
    notas_postquirurgicas = db.Column(db.Text)
    venta_id = db.Column(db.Integer, db.ForeignKey("ventas.id"))

    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    fecha_registro = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)

    mascota = db.relationship("Mascota")
    tutor = db.relationship("Tutor")
    veterinario = db.relationship("Usuario", foreign_keys=[veterinario_id])
    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])
    venta = db.relationship("Venta")

    def __repr__(self):
        return f"<Cirugia {self.id} {self.tipo_procedimiento!r} mascota={self.mascota_id}>"


# ---------------------------------------------------------------------------
# Exámenes de laboratorio
# ---------------------------------------------------------------------------

CATEGORIAS_EXAMEN = {
    "laboratorio": "Examen de Laboratorio",
    "radiografia": "Radiografía (Rayos X)",
    "ecografia": "Ecografía / Ultrasonido",
    "cardiologia": "Reporte Cardiológico",
    "otro": "Otra Ayuda Diagnóstica",
}

ESTADOS_EXAMEN = {
    "solicitado": "Solicitado",
    "en_proceso": "En proceso",
    "con_resultado": "Con resultado",
}


class ExamenLaboratorio(BaseModel):
    __tablename__ = "examenes_laboratorio"
    __table_args__ = (
        db.Index("ix_examenes_laboratorio_estado", "estado"),
        db.Index("ix_examenes_laboratorio_categoria", "categoria"),
    )

    id = db.Column(db.Integer, primary_key=True)
    mascota_id = db.Column(db.Integer, db.ForeignKey("mascotas.id"), nullable=False, index=True)
    consulta_id = db.Column(db.Integer, db.ForeignKey("consultas_medicas.id"))
    solicitado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))

    categoria = db.Column(db.String(50), default="laboratorio", nullable=False)
    tipo_examen = db.Column(db.String(150), nullable=False)
    fecha_toma = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)
    laboratorio_externo = db.Column(db.String(150))
    archivo_resultado = db.Column(db.String(255))
    interpretacion = db.Column(db.Text)
    estado = db.Column(db.String(20), nullable=False, default="solicitado")

    fecha_registro = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)

    mascota = db.relationship("Mascota")
    consulta = db.relationship("ConsultaMedica")
    solicitado_por = db.relationship("Usuario", foreign_keys=[solicitado_por_id])

    @validates("estado")
    def _validar_estado(self, _clave, valor):
        valor = valor or "solicitado"
        if valor not in ESTADOS_EXAMEN:
            raise ValueError(f"Estado de examen inválido: {valor!r}")
        return valor

    @property
    def estado_etiqueta(self):
        return ESTADOS_EXAMEN.get(self.estado, self.estado)

    @property
    def categoria_etiqueta(self):
        return CATEGORIAS_EXAMEN.get(self.categoria or "laboratorio", "Examen")

    @property
    def icono_categoria(self):
        cat = self.categoria or "laboratorio"
        if cat == "radiografia":
            return "bi-film"
        elif cat == "ecografia":
            return "bi-soundwave"
        elif cat == "cardiologia":
            return "bi-heart-pulse"
        elif cat == "laboratorio":
            return "bi-clipboard2-pulse"
        return "bi-file-earmark-medical"

    @property
    def color_categoria(self):
        cat = self.categoria or "laboratorio"
        if cat == "radiografia":
            return "warning"
        elif cat == "ecografia":
            return "info"
        elif cat == "cardiologia":
            return "danger"
        elif cat == "laboratorio":
            return "primary"
        return "secondary"

    @property
    def es_imagen(self) -> bool:
        if not self.archivo_resultado:
            return False
        ext = self.archivo_resultado.rsplit(".", 1)[-1].lower() if "." in self.archivo_resultado else ""
        return ext in ("jpg", "jpeg", "png", "webp", "gif")

    @property
    def es_pdf(self) -> bool:
        if not self.archivo_resultado:
            return False
        return self.archivo_resultado.lower().endswith(".pdf")

    def __repr__(self):
        return f"<ExamenLaboratorio {self.id} {self.tipo_examen!r} categoria={self.categoria} estado={self.estado}>"


# ---------------------------------------------------------------------------
# Gastos
# ---------------------------------------------------------------------------

TIPOS_GASTO = {"diario": "Gasto diario", "indirecto": "Costo indirecto"}
CATEGORIAS_GASTO = {
    "arriendo": "Arriendo",
    "servicios_publicos": "Servicios públicos",
    "nomina": "Nómina",
    "insumos": "Insumos",
    "mantenimiento": "Mantenimiento",
    "transporte": "Transporte",
    "marketing": "Marketing",
    "impuestos": "Impuestos",
    "otro": "Otro",
}


class Gasto(BaseModel):
    __tablename__ = "gastos"
    __table_args__ = (db.Index("ix_gastos_fecha", "fecha_gasto"),)

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    tipo_gasto = db.Column(db.String(20), nullable=False, default="diario")
    categoria = db.Column(db.String(30), nullable=False, default="otro")
    descripcion = db.Column(db.String(255), nullable=False)
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    fecha_gasto = db.Column(db.Date, nullable=False, default=hoy_bogota)
    comprobante = db.Column(db.String(255))

    fecha_registro = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)

    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])

    @validates("tipo_gasto")
    def _validar_tipo(self, _clave, valor):
        valor = valor or "diario"
        if valor not in TIPOS_GASTO:
            raise ValueError(f"Tipo de gasto inválido: {valor!r}")
        return valor

    @validates("categoria")
    def _validar_categoria(self, _clave, valor):
        valor = valor or "otro"
        if valor not in CATEGORIAS_GASTO:
            raise ValueError(f"Categoría de gasto inválida: {valor!r}")
        return valor

    @property
    def categoria_etiqueta(self):
        return CATEGORIAS_GASTO.get(self.categoria, self.categoria)

    @property
    def tipo_etiqueta(self):
        return TIPOS_GASTO.get(self.tipo_gasto, self.tipo_gasto)

    def __repr__(self):
        return f"<Gasto {self.id} {self.descripcion!r} {self.monto}>"


# ---------------------------------------------------------------------------
# Compras a crédito a proveedores
# ---------------------------------------------------------------------------

ESTADOS_FACTURA_PROVEEDOR = {"pendiente": "Pendiente", "pagada": "Pagada", "vencida": "Vencida", "anulada": "Anulada"}


class FacturaProveedor(BaseModel):
    __tablename__ = "facturas_proveedor"
    __table_args__ = (db.Index("ix_facturas_proveedor_estado", "estado"),)

    id = db.Column(db.Integer, primary_key=True)
    proveedor_id = db.Column(db.Integer, db.ForeignKey("proveedores.id"), nullable=False, index=True)
    numero_factura = db.Column(db.String(60), nullable=False)
    fecha_factura = db.Column(db.Date, nullable=False, default=hoy_bogota)
    fecha_vencimiento = db.Column(db.Date)
    monto_total = db.Column(db.Numeric(12, 2), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default="pendiente")
    notas = db.Column(db.Text)
    archivo = db.Column(db.String(255))

    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    fecha_registro = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)

    proveedor = db.relationship("Proveedor")
    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])
    pagos = db.relationship(
        "PagoProveedor", back_populates="factura", order_by="PagoProveedor.fecha_pago", cascade="all, delete-orphan"
    )

    @validates("estado")
    def _validar_estado(self, _clave, valor):
        valor = valor or "pendiente"
        if valor not in ESTADOS_FACTURA_PROVEEDOR:
            raise ValueError(f"Estado de factura inválido: {valor!r}")
        return valor

    @property
    def estado_etiqueta(self):
        return ESTADOS_FACTURA_PROVEEDOR.get(self.estado, self.estado)

    @property
    def total_abonado(self):
        return sum((p.monto for p in self.pagos), Decimal("0.00"))

    @property
    def saldo_pendiente(self):
        return self.monto_total - self.total_abonado

    def __repr__(self):
        return f"<FacturaProveedor {self.id} {self.numero_factura} saldo={self.saldo_pendiente}>"


class PagoProveedor(BaseModel):
    __tablename__ = "pagos_proveedor"

    id = db.Column(db.Integer, primary_key=True)
    factura_id = db.Column(db.Integer, db.ForeignKey("facturas_proveedor.id"), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    metodo_pago = db.Column(db.String(30), nullable=False, default="transferencia")
    fecha_pago = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)
    notas = db.Column(db.Text)

    factura = db.relationship("FacturaProveedor", back_populates="pagos")
    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])

    def __repr__(self):
        return f"<PagoProveedor {self.id} factura={self.factura_id} monto={self.monto}>"


# ---------------------------------------------------------------------------
# Cartera de tutores con crédito
# ---------------------------------------------------------------------------

ESTADOS_FACTURA_TUTOR = {"pendiente": "Pendiente", "pagada": "Pagada", "anulada": "Anulada"}


class CuentaTutor(BaseModel):
    """Factura a crédito de un tutor (fía) con sus abonos. Distinta de una
    ``Venta`` de contado; se usa para clientes con crédito autorizado."""

    __tablename__ = "cuentas_tutor"
    __table_args__ = (db.Index("ix_cuentas_tutor_estado", "estado"),)

    id = db.Column(db.Integer, primary_key=True)
    tutor_id = db.Column(db.Integer, db.ForeignKey("tutores.id"), nullable=False, index=True)
    venta_id = db.Column(db.Integer, db.ForeignKey("ventas.id"))
    descripcion = db.Column(db.String(255), nullable=False)
    monto_total = db.Column(db.Numeric(12, 2), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default="pendiente")
    fecha_factura = db.Column(db.Date, nullable=False, default=hoy_bogota)
    fecha_vencimiento = db.Column(db.Date)

    creado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    fecha_registro = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)

    tutor = db.relationship("Tutor")
    venta = db.relationship("Venta")
    creado_por = db.relationship("Usuario", foreign_keys=[creado_por_id])
    abonos = db.relationship(
        "AbonoCuentaTutor", back_populates="cuenta", order_by="AbonoCuentaTutor.fecha_pago", cascade="all, delete-orphan"
    )

    @validates("estado")
    def _validar_estado(self, _clave, valor):
        valor = valor or "pendiente"
        if valor not in ESTADOS_FACTURA_TUTOR:
            raise ValueError(f"Estado de cuenta inválido: {valor!r}")
        return valor

    @property
    def estado_etiqueta(self):
        return ESTADOS_FACTURA_TUTOR.get(self.estado, self.estado)

    @property
    def total_abonado(self):
        return sum((a.monto for a in self.abonos), Decimal("0.00"))

    @property
    def saldo_pendiente(self):
        return self.monto_total - self.total_abonado

    def __repr__(self):
        return f"<CuentaTutor {self.id} tutor={self.tutor_id} saldo={self.saldo_pendiente}>"


class AbonoCuentaTutor(BaseModel):
    __tablename__ = "abonos_cuenta_tutor"

    id = db.Column(db.Integer, primary_key=True)
    cuenta_id = db.Column(db.Integer, db.ForeignKey("cuentas_tutor.id"), nullable=False, index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    metodo_pago = db.Column(db.String(30), nullable=False, default="efectivo")
    fecha_pago = db.Column(db.DateTime(timezone=True), nullable=False, default=obtener_hora_bogota)
    notas = db.Column(db.Text)

    cuenta = db.relationship("CuentaTutor", back_populates="abonos")
    usuario = db.relationship("Usuario", foreign_keys=[usuario_id])

    def __repr__(self):
        return f"<AbonoCuentaTutor {self.id} cuenta={self.cuenta_id} monto={self.monto}>"
