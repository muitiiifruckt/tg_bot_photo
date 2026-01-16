import asyncio
import logging
import aiohttp
import io
import json
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from config import TELEGRAM_BOT_TOKEN, RUBY_PRICE
from database import Database
from openrouter_client import OpenRouterClient
from yookassa_payment import YooKassaPayment

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Настройка логирования взаимодействий с пользователями в файл
interaction_logger = logging.getLogger('user_interactions')
interaction_logger.setLevel(logging.INFO)
# Отключаем распространение на корневой логгер
interaction_logger.propagate = False

# Создаем обработчик для файла с ротацией (максимум 10MB, до 5 файлов)
log_dir = 'logs'
os.makedirs(log_dir, exist_ok=True)  # Создаем директорию для логов, если её нет

file_handler = RotatingFileHandler(
    os.path.join(log_dir, 'user_interactions.log'),
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5,
    encoding='utf-8'
)
file_handler.setLevel(logging.INFO)
file_formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
file_handler.setFormatter(file_formatter)
interaction_logger.addHandler(file_handler)

# Инициализация компонентов
db = Database()
openrouter = OpenRouterClient()
yookassa = YooKassaPayment()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    user = update.effective_user
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | COMMAND: /start | NAME: {user.first_name}")
    
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
/feedback - Отправить совет для улучшения
/help - Помощь
"""
    await update.message.reply_text(welcome_text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    user = update.effective_user
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | COMMAND: /help")
    
    help_text = """
📖 Справка по боту:

/generate - Сгенерировать изображение по вашему описанию
/profile - Посмотреть свой профиль и баланс рубинов
/buy - Купить рубины для генерации изображений
/feedback - Отправить совет для улучшения бота
/help - Показать эту справку

💎 Генерация изображения стоит 2 рубина
💎 1 рубин = 5 рублей

Просто отправьте описание изображения, и бот сгенерирует его для вас!
"""
    await update.message.reply_text(help_text)


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /profile"""
    user = update.effective_user
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | COMMAND: /profile")
    
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
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | COMMAND: /buy")
    
    text = f"""
💎 Пополнение баланса рубинов

Цена: 1 рубин = {int(RUBY_PRICE)} рублей

Введите количество рубинов, которое хотите купить (например: 10, 50, 100)

Или выберите готовый вариант:
"""
    
    keyboard = [
        [InlineKeyboardButton(f"💎 10 рубинов - {int(RUBY_PRICE * 10)} руб.", callback_data="buy_10")],
        [InlineKeyboardButton(f"💎 50 рубинов - {int(RUBY_PRICE * 50)} руб.", callback_data="buy_50")],
        [InlineKeyboardButton(f"💎 100 рубинов - {int(RUBY_PRICE * 100)} руб.", callback_data="buy_100")],
        [InlineKeyboardButton(f"💎 200 рубинов - {int(RUBY_PRICE * 200)} руб.", callback_data="buy_200")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup)
    
    # Устанавливаем состояние ожидания ввода количества рубинов
    context.user_data['waiting_for_rubies'] = True


async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback для покупки рубинов"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    data = query.data
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | CALLBACK: {data}")
    
    # Извлекаем количество рубинов из callback_data (buy_10, buy_50 и т.д.)
    try:
        rubies_count = int(data.replace("buy_", ""))
    except ValueError:
        await query.edit_message_text("❌ Неверный формат")
        return
    
    if rubies_count <= 0:
        await query.edit_message_text("❌ Количество рубинов должно быть больше 0")
        return
    
    # Рассчитываем цену: 1 рубин = 5 рублей
    amount = rubies_count * RUBY_PRICE
    
    # Создаем платеж в ЮКассе
    payment_info = yookassa.create_payment(
        amount=amount,
        user_id=user.id,
        rubies=rubies_count
    )
    
    # Сохраняем платеж в БД
    await db.create_payment(
        payment_id=payment_info["payment_id"],
        user_id=user.id,
        amount=amount,
        rubies=rubies_count
    )
    
    keyboard = [
        [InlineKeyboardButton("💳 Оплатить", url=payment_info["confirmation_url"])],
        [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_{payment_info['payment_id']}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = f"""
💳 Создан платеж

Количество рубинов: {rubies_count} 💎
Сумма: {amount:.2f} ₽
(1 рубин = {int(RUBY_PRICE)} рублей)

Нажмите кнопку "Оплатить" для перехода к оплате через СБП.
После оплаты нажмите "Проверить оплату".
"""
    await query.edit_message_text(text, reply_markup=reply_markup)


async def check_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик проверки оплаты"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    payment_id = query.data.replace("check_", "")
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | CALLBACK: check_payment | PAYMENT_ID: {payment_id}")
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
    user = update.effective_user
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | COMMAND: /generate")
    
    text = """
🎨 Генерация изображения

Отправьте описание изображения, которое вы хотите сгенерировать.

💎 Стоимость: 2 рубина за генерацию

Примеры:
• "Красивый закат над горами"
• "Кот в космосе"
• "Футуристический город"
"""
    await update.message.reply_text(text)


async def save_feedback_to_jsonl(username: str, text: str, user_id: int):
    """Сохраняет отзыв в JSONL файл"""
    feedback_file = "feedback.jsonl"
    
    feedback_entry = {
        "user_id": user_id,
        "username": username or "не указан",
        "text": text,
        "timestamp": datetime.now().isoformat()
    }
    
    try:
        with open(feedback_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(feedback_entry, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        logger.error(f"Error saving feedback: {e}")
        return False


async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /feedback - сбор советов для улучшения"""
    user = update.effective_user
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | COMMAND: /feedback")
    
    text = """
💡 Совет для улучшения бота

Мы ценим ваше мнение! Пожалуйста, отправьте ваш совет или пожелание по улучшению бота.

Ваш отзыв поможет нам сделать бота лучше! 🙏
"""
    await update.message.reply_text(text)
    
    # Устанавливаем состояние ожидания ввода отзыва
    context.user_data['waiting_for_feedback'] = True


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений для генерации изображений и покупки рубинов"""
    user = update.effective_user
    text = update.message.text
    
    # Проверяем, не ожидаем ли мы ввод отзыва
    if context.user_data.get('waiting_for_feedback'):
        context.user_data['waiting_for_feedback'] = False
        
        # Логируем отзыв
        interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | FEEDBACK: {text[:100]}...")
        
        # Сохраняем отзыв в JSONL файл
        success = await save_feedback_to_jsonl(
            username=user.username,
            text=text,
            user_id=user.id
        )
        
        if success:
            await update.message.reply_text(
                "✅ Спасибо за ваш отзыв! Мы обязательно учтем ваши пожелания. 🙏"
            )
        else:
            await update.message.reply_text(
                "❌ Произошла ошибка при сохранении отзыва. Попробуйте позже."
            )
        return
    
    # Проверяем, не ожидаем ли мы ввод количества рубинов
    if context.user_data.get('waiting_for_rubies'):
        context.user_data['waiting_for_rubies'] = False
        
        # Пытаемся распарсить количество рубинов
        try:
            rubies_count = int(text.strip())
            
            if rubies_count <= 0:
                await update.message.reply_text("❌ Количество рубинов должно быть больше 0")
                return
            
            if rubies_count > 10000:
                await update.message.reply_text("❌ Максимальное количество рубинов за раз: 10000")
                return
            
            # Рассчитываем цену: 1 рубин = 5 рублей
            amount = rubies_count * RUBY_PRICE
            
            # Логируем покупку рубинов
            interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | ACTION: buy_rubies | COUNT: {rubies_count} | AMOUNT: {amount:.2f} руб.")
            
            # Создаем платеж в ЮКассе
            payment_info = yookassa.create_payment(
                amount=amount,
                user_id=user.id,
                rubies=rubies_count
            )
            
            # Сохраняем платеж в БД
            await db.create_payment(
                payment_id=payment_info["payment_id"],
                user_id=user.id,
                amount=amount,
                rubies=rubies_count
            )
            
            keyboard = [
                [InlineKeyboardButton("💳 Оплатить", url=payment_info["confirmation_url"])],
                [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_{payment_info['payment_id']}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            payment_text = f"""
💳 Создан платеж

Количество рубинов: {rubies_count} 💎
Сумма: {amount:.2f} ₽
(1 рубин = {int(RUBY_PRICE)} рублей)

Нажмите кнопку "Оплатить" для перехода к оплате через СБП.
После оплаты нажмите "Проверить оплату".
"""
            await update.message.reply_text(payment_text, reply_markup=reply_markup)
            return
            
        except ValueError:
            # Если введен не число, сбрасываем флаг и обрабатываем как промпт
            context.user_data['waiting_for_rubies'] = False
            # Продолжаем обработку как обычное сообщение (будет обработано ниже как промпт)
            pass
    
    # Если не ожидаем ввод рубинов, обрабатываем как промпт для генерации
    prompt = text
    
    # Логируем запрос на генерацию
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | ACTION: generate_image | PROMPT: {text[:100]}...")
    
    # Проверяем баланс (генерация стоит 2 рубина)
    rubies = await db.get_user_rubies(user.id)
    GENERATION_COST = 2  # 2 рубина за генерацию
    
    if rubies < GENERATION_COST:
        interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | ACTION: generate_image | STATUS: insufficient_balance | RUBIES: {rubies}")
        await update.message.reply_text(
            f"❌ Недостаточно рубинов!\n\n"
            f"Текущий баланс: {rubies} 💎\n"
            f"Требуется: {GENERATION_COST} 💎\n\n"
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
            # Списываем рубины перед отправкой (2 рубина за генерацию)
            GENERATION_COST = 2
            success = await db.deduct_rubies(user.id, GENERATION_COST)
            
            if success:
                # Логируем генерацию
                await db.log_generation(user.id, prompt, GENERATION_COST)
                interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | ACTION: image_generated | COST: {GENERATION_COST} rubies | SUCCESS")
                
                # Отправляем изображение
                await status_message.delete()
                await update.message.reply_photo(
                    photo=io.BytesIO(image_data),
                    caption=f"🎨 Сгенерировано по запросу: {prompt}\n\n💎 Потрачено: {GENERATION_COST} рубина"
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


async def post_init(application: Application) -> None:
    """Инициализация БД после создания приложения"""
    await db.init_db()
    logger.info("База данных инициализирована")


def main():
    """Главная функция для запуска бота"""
    # Проверка наличия токенов
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен!")
        return
    
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("buy", buy_rubies))
    application.add_handler(CommandHandler("generate", generate_command))
    application.add_handler(CommandHandler("feedback", feedback_command))
    application.add_handler(CallbackQueryHandler(buy_callback, pattern="^buy_"))
    application.add_handler(CallbackQueryHandler(check_payment_callback, pattern="^check_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
