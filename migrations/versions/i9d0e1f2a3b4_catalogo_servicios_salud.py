"""catalogo_servicios_salud

Revision ID: i9d0e1f2a3b4
Revises: h8c9d0e1f2a3
Create Date: 2026-09-28 13:05:00.000000

"""
from datetime import datetime, timezone
from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column
from decimal import Decimal


# revision identifiers, used by Alembic.
revision = 'i9d0e1f2a3b4'
down_revision = 'h8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # 1. Crear tabla servicios_salud si no existe
    if 'servicios_salud' not in inspector.get_table_names():
        op.create_table(
            'servicios_salud',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('nombre', sa.String(length=120), nullable=False),
            sa.Column('categoria', sa.String(length=30), nullable=False, server_default='consulta'),
            sa.Column('descripcion', sa.Text(), nullable=True),
            sa.Column('duracion_minutos', sa.Integer(), nullable=False, server_default='30'),
            sa.Column('precio_sugerido', sa.Numeric(precision=12, scale=2), nullable=False, server_default='0.00'),
            sa.Column('especie', sa.String(length=20), nullable=True),
            sa.Column('activo', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('creado_por_id', sa.Integer(), nullable=True),
            sa.Column('fecha_registro', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(['creado_por_id'], ['usuarios.id'], name=op.f('fk_servicios_salud_creado_por_id_usuarios')),
            sa.PrimaryKeyConstraint('id', name=op.f('pk_servicios_salud'))
        )

        # Sembrar servicios médicos base iniciales
        servicios_salud_table = table(
            'servicios_salud',
            column('nombre', sa.String),
            column('categoria', sa.String),
            column('descripcion', sa.Text),
            column('duracion_minutos', sa.Integer),
            column('precio_sugerido', sa.Numeric),
            column('especie', sa.String),
            column('activo', sa.Boolean),
            column('fecha_registro', sa.DateTime),
        )

        ahora = datetime.now(timezone.utc)
        op.bulk_insert(
            servicios_salud_table,
            [
                {
                    'nombre': 'Consulta Médica General',
                    'categoria': 'consulta',
                    'descripcion': 'Evaluación clínica integral por sistemas (examen físico SOAP).',
                    'duracion_minutos': 30,
                    'precio_sugerido': Decimal('50000.00'),
                    'especie': None,
                    'activo': True,
                    'fecha_registro': ahora,
                },
                {
                    'nombre': 'Consulta Médica Especializada / Dermatología',
                    'categoria': 'consulta',
                    'descripcion': 'Evaluación con especialista en dermatología de pequeñas especies.',
                    'duracion_minutos': 45,
                    'precio_sugerido': Decimal('85000.00'),
                    'especie': None,
                    'activo': True,
                    'fecha_registro': ahora,
                },
                {
                    'nombre': 'Vacunación Canina (Pentavalente / Octavalente)',
                    'categoria': 'vacunacion',
                    'descripcion': 'Aplicación de biológico + valoración previa de temperatura y constantes.',
                    'duracion_minutos': 20,
                    'precio_sugerido': Decimal('60000.00'),
                    'especie': 'canino',
                    'activo': True,
                    'fecha_registro': ahora,
                },
                {
                    'nombre': 'Vacunación Felina (Triple Felina + Rabia)',
                    'categoria': 'vacunacion',
                    'descripcion': 'Inmunización felina completa con examen clínico previo.',
                    'duracion_minutos': 20,
                    'precio_sugerido': Decimal('65000.00'),
                    'especie': 'felino',
                    'activo': True,
                    'fecha_registro': ahora,
                },
                {
                    'nombre': 'Vacunación Antirrábica',
                    'categoria': 'vacunacion',
                    'descripcion': 'Dosis anual de vacuna contra la rabia con certificado.',
                    'duracion_minutos': 15,
                    'precio_sugerido': Decimal('35000.00'),
                    'especie': None,
                    'activo': True,
                    'fecha_registro': ahora,
                },
                {
                    'nombre': 'Desparasitación Interna & Externa',
                    'categoria': 'desparasitacion',
                    'descripcion': 'Dosificación según peso y control de endo y ectoparásitos.',
                    'duracion_minutos': 15,
                    'precio_sugerido': Decimal('25000.00'),
                    'especie': None,
                    'activo': True,
                    'fecha_registro': ahora,
                },
                {
                    'nombre': 'Profilaxis Dental Canina / Felina',
                    'categoria': 'procedimiento',
                    'descripcion': 'Limpieza y destartraje ultrasónico de sarro dental bajo sedación.',
                    'duracion_minutos': 60,
                    'precio_sugerido': Decimal('140000.00'),
                    'especie': None,
                    'activo': True,
                    'fecha_registro': ahora,
                },
                {
                    'nombre': 'Ecografía Abdominal Completa',
                    'categoria': 'imagenologia',
                    'descripcion': 'Estudio ecográfico de cavidad abdominal con informe digital.',
                    'duracion_minutos': 40,
                    'precio_sugerido': Decimal('95000.00'),
                    'especie': None,
                    'activo': True,
                    'fecha_registro': ahora,
                },
                {
                    'nombre': 'Cuadro Hemático Completo + Química Sanguínea',
                    'categoria': 'laboratorio',
                    'descripcion': 'Toma de muestra y procesamiento de panel sanguíneo completo.',
                    'duracion_minutos': 20,
                    'precio_sugerido': Decimal('75000.00'),
                    'especie': None,
                    'activo': True,
                    'fecha_registro': ahora,
                },
                {
                    'nombre': 'Control Médico Post-Consulta (Seguimiento)',
                    'categoria': 'control',
                    'descripcion': 'Revisión y seguimiento terapéutico a los 8-15 días.',
                    'duracion_minutos': 20,
                    'precio_sugerido': Decimal('25000.00'),
                    'especie': None,
                    'activo': True,
                    'fecha_registro': ahora,
                },
            ]
        )

    # 2. Agregar servicio_salud_id a citas si no existe
    columnas_citas = [c['name'] for c in inspector.get_columns('citas')]
    if 'servicio_salud_id' not in columnas_citas:
        with op.batch_alter_table('citas', schema=None) as batch_op:
            batch_op.add_column(sa.Column('servicio_salud_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                batch_op.f('fk_citas_servicio_salud_id_servicios_salud'),
                'servicios_salud',
                ['servicio_salud_id'],
                ['id']
            )


def downgrade():
    with op.batch_alter_table('citas', schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f('fk_citas_servicio_salud_id_servicios_salud'), type_='foreignkey')
        batch_op.drop_column('servicio_salud_id')

    op.drop_table('servicios_salud')
