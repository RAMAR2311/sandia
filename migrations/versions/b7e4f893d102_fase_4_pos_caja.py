"""fase 4: pos_caja

Revision ID: b7e4f893d102
Revises: a6f3e792c901
Create Date: 2026-09-14 14:04:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7e4f893d102'
down_revision = 'a6f3e792c901'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Tabla turnos_caja
    op.create_table(
        'turnos_caja',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('monto_apertura', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('monto_cierre_esperado', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('monto_cierre_real', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('diferencia', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('estado', sa.String(length=20), nullable=False),
        sa.Column('fecha_apertura', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fecha_cierre', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notas_apertura', sa.Text(), nullable=True),
        sa.Column('notas_cierre', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], name=op.f('fk_turnos_caja_usuario_id_usuarios')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_turnos_caja'))
    )
    op.create_index(op.f('ix_turnos_caja_usuario_id'), 'turnos_caja', ['usuario_id'], unique=False)

    # 2. Tabla ventas
    op.create_table(
        'ventas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('numero_factura', sa.String(length=40), nullable=False),
        sa.Column('turno_caja_id', sa.Integer(), nullable=False),
        sa.Column('tutor_id', sa.Integer(), nullable=True),
        sa.Column('mascota_id', sa.Integer(), nullable=True),
        sa.Column('usuario_id', sa.Integer(), nullable=False),
        sa.Column('subtotal', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('descuento_monto', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('impuesto_monto', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('total', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('estado', sa.String(length=20), nullable=False),
        sa.Column('motivo_anulacion', sa.Text(), nullable=True),
        sa.Column('anulada_por_id', sa.Integer(), nullable=True),
        sa.Column('fecha_venta', sa.DateTime(timezone=True), nullable=False),
        sa.Column('fecha_anulacion', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['anulada_por_id'], ['usuarios.id'], name=op.f('fk_ventas_anulada_por_id_usuarios')),
        sa.ForeignKeyConstraint(['mascota_id'], ['mascotas.id'], name=op.f('fk_ventas_mascota_id_mascotas')),
        sa.ForeignKeyConstraint(['turno_caja_id'], ['turnos_caja.id'], name=op.f('fk_ventas_turno_caja_id_turnos_caja')),
        sa.ForeignKeyConstraint(['tutor_id'], ['tutores.id'], name=op.f('fk_ventas_tutor_id_tutores')),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], name=op.f('fk_ventas_usuario_id_usuarios')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_ventas'))
    )
    op.create_index(op.f('ix_ventas_fecha'), 'ventas', ['fecha_venta'], unique=False)
    op.create_index(op.f('ix_ventas_numero_factura'), 'ventas', ['numero_factura'], unique=True)
    op.create_index(op.f('ix_ventas_turno_caja_id'), 'ventas', ['turno_caja_id'], unique=False)
    op.create_index(op.f('ix_ventas_tutor_id'), 'ventas', ['tutor_id'], unique=False)
    op.create_index(op.f('ix_ventas_mascota_id'), 'ventas', ['mascota_id'], unique=False)
    op.create_index(op.f('ix_ventas_usuario_id'), 'ventas', ['usuario_id'], unique=False)

    # 3. Tabla detalles_venta
    op.create_table(
        'detalles_venta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('venta_id', sa.Integer(), nullable=False),
        sa.Column('producto_id', sa.Integer(), nullable=True),
        sa.Column('variante_id', sa.Integer(), nullable=True),
        sa.Column('lote_id', sa.Integer(), nullable=True),
        sa.Column('descripcion', sa.String(length=180), nullable=False),
        sa.Column('tipo_item', sa.String(length=20), nullable=False),
        sa.Column('cantidad', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('precio_unitario', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('subtotal', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('descuento', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('total_linea', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.ForeignKeyConstraint(['lote_id'], ['lotes.id'], name=op.f('fk_detalles_venta_lote_id_lotes')),
        sa.ForeignKeyConstraint(['producto_id'], ['productos.id'], name=op.f('fk_detalles_venta_producto_id_productos')),
        sa.ForeignKeyConstraint(['variante_id'], ['variantes_producto.id'], name=op.f('fk_detalles_venta_variante_id_variantes_producto')),
        sa.ForeignKeyConstraint(['venta_id'], ['ventas.id'], name=op.f('fk_detalles_venta_venta_id_ventas')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_detalles_venta'))
    )
    op.create_index(op.f('ix_detalles_venta_venta_id'), 'detalles_venta', ['venta_id'], unique=False)

    # 4. Tabla pagos_venta
    op.create_table(
        'pagos_venta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('venta_id', sa.Integer(), nullable=False),
        sa.Column('metodo_pago', sa.String(length=30), nullable=False),
        sa.Column('monto', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('referencia_transaccion', sa.String(length=100), nullable=True),
        sa.Column('fecha_pago', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['venta_id'], ['ventas.id'], name=op.f('fk_pagos_venta_venta_id_ventas')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_pagos_venta'))
    )
    op.create_index(op.f('ix_pagos_venta_venta_id'), 'pagos_venta', ['venta_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_pagos_venta_venta_id'), table_name='pagos_venta')
    op.drop_table('pagos_venta')
    op.drop_index(op.f('ix_detalles_venta_venta_id'), table_name='detalles_venta')
    op.drop_table('detalles_venta')
    op.drop_index(op.f('ix_ventas_usuario_id'), table_name='ventas')
    op.drop_index(op.f('ix_ventas_mascota_id'), table_name='ventas')
    op.drop_index(op.f('ix_ventas_tutor_id'), table_name='ventas')
    op.drop_index(op.f('ix_ventas_turno_caja_id'), table_name='ventas')
    op.drop_index(op.f('ix_ventas_numero_factura'), table_name='ventas')
    op.drop_index(op.f('ix_ventas_fecha'), table_name='ventas')
    op.drop_table('ventas')
    op.drop_index(op.f('ix_turnos_caja_usuario_id'), table_name='turnos_caja')
    op.drop_table('turnos_caja')
