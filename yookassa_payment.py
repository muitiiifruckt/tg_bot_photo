from yookassa import Configuration, Payment
from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, WEBHOOK_URL
import uuid


class YooKassaPayment:
    def __init__(self):
        Configuration.account_id = YOOKASSA_SHOP_ID
        Configuration.secret_key = YOOKASSA_SECRET_KEY

    def create_payment(self, amount: float, user_id: int, rubies: int, description: str = "Пополнение рубинов"):
        """Создать платеж в ЮКассе"""
        payment_id = str(uuid.uuid4())
        
        payment = Payment.create({
            "amount": {
                "value": f"{amount:.2f}",
                "currency": "RUB"
            },
            "confirmation": {
                "type": "redirect",
                "return_url": "https://t.me"  # URL для возврата после оплаты
            },
            "capture": True,
            "description": f"{description} ({rubies} рубинов)",
            "metadata": {
                "user_id": user_id,
                "rubies": rubies,
                "payment_id": payment_id
            }
        }, payment_id)
        
        return {
            "payment_id": payment_id,
            "confirmation_url": payment.confirmation.confirmation_url,
            "status": payment.status
        }

    def check_payment_status(self, payment_id: str):
        """Проверить статус платежа"""
        try:
            payment = Payment.find_one(payment_id)
            return {
                "status": payment.status,
                "paid": payment.paid,
                "metadata": payment.metadata
            }
        except Exception as e:
            print(f"Error checking payment: {e}")
            return None
