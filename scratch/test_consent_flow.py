"""Script de verificación para el módulo de consentimientos informados."""
import json
from app import create_app
from models import db, Usuario, Tutor, Mascota, PlantillaConsentimiento, ConsentimientoEmitido, FirmaConsentimiento
from sqlalchemy import select

app = create_app()

with app.app_context():
    print("--- Verificando Plantillas ---")
    plantillas = db.session.execute(select(PlantillaConsentimiento)).scalars().all()
    print(f"Total plantillas encontradas: {len(plantillas)}")
    for p in plantillas:
        print(f" - {p.codigo}: {p.titulo} ({p.tipo})")
    assert len(plantillas) >= 5, "Deben existir al menos 5 plantillas base"

    print("\n--- Verificando o Creando Tutor y Mascota de Prueba ---")
    tutor = db.session.execute(select(Tutor).filter_by(numero_documento="1098765432")).scalar_one_or_none()
    if not tutor:
        tutor = Tutor(
            nombre_completo="María Camila Restrepo",
            tipo_documento="CC",
            numero_documento="1098765432",
            telefono="3104445566",
            email="maria.camila@ejemplo.com",
            direccion="Carrera 15 # 45-67",
        )
        db.session.add(tutor)
        db.session.flush()

    mascota = db.session.execute(select(Mascota).filter_by(nombre="Lucas", tutor_id=tutor.id)).scalar_one_or_none()
    if not mascota:
        mascota = Mascota(
            tutor_id=tutor.id,
            nombre="Lucas",
            especie="canino",
            sexo="macho",
            microchip="981098123456789",
        )
        db.session.add(mascota)
        db.session.flush()

    vet = db.session.execute(select(Usuario).filter_by(rol="admin")).scalars().first()
    if not vet:
        vet = db.session.execute(select(Usuario)).scalars().first()

    db.session.commit()
    print(f"Tutor: {tutor.nombre_completo} (ID: {tutor.id})")
    print(f"Mascota: {mascota.nombre} (ID: {mascota.id})")
    print(f"Veterinario: {vet.nombre if vet else 'Sin vet'} (ID: {vet.id if vet else None})")

    print("\n--- Probando Emisión y Sustitución de Variables ---")
    from routes.consentimientos import renderizar_variables_consentimiento
    plantilla_qx = db.session.execute(select(PlantillaConsentimiento).filter_by(codigo="QUIRURGICO_V1")).scalar_one()
    texto_renderizado = renderizar_variables_consentimiento(
        texto_template=plantilla_qx.contenido_template,
        mascota=mascota,
        tutor=tutor,
        vet=vet,
        diagnostico="Profilaxis dental ultrasónica con exodoncia simple",
    )
    print("Muestra del texto inyectado:")
    print("--------------------------------------------------")
    print("\n".join(texto_renderizado.splitlines()[:12]))
    print("--------------------------------------------------")
    assert "María Camila Restrepo" in texto_renderizado
    assert "Lucas" in texto_renderizado
    assert "Profilaxis dental" in texto_renderizado

    print("\n--- Probando Creación de ConsentimientoEmitido ---")
    consentimiento = ConsentimientoEmitido(
        plantilla_id=plantilla_qx.id,
        mascota_id=mascota.id,
        tutor_id=tutor.id,
        veterinario_id=vet.id,
        tipo=plantilla_qx.tipo,
        titulo=plantilla_qx.titulo,
        contenido_final=texto_renderizado,
        diagnostico_motivo="Profilaxis dental ultrasónica",
        estado="pendiente_firma",
    )
    db.session.add(consentimiento)
    db.session.commit()

    print(f"Consentimiento creado ID: {consentimiento.id}, Token: {consentimiento.token_publico}")
    print(f"URL Firma: {consentimiento.url_firma_publica()}")
    print(f"URL Documento: {consentimiento.url_documento()}")
    print(f"WhatsApp link: {consentimiento.enlace_whatsapp()[:80]}...")

    print("\n--- Probando Firma Digital y Sellado Criptográfico ---")
    hash_sha256 = consentimiento.calcular_hash_integridad()
    firma = FirmaConsentimiento(
        consentimiento_id=consentimiento.id,
        nombre_firmante=tutor.nombre_completo,
        documento_firmante=tutor.numero_documento,
        trazo_firma_png="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
        ip_origen="127.0.0.1",
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        canal_firma="presencial_tablet",
        hash_documento_sha256=hash_sha256,
    )
    consentimiento.estado = "firmado"
    db.session.add(firma)
    db.session.commit()

    print(f"Estado tras firmar: {consentimiento.estado}")
    print(f"Esta firmado: {consentimiento.esta_firmado}")
    print(f"Firma registrada por: {consentimiento.firma.nombre_firmante}")
    print(f"Hash SHA-256: {consentimiento.firma.hash_documento_sha256}")

    print("\n>>> ¡TODAS LAS PRUEBAS DEL FLUJO PASARON EXITOSAMENTE! <<<")
