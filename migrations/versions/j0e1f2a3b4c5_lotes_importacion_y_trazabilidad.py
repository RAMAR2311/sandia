"""lotes_importacion_y_trazabilidad

Revision ID: j0e1f2a3b4c5
Revises: i9d0e1f2a3b4
Create Date: 2026-09-30 11:55:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'j0e1f2a3b4c5'
down_revision = 'i9d0e1f2a3b4'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # 1. Tabla lotes_importacion
    if 'lotes_importacion' not in inspector.get_table_names():
        op.create_table(
            'lotes_importacion',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('uuid', sa.String(length=36), nullable=False),
            sa.Column('tipo', sa.String(length=30), nullable=False),
            sa.Column('nombre_archivo', sa.String(length=255), nullable=True),
            sa.Column('creados', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('actualizados', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('fecha', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column('usuario_id', sa.Integer(), nullable=True),
            sa.Column('revertido', sa.Boolean(), nullable=False, server_default=sa.text('false')),
            sa.Column('fecha_reversion', sa.DateTime(timezone=True), nullable=True),
            sa.Column('usuario_reversion_id', sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], name=op.f('fk_lotes_importacion_usuario_id_usuarios')),
            sa.ForeignKeyConstraint(['usuario_reversion_id'], ['usuarios.id'], name=op.f('fk_lotes_importacion_usuario_reversion_id_usuarios')),
            sa.PrimaryKeyConstraint('id', name=op.f('pk_lotes_importacion')),
            sa.UniqueConstraint('uuid', name=op.f('uq_lotes_importacion_uuid'))
        )
        op.create_index('ix_lotes_importacion_tipo', 'lotes_importacion', ['tipo'])
        op.create_index('ix_lotes_importacion_fecha', 'lotes_importacion', ['fecha'])

    # 2. Columnas en tutores
    columnas_tutores = [c['name'] for c in inspector.get_columns('tutores')]
    if 'lote_importacion' not in columnas_tutores:
        op.add_column('tutores', sa.Column('lote_importacion', sa.String(length=64), nullable=True))
        op.create_index('ix_tutores_lote_importacion', 'tutores', ['lote_importacion'])
    if 'id_externo' not in columnas_tutores:
        op.add_column('tutores', sa.Column('id_externo', sa.String(length=50), nullable=True))
        op.create_index('ix_tutores_id_externo', 'tutores', ['id_externo'])

    # 3. Columnas en mascotas
    columnas_mascotas = [c['name'] for c in inspector.get_columns('mascotas')]
    if 'lote_importacion' not in columnas_mascotas:
        op.add_column('mascotas', sa.Column('lote_importacion', sa.String(length=64), nullable=True))
        op.create_index('ix_mascotas_lote_importacion', 'mascotas', ['lote_importacion'])
    if 'id_externo' not in columnas_mascotas:
        op.add_column('mascotas', sa.Column('id_externo', sa.String(length=50), nullable=True))
        op.create_index('ix_mascotas_id_externo', 'mascotas', ['id_externo'])

    # 4. Columnas en consultas_medicas
    columnas_consultas = [c['name'] for c in inspector.get_columns('consultas_medicas')]
    if 'lote_importacion' not in columnas_consultas:
        op.add_column('consultas_medicas', sa.Column('lote_importacion', sa.String(length=64), nullable=True))
        op.create_index('ix_consultas_medicas_lote_importacion', 'consultas_medicas', ['lote_importacion'])


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    columnas_consultas = [c['name'] for c in inspector.get_columns('consultas_medicas')]
    if 'lote_importacion' in columnas_consultas:
        op.drop_index('ix_consultas_medicas_lote_importacion', table_name='consultas_medicas')
        op.drop_column('consultas_medicas', 'lote_importacion')

    columnas_mascotas = [c['name'] for c in inspector.get_columns('mascotas')]
    if 'id_externo' in columnas_mascotas:
        op.drop_index('ix_mascotas_id_externo', table_name='mascotas')
        op.drop_column('mascotas', 'id_externo')
    if 'lote_importacion' in columnas_mascotas:
        op.drop_index('ix_mascotas_lote_importacion', table_name='mascotas')
        op.drop_column('mascotas', 'lote_importacion')

    columnas_tutores = [c['name'] for c in inspector.get_columns('tutores')]
    if 'id_externo' in columnas_tutores:
        op.drop_index('ix_tutores_id_externo', table_name='tutores')
        op.drop_column('tutores', 'id_externo')
    if 'lote_importacion' in columnas_tutores:
        op.drop_index('ix_tutores_lote_importacion', table_name='tutores')
        op.drop_column('tutores', 'lote_importacion')

    if 'lotes_importacion' in inspector.get_table_names():
        op.drop_table('lotes_importacion')
