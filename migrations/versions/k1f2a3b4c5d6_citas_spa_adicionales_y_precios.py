"""citas_spa_adicionales_y_precios

Revision ID: k1f2a3b4c5d6
Revises: j0e1f2a3b4c5
Create Date: 2026-10-03 18:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'k1f2a3b4c5d6'
down_revision = 'j0e1f2a3b4c5'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    columnas_citas_spa = [c['name'] for c in inspector.get_columns('citas_spa')]
    
    if 'precio_personalizado' not in columnas_citas_spa:
        op.add_column('citas_spa', sa.Column('precio_personalizado', sa.Numeric(10, 2), nullable=True))
        
    if 'recargo_adicional' not in columnas_citas_spa:
        op.add_column('citas_spa', sa.Column('recargo_adicional', sa.Numeric(10, 2), nullable=False, server_default='0.00'))
        
    if 'concepto_adicional' not in columnas_citas_spa:
        op.add_column('citas_spa', sa.Column('concepto_adicional', sa.String(length=255), nullable=True))
        
    if 'items_adicionales_json' not in columnas_citas_spa:
        op.add_column('citas_spa', sa.Column('items_adicionales_json', sa.Text(), nullable=True))


def downgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    columnas_citas_spa = [c['name'] for c in inspector.get_columns('citas_spa')]
    
    if 'items_adicionales_json' in columnas_citas_spa:
        op.drop_column('citas_spa', 'items_adicionales_json')
    if 'concepto_adicional' in columnas_citas_spa:
        op.drop_column('citas_spa', 'concepto_adicional')
    if 'recargo_adicional' in columnas_citas_spa:
        op.drop_column('citas_spa', 'recargo_adicional')
    if 'precio_personalizado' in columnas_citas_spa:
        op.drop_column('citas_spa', 'precio_personalizado')
