"""alimentacion_mascota

Revision ID: a1b2c3d4e5f6
Revises: 8f219b139c82
Create Date: 2026-09-18 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '8f219b139c82'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('mascotas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('alimentacion', sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table('mascotas', schema=None) as batch_op:
        batch_op.drop_column('alimentacion')
