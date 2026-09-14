"""fase 1: usuarios, configuracion_sistema, intentos_login

Crea las tablas base y siembra la configuración inicial del sistema
(``descontar_stock_ventas`` y los datos de la clínica).

Revision ID: cdb9d2b36fb6
Revises:
Create Date: 2026-09-14 12:53:43.574352

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cdb9d2b36fb6'
down_revision = None
branch_labels = None
depends_on = None


# Copia literal de models.CONFIGURACION_INICIAL en el momento de esta migración.
# No se importa desde models.py a propósito: una migración debe seguir siendo
# reproducible aunque el modelo cambie en el futuro.
CONFIGURACION_INICIAL = [
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


def upgrade():
    op.create_table('intentos_login',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ip', sa.String(length=45), nullable=False),
    sa.Column('email', sa.String(length=120), nullable=True),
    sa.Column('exitoso', sa.Boolean(), nullable=False),
    sa.Column('fecha', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_intentos_login'))
    )
    op.create_index('ix_intentos_login_ip_fecha', 'intentos_login', ['ip', 'fecha'], unique=False)

    op.create_table('usuarios',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=120), nullable=False),
    sa.Column('email', sa.String(length=120), nullable=False),
    sa.Column('telefono', sa.String(length=20), nullable=True),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('rol', sa.String(length=20), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('fecha_registro', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ultimo_acceso', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_usuarios')),
    sa.UniqueConstraint('email', name=op.f('uq_usuarios_email'))
    )

    tabla_configuracion = op.create_table('configuracion_sistema',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('clave', sa.String(length=80), nullable=False),
    sa.Column('valor', sa.Text(), nullable=True),
    sa.Column('tipo', sa.String(length=10), nullable=False),
    sa.Column('descripcion', sa.String(length=255), nullable=True),
    sa.Column('grupo', sa.String(length=40), nullable=False),
    sa.Column('actualizado_por_id', sa.Integer(), nullable=True),
    sa.Column('fecha_actualizacion', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['actualizado_por_id'], ['usuarios.id'], name=op.f('fk_configuracion_sistema_actualizado_por_id_usuarios')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_configuracion_sistema')),
    sa.UniqueConstraint('clave', name=op.f('uq_configuracion_sistema_clave'))
    )

    # Siembra de la configuración inicial: debe existir desde la primera migración.
    op.bulk_insert(
        tabla_configuracion,
        [
            {"clave": clave, "valor": valor, "tipo": tipo, "descripcion": descripcion, "grupo": grupo}
            for clave, valor, tipo, descripcion, grupo in CONFIGURACION_INICIAL
        ],
    )


def downgrade():
    op.drop_table('configuracion_sistema')
    op.drop_table('usuarios')
    op.drop_index('ix_intentos_login_ip_fecha', table_name='intentos_login')
    op.drop_table('intentos_login')
