from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api import billing


def _request() -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/v1/billing/webhook",
        "headers": [],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
    })


def _settings(**overrides):
    values = {
        "flutterwave_secret_key": "test-secret",
        "flutterwave_secret_hash": "test-webhook-hash",
        "flutterwave_pro_monthly_plan_id": "1234",
        "flutterwave_pro_monthly_price_mwk": 20000,
        "public_app_base_url": "https://qwantej.example",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_pro_offer_uses_configured_monthly_mwk_price(monkeypatch):
    monkeypatch.setattr(billing, "settings", _settings())

    assert billing._offer() == {
        "price": "20000.00",
        "currency": "MWK",
        "interval": "monthly",
        "checkout_enabled": True,
    }


def test_checkout_fails_closed_until_provider_plan_is_configured(monkeypatch):
    monkeypatch.setattr(billing, "settings", _settings(flutterwave_pro_monthly_plan_id=""))

    assert billing._offer()["checkout_enabled"] is False


@pytest.mark.parametrize("payment,expected", [
    ({"id": 7, "tx_ref": "qw-1-a", "status": "successful", "amount": 20000, "currency": "MWK", "payment_type": "card"}, True),
    ({"id": 7, "tx_ref": "other", "status": "successful", "amount": 20000, "currency": "MWK", "payment_type": "card"}, False),
    ({"id": 7, "tx_ref": "qw-1-a", "status": "successful", "amount": 19999, "currency": "MWK", "payment_type": "card"}, False),
    ({"id": 7, "tx_ref": "qw-1-a", "status": "successful", "amount": 20000, "currency": "USD", "payment_type": "card"}, False),
    ({"id": 7, "tx_ref": "qw-1-a", "status": "successful", "amount": 20000, "currency": "MWK", "payment_type": "mobilemoney"}, False),
])
def test_payment_must_match_reference_amount_currency_and_card(payment, expected, monkeypatch):
    monkeypatch.setattr(billing, "settings", _settings())

    assert billing._matches_expected_transaction(payment, "qw-1-a") is expected


@pytest.mark.asyncio
async def test_webhook_rejects_invalid_signature_before_reading_body(monkeypatch):
    monkeypatch.setattr(billing, "settings", _settings())

    with pytest.raises(HTTPException) as error:
        await billing.flutterwave_webhook(_request(), db=object())

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_checkout_starts_the_configured_monthly_mwk_plan(monkeypatch):
    monkeypatch.setattr(billing, "settings", _settings())
    captured = {}

    class FakeResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"status": "success", "data": {"link": "https://checkout.flutterwave.com/v3/hosted/pay/test"}}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, *, json, headers):
            captured.update(url=url, payload=json, headers=headers)
            return FakeResponse()

    monkeypatch.setattr(billing.httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    db = SimpleNamespace(scalar=AsyncMock(return_value=None), add=Mock(), commit=AsyncMock(), refresh=AsyncMock())
    user = SimpleNamespace(id=9, email="reader@example.com", username="reader", plan="free", role="user")

    result = await billing.create_checkout(_request(), user=user, db=db)

    assert result["status"] == "pending"
    assert result["checkout_url"].startswith("https://checkout.flutterwave.com/")
    assert captured["url"].endswith("/payments")
    assert captured["payload"]["amount"] == 20000
    assert captured["payload"]["currency"] == "MWK"
    assert captured["payload"]["payment_plan"] == 1234
    assert "tx_ref=qw-9-" in captured["payload"]["redirect_url"]
    order = db.add.call_args.args[0]
    assert str(order.amount) == "20000.00"
    assert order.status == "pending"


@pytest.mark.asyncio
async def test_return_activates_pro_only_after_provider_verification(monkeypatch):
    monkeypatch.setattr(billing, "settings", _settings())
    tx_ref = "qw-9-verified"
    order = SimpleNamespace(id=3, user_id=9, tx_ref=tx_ref, status="pending", checkout_url="https://checkout.flutterwave.com/test")
    transaction = {
        "id": 71,
        "tx_ref": tx_ref,
        "status": "successful",
        "amount": 20000,
        "currency": "MWK",
        "payment_type": "card",
        "customer": {"id": 808, "email": "reader@example.com"},
    }
    monkeypatch.setattr(billing, "_verify_by_reference", AsyncMock(return_value=transaction))
    db = SimpleNamespace(
        scalar=AsyncMock(side_effect=[order, None, None]),
        add=Mock(),
        commit=AsyncMock(),
    )
    user = SimpleNamespace(id=9, email="reader@example.com", plan="free", plan_source="manual", role="user")

    result = await billing.check_checkout(tx_ref, user=user, db=db)

    assert result == {"status": "paid", "plan": "pro"}
    assert user.plan == "pro"
    assert user.plan_source == "flutterwave"
    assert order.status == "paid"
    assert len(db.add.call_args_list) == 2


@pytest.mark.asyncio
async def test_wrong_payment_amount_does_not_activate_pro(monkeypatch):
    monkeypatch.setattr(billing, "settings", _settings())
    tx_ref = "qw-9-underpaid"
    order = SimpleNamespace(id=4, user_id=9, tx_ref=tx_ref, status="pending", checkout_url="https://checkout.flutterwave.com/test")
    transaction = {
        "id": 72,
        "tx_ref": tx_ref,
        "status": "successful",
        "amount": 19999,
        "currency": "MWK",
        "payment_type": "card",
    }
    monkeypatch.setattr(billing, "_verify_by_reference", AsyncMock(return_value=transaction))
    db = SimpleNamespace(scalar=AsyncMock(return_value=order))
    user = SimpleNamespace(id=9, plan="free", plan_source="manual", role="user")

    result = await billing.check_checkout(tx_ref, user=user, db=db)

    assert result == {"status": "pending", "plan": "free"}
    assert user.plan == "free"
    db.scalar.assert_awaited_once()
