import logging

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from tg_bot.core.config import TELEGRAM_BOT_TOKEN, YOOKASSA_SECRET_KEY, YOOKASSA_SHOP_ID
from tg_bot.deps import init_deps
from tg_bot.handlers.basic import error_handler, feedback_command, help_command, profile, start
from tg_bot.handlers.generate import generate_command, handle_message, handle_photo
from tg_bot.handlers.models import models_command, select_model_callback
from tg_bot.handlers.payments import buy_callback, buy_rubies, check_payment_callback
from tg_bot.handlers.transfers import send_rubies

logger = logging.getLogger(__name__)


def run() -> None:
    """Создать приложение и запустить polling."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен!")
        return

    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        logger.error("YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY должны быть установлены в .env файле!")
        logger.error("Без этих данных функция покупки рубинов работать не будет.")

    deps = init_deps()

    async def post_init(application: Application) -> None:
        application.bot_data.update(deps)
        try:
            await deps["db"].init_db()
            logger.info("База данных инициализирована")
        except Exception as e:
            logger.error(f"Ошибка при инициализации БД: {e}", exc_info=True)
            raise

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("buy", buy_rubies))
    application.add_handler(CommandHandler("send", send_rubies))
    application.add_handler(CommandHandler("generate", generate_command))
    application.add_handler(CommandHandler("models", models_command))
    application.add_handler(CommandHandler("feedback", feedback_command))
    application.add_handler(CallbackQueryHandler(buy_callback, pattern="^buy_"))
    application.add_handler(CallbackQueryHandler(check_payment_callback, pattern="^check_"))
    application.add_handler(CallbackQueryHandler(select_model_callback, pattern="^select_model_"))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)

    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

