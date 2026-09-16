"""Pruebas unitarias y de integración para el módulo de Consentimientos Informados Digitales."""

import json
from decimal import Decimal
import pytest
from sqlalchemy import select

from models import (
    ConsentimientoEmitido,
    FirmaConsentimiento,
    Mascota,
    PlantillaConsentimiento,
    Tutor,
    Usuario,
    db,
)
from tests.conftest import PASSWORD_PRUEBA


def iniciar_sesion(client, email="admin@prueba.local", password=PASSWORD_PRUEBA):
    res = client.get("/auth/login")
    import re
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', res.get_data(as_text=True))
    token = m.group(1) if m else ""
    return client.post(
        "/auth/login",
        data={"email": email, "password": password, "csrf_token": token},
        follow_redirects=True,
    )


def test_plantillas_base_existen(app):
    """Verifica que las 5 plantillas legales estándar estén disponibles."""
    with app.app_context():
        codigos = [
            "EUTANASIA_V1",
            "ANESTESIA_V1",
            "QUIRURGICO_V1",
            "HOSPITALIZACION_V1",
            "ALTA_VOLUNTARIA_V1",
        ]
        for c in codigos:
            p = db.session.execute(select(PlantillaConsentimiento).filter_by(codigo=c)).scalar_one_or_none()
            assert p is not None, f"Plantilla {c} no encontrada"
            assert p.activo is True
            assert "{{nombre_tutor}}" in p.contenido_template
            assert "{{nombre_paciente}}" in p.contenido_template


def test_flujo_completo_consentimiento_y_firma(client, admin, app):
    """Prueba el ciclo completo: preparar -> emitir -> firmar públicamente -> ver documento oficial."""
    iniciar_sesion(client)

    with app.app_context():
        tutor = Tutor(
            nombre_completo="Valentina Gómez Pérez",
            tipo_documento="CC",
            numero_documento="1122334455",
            telefono="3115550011",
            email="valentina@ejemplo.com",
            direccion="Calle 45 # 12-34",
        )
        db.session.add(tutor)
        db.session.flush()

        mascota = Mascota(
            tutor_id=tutor.id,
            nombre="Rocky",
            especie="canino",
            sexo="macho",
        )
        db.session.add(mascota)
        db.session.commit()
        mascota_id = mascota.id

    # 1. Preparar borrador vía AJAX
    res_prep = client.post(
        "/consentimientos/preparar",
        data=json.dumps({
            "mascota_id": mascota_id,
            "codigo_plantilla": "QUIRURGICO_V1",
            "diagnostico_motivo": "Castración profiláctica y limpieza dental",
        }),
        content_type="application/json",
    )
    assert res_prep.status_code == 200
    data_prep = res_prep.get_json()
    assert data_prep["success"] is True
    assert "Rocky" in data_prep["contenido"]
    assert "Valentina Gómez Pérez" in data_prep["contenido"]
    assert "Castración profiláctica" in data_prep["contenido"]

    # 2. Emitir consentimiento
    res_emitir = client.post(
        "/consentimientos/emitir",
        data=json.dumps({
            "mascota_id": mascota_id,
            "plantilla_id": data_prep["plantilla_id"],
            "tipo": data_prep["tipo"],
            "titulo": "Consentimiento para Castración",
            "contenido_final": data_prep["contenido"] + "\nNota extra: Paciente en ayuno confirmado.",
            "diagnostico_motivo": "Castración profiláctica",
        }),
        content_type="application/json",
    )
    assert res_emitir.status_code == 200
    data_emitir = res_emitir.get_json()
    assert data_emitir["success"] is True
    token = data_emitir["token_publico"]
    doc_id = data_emitir["consentimiento_id"]

    # 3. Acceso público a la vista de firma
    res_publica = client.get(f"/consentimientos/firmar/{token}")
    assert res_publica.status_code == 200
    assert "Castración profiláctica" in res_publica.get_data(as_text=True)
    assert "Firma Digital del Tutor" in res_publica.get_data(as_text=True)

    # 4. Enviar firma táctil (Base64 PNG de prueba)
    trazo_dummy = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    res_firma = client.post(
        f"/consentimientos/firmar/{token}/guardar",
        data=json.dumps({
            "firma_png": trazo_dummy,
            "nombre_firmante": "Valentina Gómez Pérez",
            "documento_firmante": "1122334455",
            "canal_firma": "remoto_whatsapp",
        }),
        content_type="application/json",
    )
    assert res_firma.status_code == 200
    data_firma = res_firma.get_json()
    assert data_firma["success"] is True

    # 5. Verificar que en la base de datos esté sellado y firmado
    with app.app_context():
        doc = db.session.execute(select(ConsentimientoEmitido).filter_by(id=doc_id)).scalar_one()
        assert doc.estado == "firmado"
        assert doc.esta_firmado is True
        assert doc.firma is not None
        assert doc.firma.nombre_firmante == "Valentina Gómez Pérez"
        assert len(doc.firma.hash_documento_sha256) == 64

    # 6. Vista del documento oficial membretado
    res_doc = client.get(f"/consentimientos/{doc_id}/documento")
    assert res_doc.status_code == 200
    assert "SANDÍA" in res_doc.get_data(as_text=True)
    assert "Certificación Digital de Integridad" in res_doc.get_data(as_text=True)
