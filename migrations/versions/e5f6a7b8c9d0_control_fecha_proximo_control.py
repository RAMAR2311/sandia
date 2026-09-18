"""control_fecha_proximo_control

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-18 14:25:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('controles_medicos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('fecha_proximo_control', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table('controles_medicos', schema=None) as batch_op:
        batch_op.drop_column('fecha_proximo_control')
