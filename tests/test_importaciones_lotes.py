"""Pruebas de importación masiva segura, mapeo de pacientes y reversión de lotes."""

import io
import pandas as pd
import pytest
from sqlalchemy import select

from models import ConsultaMedica, LoteImportacion, Mascota, Tutor, Usuario, db
from tests.conftest import iniciar_sesion, token_csrf


def test_importar_tutores_seguro_y_revertir(client, app, admin):
    """Verifica que tutores se importen sin usar ID como PK y que el lote se pueda revertir."""
    iniciar_sesion(client)

    with app.app_context():
        # Crear un tutor previo en BD con ID autoincremental
        tutor_previo = Tutor(
            nombre_completo="Tutor Preexistente",
            numero_documento="99999999",
            creado_por_id=admin,
        )
        db.session.add(tutor_previo)
        db.session.commit()
        id_previo = tutor_previo.id

    # Simular CSV de tutores con ID=id_previo pero con documento diferente
    data_tutores = [
        {
            "ID": str(id_previo),
            "Tipo_Doc": "CC",
            "Documento": "1020304050",
            "Nombres": "Carlos",
            "Apellidos": "Gomez",
            "Telefono": "3110000000",
            "Correo": "carlos@test.com",
        }
    ]
    df = pd.DataFrame(data_tutores)
    csv_bytes = io.BytesIO(df.to_csv(index=False).encode("utf-8"))

    token = token_csrf(client, "/tutores/importar-excel")
    resp = client.post(
        "/tutores/importar-excel",
        data={"csrf_token": token, "archivo": (csv_bytes, "tutores.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        # Verificar que el tutor previo NO fue sobreescrito
        tutor_db = db.session.get(Tutor, id_previo)
        assert tutor_db.nombre_completo == "Tutor Preexistente"
        assert tutor_db.numero_documento == "99999999"

        # Verificar que el nuevo tutor se creó con su propio ID y lote_importacion
        nuevo = db.session.execute(
            select(Tutor).where(Tutor.numero_documento == "1020304050")
        ).scalar_one_or_none()
        assert nuevo is not None
        assert nuevo.id != id_previo
        assert nuevo.lote_importacion is not None
        lote_uuid = nuevo.lote_importacion

    # Probar reversión de lote
    token_rev = token_csrf(client, "/tutores/importar-excel")
    resp_rev = client.post(
        f"/tutores/revertir-lote/{lote_uuid}",
        data={"csrf_token": token_rev},
        follow_redirects=True,
    )
    assert resp_rev.status_code == 200

    with app.app_context():
        # El nuevo tutor fue eliminado
        eliminado = db.session.execute(
            select(Tutor).where(Tutor.numero_documento == "1020304050")
        ).scalar_one_or_none()
        assert eliminado is None

        # El tutor preexistente permanece intacto
        assert db.session.get(Tutor, id_previo) is not None


def test_importar_pacientes_e_historias_con_mapeo(client, app, admin):
    """Verifica que historias clinicas se vinculen por columna 'paciente' a Mascota.id_externo sin cruzar datos."""
    iniciar_sesion(client)

    # 1. Importar archivo 2_PACIENTES.csv
    data_pacientes = [
        {
            "ID": "1001",
            "Mascota": "MIMI FELINO",
            "Especie": "Felino",
            "Raza": "Comun",
            "Sexo": "0",
            "Peso": "4.5",
            "Propietario": "Ana Maria",
            "Doc_Propietario": "55667788",
        },
        {
            "ID": "1002",
            "Mascota": "ROCKY CANINO",
            "Especie": "Canino",
            "Raza": "Labrador",
            "Sexo": "1",
            "Peso": "28.0",
            "Propietario": "Pedro Gomez",
            "Doc_Propietario": "88776655",
        }
    ]
    df_pac = pd.DataFrame(data_pacientes)
    csv_pac = io.BytesIO(df_pac.to_csv(index=False).encode("utf-8"))

    token_pac = token_csrf(client, "/mascotas/importar-excel")
    resp_pac = client.post(
        "/mascotas/importar-excel",
        data={"csrf_token": token_pac, "archivo": (csv_pac, "2_PACIENTES.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp_pac.status_code == 200

    with app.app_context():
        mimi = db.session.execute(select(Mascota).where(Mascota.id_externo == "1001")).scalar_one()
        rocky = db.session.execute(select(Mascota).where(Mascota.id_externo == "1002")).scalar_one()

        assert mimi.especie == "felino"
        assert rocky.especie == "canino"
        assert mimi.tutor.numero_documento == "55667788"
        assert rocky.tutor.numero_documento == "88776655"
        mimi_id = mimi.id
        rocky_id = rocky.id
        mimi_tutor_id = mimi.tutor_id

    # 2. Importar historia_clinica.csv vinculada por 'paciente': 1001 (Mimi)
    data_historias = [
        {
            "paciente": "1001",
            "Motivo_Consulta": "Vacunacion y control de peso",
            "Peso": "4.6",
            "Temperatura": "38.5",
            "Diag_Definitivo": "Paciente felino sano",
            "Tratamiento": "Desparasitacion preventiva",
        }
    ]
    df_hist = pd.DataFrame(data_historias)
    csv_hist = io.BytesIO(df_hist.to_csv(index=False).encode("utf-8"))

    token_hist = token_csrf(client, "/historias/importar-excel")
    resp_hist = client.post(
        "/historias/importar-excel",
        data={"csrf_token": token_hist, "archivo": (csv_hist, "historia_clinica.csv")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp_hist.status_code == 200

    with app.app_context():
        # Verificar que la consulta quedo asignada exactamente a Mimi y al tutor de Mimi
        consulta = db.session.execute(
            select(ConsultaMedica).where(ConsultaMedica.mascota_id == mimi_id)
        ).scalar_one()

        assert consulta.mascota_id == mimi_id
        assert consulta.tutor_id == mimi_tutor_id
        assert consulta.diagnostico == "Paciente felino sano"
        assert float(consulta.peso_kg) == 4.6
        consulta_id = consulta.id
        lote_uuid_hist = consulta.lote_importacion

        # Verificar que no se creo ninguna consulta para Rocky
        consultas_rocky = db.session.execute(
            select(ConsultaMedica).where(ConsultaMedica.mascota_id == rocky_id)
        ).scalars().all()
        assert len(consultas_rocky) == 0

    # Revertir lote de historias
    token_rev_hist = token_csrf(client, "/historias/importar-excel")
    resp_rev = client.post(
        f"/historias/revertir-lote/{lote_uuid_hist}",
        data={"csrf_token": token_rev_hist},
        follow_redirects=True,
    )
    assert resp_rev.status_code == 200

    with app.app_context():
        # Consulta eliminada en reversión
        c_despues = db.session.get(ConsultaMedica, consulta_id)
        assert c_despues is None
