"""fase 3: inventario, proveedores, productos, variantes, lotes, movimientos_stock

Revision ID: a6f3e792c901
Revises: 510bde3a0636
Create Date: 2026-09-14 13:51:30.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a6f3e792c901'
down_revision = '510bde3a0636'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Proveedores
    op.create_table('proveedores',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nit', sa.String(length=30), nullable=True),
    sa.Column('nombre', sa.String(length=120), nullable=False),
    sa.Column('nombre_busqueda', sa.String(length=120), nullable=False),
    sa.Column('contacto', sa.String(length=100), nullable=True),
    sa.Column('telefono', sa.String(length=20), nullable=True),
    sa.Column('email', sa.String(length=120), nullable=True),
    sa.Column('direccion', sa.String(length=200), nullable=True),
    sa.Column('ciudad', sa.String(length=80), nullable=True),
    sa.Column('notas', sa.Text(), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('fecha_registro', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_proveedores'))
    )

    # 2. Productos
    op.create_table('productos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('sku', sa.String(length=40), nullable=False),
    sa.Column('codigo_barras', sa.String(length=50), nullable=True),
    sa.Column('nombre', sa.String(length=150), nullable=False),
    sa.Column('nombre_busqueda', sa.String(length=150), nullable=False),
    sa.Column('descripcion', sa.Text(), nullable=True),
    sa.Column('categoria', sa.String(length=30), nullable=False),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('requiere_receta', sa.Boolean(), nullable=False),
    sa.Column('unidad_medida', sa.String(length=30), nullable=False),
    sa.Column('precio_costo', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('precio_minimo', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('precio_sugerido', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('cantidad_stock', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('stock_minimo', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('imagen', sa.String(length=255), nullable=True),
    sa.Column('proveedor_id', sa.Integer(), nullable=True),
    sa.Column('controla_lote', sa.Boolean(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('creado_por_id', sa.Integer(), nullable=True),
    sa.Column('fecha_registro', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['creado_por_id'], ['usuarios.id'], name=op.f('fk_productos_creado_por_id_usuarios')),
    sa.ForeignKeyConstraint(['proveedor_id'], ['proveedores.id'], name=op.f('fk_productos_proveedor_id_proveedores')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_productos'))
    )
    with op.batch_alter_table('productos', schema=None) as batch_op:
        batch_op.create_index('ix_productos_sku', ['sku'], unique=True)
        batch_op.create_index('ix_productos_codigo_barras', ['codigo_barras'], unique=True, postgresql_where=sa.text('codigo_barras IS NOT NULL'))
        batch_op.create_index('ix_productos_nombre_busqueda', ['nombre_busqueda'], unique=False)

    # 3. Variantes
    op.create_table('variantes_producto',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('producto_id', sa.Integer(), nullable=False),
    sa.Column('nombre_variante', sa.String(length=100), nullable=False),
    sa.Column('sku', sa.String(length=40), nullable=True),
    sa.Column('codigo_barras', sa.String(length=50), nullable=True),
    sa.Column('precio_costo', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('precio_minimo', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('precio_sugerido', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('cantidad_stock', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('stock_minimo', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['producto_id'], ['productos.id'], name=op.f('fk_variantes_producto_producto_id_productos')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_variantes_producto'))
    )
    with op.batch_alter_table('variantes_producto', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_variantes_producto_producto_id'), ['producto_id'], unique=False)
        batch_op.create_index('ix_variantes_sku', ['sku'], unique=True, postgresql_where=sa.text('sku IS NOT NULL'))
        batch_op.create_index('ix_variantes_codigo_barras', ['codigo_barras'], unique=True, postgresql_where=sa.text('codigo_barras IS NOT NULL'))

    # 4. Lotes
    op.create_table('lotes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('producto_id', sa.Integer(), nullable=False),
    sa.Column('variante_id', sa.Integer(), nullable=True),
    sa.Column('numero_lote', sa.String(length=60), nullable=False),
    sa.Column('fecha_vencimiento', sa.Date(), nullable=False),
    sa.Column('cantidad_inicial', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('cantidad_disponible', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('proveedor_id', sa.Integer(), nullable=True),
    sa.Column('creado_por_id', sa.Integer(), nullable=True),
    sa.Column('fecha_ingreso', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['creado_por_id'], ['usuarios.id'], name=op.f('fk_lotes_creado_por_id_usuarios')),
    sa.ForeignKeyConstraint(['producto_id'], ['productos.id'], name=op.f('fk_lotes_producto_id_productos')),
    sa.ForeignKeyConstraint(['proveedor_id'], ['proveedores.id'], name=op.f('fk_lotes_proveedor_id_proveedores')),
    sa.ForeignKeyConstraint(['variante_id'], ['variantes_producto.id'], name=op.f('fk_lotes_variante_id_variantes_producto')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_lotes'))
    )
    with op.batch_alter_table('lotes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_lotes_producto_id'), ['producto_id'], unique=False)
        batch_op.create_index('ix_lotes_producto_vencimiento', ['producto_id', 'fecha_vencimiento'], unique=False)

    # 5. Movimientos Stock (Kardex)
    op.create_table('movimientos_stock',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('producto_id', sa.Integer(), nullable=False),
    sa.Column('variante_id', sa.Integer(), nullable=True),
    sa.Column('lote_id', sa.Integer(), nullable=True),
    sa.Column('usuario_id', sa.Integer(), nullable=False),
    sa.Column('tipo_movimiento', sa.String(length=30), nullable=False),
    sa.Column('cantidad', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('stock_anterior', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('stock_nuevo', sa.Numeric(precision=12, scale=2), nullable=False),
    sa.Column('motivo', sa.Text(), nullable=True),
    sa.Column('referencia', sa.String(length=100), nullable=True),
    sa.Column('fecha', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['lote_id'], ['lotes.id'], name=op.f('fk_movimientos_stock_lote_id_lotes')),
    sa.ForeignKeyConstraint(['producto_id'], ['productos.id'], name=op.f('fk_movimientos_stock_producto_id_productos')),
    sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], name=op.f('fk_movimientos_stock_usuario_id_usuarios')),
    sa.ForeignKeyConstraint(['variante_id'], ['variantes_producto.id'], name=op.f('fk_movimientos_stock_variante_id_variantes_producto')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_movimientos_stock'))
    )
    with op.batch_alter_table('movimientos_stock', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_movimientos_stock_producto_id'), ['producto_id'], unique=False)
        batch_op.create_index('ix_movimientos_producto_fecha', ['producto_id', 'fecha'], unique=False)


def downgrade():
    with op.batch_alter_table('movimientos_stock', schema=None) as batch_op:
        batch_op.drop_index('ix_movimientos_producto_fecha')
        batch_op.drop_index(batch_op.f('ix_movimientos_stock_producto_id'))
    op.drop_table('movimientos_stock')

    with op.batch_alter_table('lotes', schema=None) as batch_op:
        batch_op.drop_index('ix_lotes_producto_vencimiento')
        batch_op.drop_index(batch_op.f('ix_lotes_producto_id'))
    op.drop_table('lotes')

    with op.batch_alter_table('variantes_producto', schema=None) as batch_op:
        batch_op.drop_index('ix_variantes_codigo_barras', postgresql_where=sa.text('codigo_barras IS NOT NULL'))
        batch_op.drop_index('ix_variantes_sku', postgresql_where=sa.text('sku IS NOT NULL'))
        batch_op.drop_index(batch_op.f('ix_variantes_producto_producto_id'))
    op.drop_table('variantes_producto')

    with op.batch_alter_table('productos', schema=None) as batch_op:
        batch_op.drop_index('ix_productos_nombre_busqueda')
        batch_op.drop_index('ix_productos_codigo_barras', postgresql_where=sa.text('codigo_barras IS NOT NULL'))
        batch_op.drop_index('ix_productos_sku')
    op.drop_table('productos')

    op.drop_table('proveedores')
