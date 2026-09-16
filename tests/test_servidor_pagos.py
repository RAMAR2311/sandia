"""Pruebas para el módulo de pagos de servidor, licenciamiento, bloqueo y confirmación con PIN."""

import pytest
from itsdangerous import URLSafeTimedSerializer
from models import ServerPayment, Usuario, db
from app import calcular_estado_pago_servidor


def test_confirmacion_pago_token_y_pin(client, app):
    """Verifica que la confirmación de pago con token y PIN opere correctamente."""
    with app.app_context():
        # Limpiar
        ServerPayment.query.filter_by(anio=2026, mes=10).delete()
        db.session.commit()

        serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])
        token = serializer.dumps({"anio": 2026, "mes": 10}, salt="server-payment-salt")

        # 1. GET con token válido
        res_get = client.get(f"/servidor/confirmar-pago?token={token}")
        assert res_get.status_code == 200

        # 2. POST con PIN incorrecto
        res_bad = client.post("/servidor/confirmar-pago", data={"token": token, "pin": "0000"})
        assert res_bad.status_code == 422

        # 3. POST con PIN correcto
        res_ok = client.post("/servidor/confirmar-pago", data={"token": token, "pin": "9876"})
        assert res_ok.status_code == 200

        # 4. Verificar guardado en BD
        pago = ServerPayment.query.filter_by(anio=2026, mes=10, estado="pagado").first()
        assert pago is not None
        assert pago.estado == "pagado"

        # 5. GET posterior debe mostrar estado ya confirmado
        res_ya_pagado = client.get(f"/servidor/confirmar-pago?token={token}")
        assert res_ya_pagado.status_code == 200
        assert "¡Pago Ya Confirmado!" in res_ya_pagado.get_data(as_text=True)


def test_token_invalido(client):
    """Verifica el rechazo de tokens inválidos o alterados."""
    res = client.get("/servidor/confirmar-pago?token=token_invalido_123")
    assert res.status_code == 400
