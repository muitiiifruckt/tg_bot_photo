import os

import pytest


@pytest.mark.integration
@pytest.mark.expensive
def test_yookassa_create_payment_real():
    """
    Real API test for YooKassa.
    WARNING: creates a payment (no charge unless you actually pay it).
    Enable with RUN_EXPENSIVE=1 and ONLY use sandbox/test credentials.
    """
    shop_id = os.getenv("YOOKASSA_SHOP_ID")
    secret = os.getenv("YOOKASSA_SECRET_KEY")
    assert shop_id and secret, "Set YOOKASSA_SHOP_ID/YOOKASSA_SECRET_KEY to run integration tests"

    from tg_bot.payments.yookassa_payment import YooKassaPayment

    y = YooKassaPayment()
    p = y.create_payment(amount=1.00, user_id=123, rubies=1, description="Integration test payment")

    assert "payment_id" in p and p["payment_id"]
    assert "confirmation_url" in p and p["confirmation_url"]
    assert "status" in p and p["status"]

