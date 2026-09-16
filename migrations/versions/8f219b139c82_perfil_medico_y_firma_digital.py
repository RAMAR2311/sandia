"""perfil_medico_y_firma_digital

Revision ID: 8f219b139c82
Revises: 37a89e12cb41
Create Date: 2026-09-16 16:55:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8f219b139c82'
down_revision = '37a89e12cb41'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('titulo_profesional', sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column('especialidad', sa.String(length=150), nullable=True))
        batch_op.add_column(sa.Column('firma_digital', sa.String(length=255), nullable=True))

    # Insertar configuraciones iniciales de la doctora principal si no existen
    configuracion_sistema = sa.table(
        'configuracion_sistema',
        sa.column('clave', sa.String),
        sa.column('valor', sa.Text),
        sa.column('tipo', sa.String),
        sa.column('descripcion', sa.String),
        sa.column('grupo', sa.String),
    )

    op.bulk_insert(
        configuracion_sistema,
        [
            {
                'clave': 'medico_principal_nombre',
                'valor': 'Dra. Daniela Pulido',
                'tipo': 'str',
                'descripcion': 'Nombre del médico veterinario principal',
                'grupo': 'medico',
            },
            {
                'clave': 'medico_principal_titulo',
                'valor': 'Médica veterinaria',
                'tipo': 'str',
                'descripcion': 'Título profesional (ej. Médica veterinaria)',
                'grupo': 'medico',
            },
            {
                'clave': 'medico_principal_tp',
                'valor': '53214',
                'tipo': 'str',
                'descripcion': 'Tarjeta profesional (T.P.)',
                'grupo': 'medico',
            },
            {
                'clave': 'medico_principal_especialidad',
                'valor': 'Dpl. Dermatología de pequeñas especies',
                'tipo': 'str',
                'descripcion': 'Especialidad / Diplomado',
                'grupo': 'medico',
            },
            {
                'clave': 'medico_principal_firma',
                'valor': '',
                'tipo': 'str',
                'descripcion': 'Nombre de archivo o firma digitalizada',
                'grupo': 'medico',
            },
        ],
    )


def downgrade():
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.drop_column('firma_digital')
        batch_op.drop_column('especialidad')
        batch_op.drop_column('titulo_profesional')

    op.execute(
        "DELETE FROM configuracion_sistema WHERE clave IN ("
        "'medico_principal_nombre', 'medico_principal_titulo', 'medico_principal_tp', "
        "'medico_principal_especialidad', 'medico_principal_firma')"
    )
