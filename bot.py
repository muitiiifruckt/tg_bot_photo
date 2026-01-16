import asyncio
import logging
import aiohttp
import io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from config import TELEGRAM_BOT_TOKEN, PRICE_PER_GENERATION
from database import Database
from openrouter_client import OpenRouterClient
from yookassa_payment import YooKassaPayment

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация компонентов
db = Database()
openrouter = OpenRouterClient()
yookassa = YooKassaPayment()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    await db.get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name
    )
    
    rubies = await db.get_user_rubies(user.id)
    
    welcome_text = f"""
👋 Привет, {user.first_name}!

Добро пожаловать в бота для генерации изображений! 🎨

💎 Твои рубины: {rubies}

Используй команды:
/generate - Сгенерировать изображение
/profile - Мой профиль
/buy - Купить рубины
/help - Помощь
"""
    await update.message.reply_text(welcome_text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    help_text = f"""
📖 Справка по боту:

/generate - Сгенерировать изображение по вашему описанию
/profile - Посмотреть свой профиль и баланс рубинов
/buy - Купить рубины для генерации изображений
/help - Показать эту справку

💎 Стоимость одной генерации: {PRICE_PER_GENERATION} рубинов

Просто отправьте описание изображения, и бот сгенерирует его для вас!
"""
    await update.message.reply_text(help_text)


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /profile"""
    user = update.effective_user
    user_data = await db.get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name
    )
    
    profile_text = f"""
👤 Профиль пользователя

Имя: {user_data['first_name']}
Username: @{user_data['username'] or 'не указан'}
💎 Рубины: {user_data['rubies']}

Используйте /buy для пополнения баланса
"""
    await update.message.reply_text(profile_text)


async def buy_rubies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /buy - покупка рубинов"""
    user = update.effective_user
    
    keyboard = [
        [InlineKeyboardButton("💎 50 рубинов - 100₽", callback_data="buy_50")],
        [InlineKeyboardButton("💎 100 рубинов - 180₽", callback_data="buy_100")],
        [InlineKeyboardButton("💎 200 рубинов - 350₽", callback_data="buy_200")],
        [InlineKeyboardButton("💎 500 рубинов - 800₽", callback_data="buy_500")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = """
💎 Пополнение баланса рубинов

Выберите количество рубинов для покупки:
"""
    await update.message.reply_text(text, reply_markup=reply_markup)


async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback для покупки рубинов"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    data = query.data
    
    # Маппинг количества рубинов и цены
    packages = {
        "buy_50": {"rubies": 50, "price": 100.0},
        "buy_100": {"rubies": 100, "price": 180.0},
        "buy_200": {"rubies": 200, "price": 350.0},
        "buy_500": {"rubies": 500, "price": 800.0},
    }
    
    if data not in packages:
        await query.edit_message_text("❌ Неверный пакет")
        return
    
    package = packages[data]
    
    # Создаем платеж в ЮКассе
    payment_info = yookassa.create_payment(
        amount=package["price"],
        user_id=user.id,
        rubies=package["rubies"]
    )
    
    # Сохраняем платеж в БД
    await db.create_payment(
        payment_id=payment_info["payment_id"],
        user_id=user.id,
        amount=package["price"],
        rubies=package["rubies"]
    )
    
    keyboard = [
        [InlineKeyboardButton("💳 Оплатить", url=payment_info["confirmation_url"])],
        [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_{payment_info['payment_id']}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""
💳 Создан платеж

Количество рубинов: {package['rubies']} 💎
Сумма: {package['price']:.2f} ₽

Нажмите кнопку "Оплатить" для перехода к оплате через СБП.
После оплаты нажмите "Проверить оплату".
"""
    await query.edit_message_text(text, reply_markup=reply_markup)


async def check_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик проверки оплаты"""
    query = update.callback_query
    await query.answer()
    
    payment_id = query.data.replace("check_", "")
    payment_data = await db.get_payment(payment_id)
    
    if not payment_data:
        await query.edit_message_text("❌ Платеж не найден")
        return
    
    # Проверяем статус в ЮКассе
    yookassa_status = yookassa.check_payment_status(payment_id)
    
    if yookassa_status and yookassa_status["paid"]:
        if payment_data["status"] != "succeeded":
            # Начисляем рубины
            await db.add_rubies(payment_data["user_id"], payment_data["rubies"])
            await db.update_payment_status(payment_id, "succeeded")
            
            rubies = await db.get_user_rubies(payment_data["user_id"])
            await query.edit_message_text(
                f"✅ Платеж успешно обработан!\n\n"
                f"Начислено: {payment_data['rubies']} 💎\n"
                f"Текущий баланс: {rubies} 💎"
            )
        else:
            await query.edit_message_text("✅ Платеж уже был обработан ранее")
    else:
        await query.edit_message_text(
            "⏳ Платеж еще не обработан. Попробуйте проверить позже.\n\n"
            "Или нажмите кнопку 'Проверить оплату' еще раз."
        )


async def generate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /generate"""
    text = f"""
🎨 Генерация изображения

Отправьте описание изображения, которое вы хотите сгенерировать.

💎 Стоимость: {PRICE_PER_GENERATION} рубинов за генерацию

Примеры:
• "Красивый закат над горами"
• "Кот в космосе"
• "Футуристический город"
"""
    await update.message.reply_text(text)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений для генерации изображений"""
    user = update.effective_user
    prompt = update.message.text
    
    # Проверяем баланс
    rubies = await db.get_user_rubies(user.id)
    
    if rubies < PRICE_PER_GENERATION:
        await update.message.reply_text(
            f"❌ Недостаточно рубинов!\n\n"
            f"Текущий баланс: {rubies} 💎\n"
            f"Требуется: {PRICE_PER_GENERATION} 💎\n\n"
            f"Используйте /buy для пополнения баланса."
        )
        return
    
    # Отправляем сообщение о начале генерации
    status_message = await update.message.reply_text("⏳ Генерирую изображение... Это может занять некоторое время.")
    
    try:
        # Генерируем изображение
        image_url = await openrouter.generate_image(prompt)
        
        if not image_url:
            await status_message.edit_text("❌ Ошибка при генерации изображения. Попробуйте еще раз.")
            return
        
        # Обрабатываем изображение
        image_data = None
        
        if image_url.startswith("data:image"):
            # Декодируем base64 изображение
            image_data = openrouter.decode_base64_image(image_url)
        elif image_url.startswith("http"):
            # Если это URL, пытаемся скачать
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as resp:
                        if resp.status == 200:
                            image_data = await resp.read()
            except Exception as e:
                logger.error(f"Error downloading image: {e}")
        
        if image_data:
            # Списываем рубины перед отправкой
            success = await db.deduct_rubies(user.id, PRICE_PER_GENERATION)
            
            if success:
                # Логируем генерацию
                await db.log_generation(user.id, prompt, PRICE_PER_GENERATION)
                
                # Отправляем изображение
                await status_message.delete()
                await update.message.reply_photo(
                    photo=io.BytesIO(image_data),
                    caption=f"🎨 Сгенерировано по запросу: {prompt}\n\n💎 Потрачено: {PRICE_PER_GENERATION} рубинов"
                )
                
                # Показываем новый баланс
                new_rubies = await db.get_user_rubies(user.id)
                await update.message.reply_text(f"💎 Остаток рубинов: {new_rubies}")
            else:
                await status_message.edit_text("❌ Ошибка при списании рубинов")
        else:
            await status_message.edit_text("❌ Не удалось обработать изображение. Попробуйте еще раз.")
            
    except Exception as e:
        logger.error(f"Error in handle_message: {e}")
        await status_message.edit_text("❌ Произошла ошибка при генерации изображения. Попробуйте позже.")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Update {update} caused error {context.error}")


def main():
    """Главная функция для запуска бота"""
    # Проверка наличия токенов
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен!")
        return
    
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Инициализируем БД
    asyncio.run(db.init_db())
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("buy", buy_rubies))
    application.add_handler(CommandHandler("generate", generate_command))
    application.add_handler(CallbackQueryHandler(buy_callback, pattern="^buy_"))
    application.add_handler(CallbackQueryHandler(check_payment_callback, pattern="^check_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
