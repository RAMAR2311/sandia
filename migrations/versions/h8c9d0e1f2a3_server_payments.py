"""server_payments

Revision ID: h8c9d0e1f2a3
Revises: g7b8c9d0e1f2
Create Date: 2026-09-20 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'h8c9d0e1f2a3'
down_revision = 'g7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'server_payments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('anio', sa.Integer(), nullable=False),
        sa.Column('mes', sa.Integer(), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False, server_default='pagado'),
        sa.Column('fecha_pago', sa.DateTime(timezone=True), nullable=False),
        sa.Column('observacion', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_server_payments')),
        sa.UniqueConstraint('anio', 'mes', name='uq_server_payments_anio_mes')
    )


def downgrade():
    op.drop_table('server_payments')
