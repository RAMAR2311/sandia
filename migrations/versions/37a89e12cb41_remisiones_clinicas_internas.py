"""remisiones_clinicas_internas

Revision ID: 37a89e12cb41
Revises: 12f952acface
Create Date: 2026-09-16 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '37a89e12cb41'
down_revision = '12f952acface'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'remisiones_internas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mascota_id', sa.Integer(), nullable=False),
        sa.Column('tutor_id', sa.Integer(), nullable=False),
        sa.Column('veterinario_id', sa.Integer(), nullable=False),
        sa.Column('creado_por_id', sa.Integer(), nullable=True),
        sa.Column('fecha_remision', sa.DateTime(timezone=True), nullable=False),
        sa.Column('dieta_marca_tipo', sa.String(length=255), nullable=True),
        sa.Column('antecedentes_cirugias', sa.Text(), nullable=True),
        sa.Column('antecedentes_enfermedades', sa.Text(), nullable=True),
        sa.Column('desparasitacion_interna_producto', sa.String(length=120), nullable=True),
        sa.Column('desparasitacion_interna_fecha', sa.Date(), nullable=True),
        sa.Column('desparasitacion_externa_producto', sa.String(length=120), nullable=True),
        sa.Column('desparasitacion_externa_fecha', sa.Date(), nullable=True),
        sa.Column('vacunacion_al_dia', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('vacunacion_ultima_fecha', sa.Date(), nullable=True),
        sa.Column('especialidad_destino', sa.String(length=150), nullable=False),
        sa.Column('centro_medico_destino', sa.String(length=180), nullable=True),
        sa.Column('motivo_remision', sa.Text(), nullable=False),
        sa.Column('observaciones_clinicas', sa.Text(), nullable=True),
        sa.Column('fecha_registro', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['creado_por_id'], ['usuarios.id'], name=op.f('fk_remisiones_internas_creado_por_id_usuarios'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['mascota_id'], ['mascotas.id'], name=op.f('fk_remisiones_internas_mascota_id_mascotas'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tutor_id'], ['tutores.id'], name=op.f('fk_remisiones_internas_tutor_id_tutores'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['veterinario_id'], ['usuarios.id'], name=op.f('fk_remisiones_internas_veterinario_id_usuarios'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_remisiones_internas'))
    )
    op.create_index('ix_remisiones_internas_mascota_fecha', 'remisiones_internas', ['mascota_id', 'fecha_remision'], unique=False)
    op.create_index(op.f('ix_remisiones_internas_mascota_id'), 'remisiones_internas', ['mascota_id'], unique=False)
    op.create_index(op.f('ix_remisiones_internas_tutor_id'), 'remisiones_internas', ['tutor_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_remisiones_internas_tutor_id'), table_name='remisiones_internas')
    op.drop_index(op.f('ix_remisiones_internas_mascota_id'), table_name='remisiones_internas')
    op.drop_index('ix_remisiones_internas_mascota_fecha', table_name='remisiones_internas')
    op.drop_table('remisiones_internas')
