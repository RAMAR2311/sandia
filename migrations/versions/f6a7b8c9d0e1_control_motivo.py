"""control_motivo

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-18 14:34:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('controles_medicos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('motivo', sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table('controles_medicos', schema=None) as batch_op:
        batch_op.drop_column('motivo')
