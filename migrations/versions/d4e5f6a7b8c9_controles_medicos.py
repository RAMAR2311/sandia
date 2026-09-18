"""controles_medicos

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-18 14:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'controles_medicos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mascota_id', sa.Integer(), nullable=False),
        sa.Column('tutor_id', sa.Integer(), nullable=False),
        sa.Column('veterinario_id', sa.Integer(), nullable=False),
        sa.Column('consulta_origen_id', sa.Integer(), nullable=True),
        sa.Column('fecha_hora', sa.DateTime(timezone=True), nullable=False),
        sa.Column('peso_kg', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('temperatura_c', sa.Numeric(precision=4, scale=1), nullable=True),
        sa.Column('avances', sa.Text(), nullable=False),
        sa.Column('diagnostico', sa.Text(), nullable=True),
        sa.Column('plan_terapeutico', sa.Text(), nullable=False),
        sa.Column('medicamento', sa.Text(), nullable=True),
        sa.Column('observaciones', sa.Text(), nullable=True),
        sa.Column('creado_por_id', sa.Integer(), nullable=True),
        sa.Column('fecha_registro', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['consulta_origen_id'], ['consultas_medicas.id'], ),
        sa.ForeignKeyConstraint(['creado_por_id'], ['usuarios.id'], ),
        sa.ForeignKeyConstraint(['mascota_id'], ['mascotas.id'], ),
        sa.ForeignKeyConstraint(['tutor_id'], ['tutores.id'], ),
        sa.ForeignKeyConstraint(['veterinario_id'], ['usuarios.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('controles_medicos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_controles_medicos_consulta_origen_id'), ['consulta_origen_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_controles_medicos_mascota_id'), ['mascota_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_controles_medicos_tutor_id'), ['tutor_id'], unique=False)


def downgrade():
    with op.batch_alter_table('controles_medicos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_controles_medicos_tutor_id'))
        batch_op.drop_index(batch_op.f('ix_controles_medicos_mascota_id'))
        batch_op.drop_index(batch_op.f('ix_controles_medicos_consulta_origen_id'))

    op.drop_table('controles_medicos')
