"""frecuencia_respiratoria_texto

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-18 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('consultas_medicas', schema=None) as batch_op:
        batch_op.alter_column(
            'frecuencia_respiratoria',
            existing_type=sa.Integer(),
            type_=sa.String(length=50),
            existing_nullable=True,
            postgresql_using='frecuencia_respiratoria::text'
        )

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if 'certificados_salud_animal' in tables:
        cols = [c['name'] for c in inspector.get_columns('certificados_salud_animal')]
        if 'frecuencia_respiratoria' in cols:
            with op.batch_alter_table('certificados_salud_animal', schema=None) as batch_op:
                batch_op.alter_column(
                    'frecuencia_respiratoria',
                    existing_type=sa.Integer(),
                    type_=sa.String(length=50),
                    existing_nullable=True,
                    postgresql_using='frecuencia_respiratoria::text'
                )


def downgrade():
    with op.batch_alter_table('consultas_medicas', schema=None) as batch_op:
        batch_op.alter_column(
            'frecuencia_respiratoria',
            existing_type=sa.String(length=50),
            type_=sa.Integer(),
            existing_nullable=True,
            postgresql_using='frecuencia_respiratoria::integer'
        )
