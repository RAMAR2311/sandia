"""fase 2: razas, tutores, mascotas, registros_peso

Crea el catálogo de razas (con siembra inicial por especie), los tutores, las
mascotas y los registros de peso.

Revision ID: 510bde3a0636
Revises: cdb9d2b36fb6
Create Date: 2026-09-14 13:25:32.314207

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '510bde3a0636'
down_revision = 'cdb9d2b36fb6'
branch_labels = None
depends_on = None


# Catálogo inicial de razas por especie (editable luego desde /admin/razas).
RAZAS_INICIALES = {
    "canino": [
        "Criollo / Mestizo", "Labrador Retriever", "Golden Retriever", "Pastor Alemán", "French Poodle",
        "Schnauzer", "Bulldog Francés", "Bulldog Inglés", "Beagle", "Pitbull", "Husky Siberiano",
        "Shih Tzu", "Yorkshire Terrier", "Pinscher", "Chihuahua", "Pug", "Cocker Spaniel",
        "Dachshund (Salchicha)", "Border Collie", "Boxer", "Rottweiler", "Pomerania", "Bichón Frisé",
        "Maltés", "Basset Hound", "Dálmata", "Doberman", "Gran Danés", "San Bernardo", "Akita",
        "Shar Pei", "Bull Terrier", "Jack Russell Terrier", "Pastor Belga", "Samoyedo",
        "Pastor Australiano", "Weimaraner", "Cane Corso", "Bernés de la Montaña", "Chow Chow", "Terranova",
    ],
    "felino": [
        "Criollo / Mestizo", "Persa", "Siamés", "Angora", "Bengalí", "Maine Coon", "Sphynx", "Ragdoll",
        "British Shorthair", "Azul Ruso", "Scottish Fold", "Himalayo", "Abisinio", "Bombay",
        "Exótico de pelo corto", "Siberiano", "Bosque de Noruega",
    ],
    "ave": [
        "Loro", "Periquito australiano", "Canario", "Cacatúa", "Agapornis", "Ninfa (Cockatiel)",
        "Guacamaya", "Gallina", "Paloma", "Perico", "Pato", "Otra ave",
    ],
    "roedor": ["Hámster", "Cobayo (Cuy)", "Rata", "Ratón", "Chinchilla", "Jerbo", "Ardilla"],
    "otro": [
        "Conejo", "Hurón", "Tortuga", "Iguana", "Erizo", "Serpiente", "Pez", "Cerdo miniatura",
        "Caballo", "Otra especie",
    ],
}


def upgrade():
    tabla_razas = op.create_table('razas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('especie', sa.String(length=20), nullable=False),
    sa.Column('nombre', sa.String(length=80), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_razas')),
    sa.UniqueConstraint('especie', 'nombre', name='uq_razas_especie_nombre')
    )
    op.bulk_insert(
        tabla_razas,
        [
            {"especie": especie, "nombre": nombre, "activo": True}
            for especie, nombres in RAZAS_INICIALES.items()
            for nombre in nombres
        ],
    )
    op.create_table('tutores',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tipo_documento', sa.String(length=5), nullable=True),
    sa.Column('numero_documento', sa.String(length=30), nullable=True),
    sa.Column('nombre_completo', sa.String(length=150), nullable=False),
    sa.Column('nombre_busqueda', sa.String(length=150), nullable=False),
    sa.Column('telefono', sa.String(length=20), nullable=True),
    sa.Column('whatsapp', sa.String(length=20), nullable=True),
    sa.Column('email', sa.String(length=120), nullable=True),
    sa.Column('direccion', sa.String(length=200), nullable=True),
    sa.Column('barrio', sa.String(length=100), nullable=True),
    sa.Column('notas', sa.Text(), nullable=True),
    sa.Column('acepta_recordatorios', sa.Boolean(), nullable=False),
    sa.Column('creado_por_id', sa.Integer(), nullable=True),
    sa.Column('fecha_registro', sa.DateTime(timezone=True), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['creado_por_id'], ['usuarios.id'], name=op.f('fk_tutores_creado_por_id_usuarios')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_tutores'))
    )
    with op.batch_alter_table('tutores', schema=None) as batch_op:
        batch_op.create_index('ix_tutores_nombre_busqueda', ['nombre_busqueda'], unique=False)
        batch_op.create_index('ix_tutores_numero_documento', ['numero_documento'], unique=True, postgresql_where=sa.text('numero_documento IS NOT NULL'))

    op.create_table('mascotas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tutor_id', sa.Integer(), nullable=False),
    sa.Column('nombre', sa.String(length=80), nullable=False),
    sa.Column('nombre_busqueda', sa.String(length=80), nullable=False),
    sa.Column('especie', sa.String(length=20), nullable=False),
    sa.Column('raza_id', sa.Integer(), nullable=True),
    sa.Column('sexo', sa.String(length=12), nullable=False),
    sa.Column('fecha_nacimiento', sa.Date(), nullable=True),
    sa.Column('fecha_nacimiento_estimada', sa.Boolean(), nullable=False),
    sa.Column('color', sa.String(length=60), nullable=True),
    sa.Column('senas_particulares', sa.Text(), nullable=True),
    sa.Column('microchip', sa.String(length=30), nullable=True),
    sa.Column('esterilizado', sa.Boolean(), nullable=False),
    sa.Column('tamano', sa.String(length=10), nullable=True),
    sa.Column('alergias', sa.Text(), nullable=True),
    sa.Column('condiciones_preexistentes', sa.Text(), nullable=True),
    sa.Column('foto', sa.String(length=255), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('fallecido', sa.Boolean(), nullable=False),
    sa.Column('fecha_fallecimiento', sa.Date(), nullable=True),
    sa.Column('creado_por_id', sa.Integer(), nullable=True),
    sa.Column('fecha_registro', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['creado_por_id'], ['usuarios.id'], name=op.f('fk_mascotas_creado_por_id_usuarios')),
    sa.ForeignKeyConstraint(['raza_id'], ['razas.id'], name=op.f('fk_mascotas_raza_id_razas')),
    sa.ForeignKeyConstraint(['tutor_id'], ['tutores.id'], name=op.f('fk_mascotas_tutor_id_tutores')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_mascotas'))
    )
    with op.batch_alter_table('mascotas', schema=None) as batch_op:
        batch_op.create_index('ix_mascotas_microchip', ['microchip'], unique=True, postgresql_where=sa.text('microchip IS NOT NULL'))
        batch_op.create_index('ix_mascotas_nombre_busqueda', ['nombre_busqueda'], unique=False)
        batch_op.create_index(batch_op.f('ix_mascotas_tutor_id'), ['tutor_id'], unique=False)

    op.create_table('registros_peso',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('mascota_id', sa.Integer(), nullable=False),
    sa.Column('peso_kg', sa.Numeric(precision=6, scale=2), nullable=False),
    sa.Column('fecha', sa.DateTime(timezone=True), nullable=False),
    sa.Column('registrado_por_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['mascota_id'], ['mascotas.id'], name=op.f('fk_registros_peso_mascota_id_mascotas')),
    sa.ForeignKeyConstraint(['registrado_por_id'], ['usuarios.id'], name=op.f('fk_registros_peso_registrado_por_id_usuarios')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_registros_peso'))
    )
    with op.batch_alter_table('registros_peso', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_registros_peso_mascota_id'), ['mascota_id'], unique=False)



def downgrade():
    with op.batch_alter_table('registros_peso', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_registros_peso_mascota_id'))

    op.drop_table('registros_peso')
    with op.batch_alter_table('mascotas', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_mascotas_tutor_id'))
        batch_op.drop_index('ix_mascotas_nombre_busqueda')
        batch_op.drop_index('ix_mascotas_microchip', postgresql_where=sa.text('microchip IS NOT NULL'))

    op.drop_table('mascotas')
    with op.batch_alter_table('tutores', schema=None) as batch_op:
        batch_op.drop_index('ix_tutores_numero_documento', postgresql_where=sa.text('numero_documento IS NOT NULL'))
        batch_op.drop_index('ix_tutores_nombre_busqueda')

    op.drop_table('tutores')
    op.drop_table('razas')
