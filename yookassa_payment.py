from yookassa import Configuration, Payment
from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, WEBHOOK_URL
import uuid
import logging

logger = logging.getLogger(__name__)


class YooKassaPayment:
    def __init__(self):
        # Проверяем, что учетные данные установлены
        if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
            raise ValueError("YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY должны быть установлены в .env файле")
        
        Configuration.account_id = YOOKASSA_SHOP_ID
        Configuration.secret_key = YOOKASSA_SECRET_KEY
        logger.info(f"YooKassa настроен с shop_id: {YOOKASSA_SHOP_ID[:4]}...")

    def create_payment(self, amount: float, user_id: int, rubies: int, description: str = "Пополнение рубинов"):
        """Создать платеж в ЮКассе"""
        # Генерируем idempotence_key для предотвращения дублирования платежей
        idempotence_key = str(uuid.uuid4())
        
        try:
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
                    "user_id": str(user_id),
                    "rubies": str(rubies)
                }
            }, idempotence_key)
            
            # Получаем payment_id из ответа YooKassa
            payment_id = payment.id
            
            return {
                "payment_id": payment_id,
                "confirmation_url": payment.confirmation.confirmation_url,
                "status": payment.status
            }
        except Exception as e:
            logger.error(f"Ошибка при создании платежа в YooKassa: {e}", exc_info=True)
            raise

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
