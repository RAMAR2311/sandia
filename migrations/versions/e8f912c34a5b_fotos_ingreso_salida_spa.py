"""fotos ingreso salida spa

Revision ID: e8f912c34a5b
Revises: b7e862d70a4e
Create Date: 2026-09-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e8f912c34a5b'
down_revision = 'b7e862d70a4e'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('citas_spa', sa.Column('foto_ingreso', sa.String(length=255), nullable=True))
    op.add_column('citas_spa', sa.Column('foto_salida', sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column('citas_spa', 'foto_salida')
    op.drop_column('citas_spa', 'foto_ingreso')
