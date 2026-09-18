"""Agrega telefono_destino y direccion_destino a remisiones_internas

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-09-18 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'g7b8c9d0e1f2'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('remisiones_internas', sa.Column('telefono_destino', sa.String(length=50), nullable=True))
    op.add_column('remisiones_internas', sa.Column('direccion_destino', sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column('remisiones_internas', 'direccion_destino')
    op.drop_column('remisiones_internas', 'telefono_destino')
