"""consulta_preventivo_alimentacion

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-18 13:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('consultas_medicas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('alimentacion', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('desparasitacion_producto', sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column('desparasitacion_fecha', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('vacunacion_producto', sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column('vacunacion_fecha', sa.Date(), nullable=True))


def downgrade():
    with op.batch_alter_table('consultas_medicas', schema=None) as batch_op:
        batch_op.drop_column('vacunacion_fecha')
        batch_op.drop_column('vacunacion_producto')
        batch_op.drop_column('desparasitacion_fecha')
        batch_op.drop_column('desparasitacion_producto')
        batch_op.drop_column('alimentacion')
