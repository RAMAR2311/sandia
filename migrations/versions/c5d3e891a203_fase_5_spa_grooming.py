"""fase 5: spa_grooming

Revision ID: c5d3e891a203
Revises: b7e4f893d102
Create Date: 2026-09-14 14:10:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c5d3e891a203'
down_revision = 'b7e4f893d102'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Tabla servicios_spa
    op.create_table(
        'servicios_spa',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nombre', sa.String(length=120), nullable=False),
        sa.Column('descripcion', sa.Text(), nullable=True),
        sa.Column('duracion_minutos', sa.Integer(), nullable=False),
        sa.Column('precio_sugerido', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('especie', sa.String(length=20), nullable=True),
        sa.Column('tamano_mascota', sa.String(length=20), nullable=True),
        sa.Column('activo', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_servicios_spa'))
    )

    # 2. Tabla citas_spa
    op.create_table(
        'citas_spa',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mascota_id', sa.Integer(), nullable=False),
        sa.Column('tutor_id', sa.Integer(), nullable=False),
        sa.Column('groomer_id', sa.Integer(), nullable=True),
        sa.Column('servicio_spa_id', sa.Integer(), nullable=False),
        sa.Column('fecha_hora', sa.DateTime(timezone=True), nullable=False),
        sa.Column('duracion_minutos', sa.Integer(), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False),
        sa.Column('notas_ingreso', sa.Text(), nullable=True),
        sa.Column('notas_salida', sa.Text(), nullable=True),
        sa.Column('notificado_whatsapp', sa.Boolean(), nullable=False),
        sa.Column('fecha_listo', sa.DateTime(timezone=True), nullable=True),
        sa.Column('venta_id', sa.Integer(), nullable=True),
        sa.Column('creado_por_id', sa.Integer(), nullable=True),
        sa.Column('fecha_registro', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['creado_por_id'], ['usuarios.id'], name=op.f('fk_citas_spa_creado_por_id_usuarios')),
        sa.ForeignKeyConstraint(['groomer_id'], ['usuarios.id'], name=op.f('fk_citas_spa_groomer_id_usuarios')),
        sa.ForeignKeyConstraint(['mascota_id'], ['mascotas.id'], name=op.f('fk_citas_spa_mascota_id_mascotas')),
        sa.ForeignKeyConstraint(['servicio_spa_id'], ['servicios_spa.id'], name=op.f('fk_citas_spa_servicio_spa_id_servicios_spa')),
        sa.ForeignKeyConstraint(['tutor_id'], ['tutores.id'], name=op.f('fk_citas_spa_tutor_id_tutores')),
        sa.ForeignKeyConstraint(['venta_id'], ['ventas.id'], name=op.f('fk_citas_spa_venta_id_ventas')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_citas_spa'))
    )
    op.create_index(op.f('ix_citas_spa_estado'), 'citas_spa', ['estado'], unique=False)
    op.create_index(op.f('ix_citas_spa_fecha'), 'citas_spa', ['fecha_hora'], unique=False)
    op.create_index(op.f('ix_citas_spa_groomer_id'), 'citas_spa', ['groomer_id'], unique=False)
    op.create_index(op.f('ix_citas_spa_mascota_id'), 'citas_spa', ['mascota_id'], unique=False)
    op.create_index(op.f('ix_citas_spa_tutor_id'), 'citas_spa', ['tutor_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_citas_spa_tutor_id'), table_name='citas_spa')
    op.drop_index(op.f('ix_citas_spa_mascota_id'), table_name='citas_spa')
    op.drop_index(op.f('ix_citas_spa_groomer_id'), table_name='citas_spa')
    op.drop_index(op.f('ix_citas_spa_fecha'), table_name='citas_spa')
    op.drop_index(op.f('ix_citas_spa_estado'), table_name='citas_spa')
    op.drop_table('citas_spa')
    op.drop_table('servicios_spa')
