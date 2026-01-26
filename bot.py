import asyncio
import logging
import aiohttp
import io
import json
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from config import TELEGRAM_BOT_TOKEN, RUBY_PRICE
from database import Database
from openrouter_client import OpenRouterClient
from yookassa_payment import YooKassaPayment
from models_manager import ModelsManager

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
models_manager = ModelsManager()

# Буфер для хранения медиа-групп (несколько фото в одном сообщении)
media_groups = {}


def get_user_selected_model(context: ContextTypes.DEFAULT_TYPE):
    """Получить выбранную пользователем модель или модель по умолчанию"""
    selected_model_name = context.user_data.get('selected_model')
    
    if selected_model_name:
        model = models_manager.get_model_by_name(selected_model_name)
        if model:
            return model
    
    # Если модель не выбрана или не найдена, возвращаем дефолтную
    return models_manager.get_default_model()


# Главное меню с кнопками
def get_main_menu_keyboard():
    """Создает главное меню с кнопками"""
    keyboard = [
        [KeyboardButton("🎨 Генерация"), KeyboardButton("🤖 Модели")],
        [KeyboardButton("👤 Профиль"), KeyboardButton("💎 Купить рубины")],
        [KeyboardButton("💸 Отправить рубины"), KeyboardButton("💡 Отзыв")],
        [KeyboardButton("❓ Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


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
/models - Доступные модели
/profile - Мой профиль
/buy - Купить рубины
/send - Отправить рубины другу
/feedback - Отправить совет для улучшения
/help - Помощь

🎨 Генерируй изображения двумя способами:
• Отправь текстовое описание
• Загрузи фото для модификации
"""
    await update.message.reply_text(welcome_text, reply_markup=get_main_menu_keyboard())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help"""
    user = update.effective_user
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | COMMAND: /help")
    
    help_text = """
📖 Справка по боту:

/generate - Сгенерировать изображение по вашему описанию
/models - Посмотреть доступные модели и цены
/profile - Посмотреть свой профиль и баланс рубинов
/buy - Купить рубины для генерации изображений
/send - Отправить рубины другому пользователю
/feedback - Отправить совет для улучшения бота
/help - Показать эту справку

💎 Стоимость генерации зависит от модели
💎 1 рубин = 1 рубль

🎨 Способы генерации:
1. Отправьте текстовое описание - бот создаст изображение с нуля
2. Отправьте фото - бот попросит описание для модификации
3. Отправьте фото с подписью - бот сразу начнет генерацию

💸 Перевод рубинов:
/send @username 10 - отправить 10 рубинов пользователю

Примеры: "Красивый закат", "Кот в космосе" или загрузите фото с подписью "В стиле аниме"
"""
    await update.message.reply_text(help_text, reply_markup=get_main_menu_keyboard())


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /profile"""
    user = update.effective_user
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | COMMAND: /profile")
    
    user_data = await db.get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name
    )
    
    # Получаем историю переводов
    transfers = await db.get_transfer_history(user.id, limit=5)
    
    transfer_text = ""
    if transfers:
        transfer_text = "\n\n📊 Последние переводы:\n"
        for t in transfers:
            if t['from_user_id'] == user.id:
                # Исходящий перевод
                to_name = f"@{t['to_username']}" if t['to_username'] else t['to_first_name']
                transfer_text += f"➡️ {to_name}: -{t['amount']} 💎\n"
            else:
                # Входящий перевод
                from_name = f"@{t['from_username']}" if t['from_username'] else t['from_first_name']
                transfer_text += f"⬅️ {from_name}: +{t['amount']} 💎\n"
    
    profile_text = f"""
👤 Профиль пользователя

Имя: {user_data['first_name']}
Username: @{user_data['username'] or 'не указан'}
💎 Рубины: {user_data['rubies']}

"""
    await update.message.reply_text(profile_text, reply_markup=get_main_menu_keyboard())


async def send_rubies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /send - отправка рубинов другому пользователю"""
    user = update.effective_user
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | COMMAND: /send")

    # Гарантируем, что пользователь существует в БД (например, если не нажимал /start)
    await db.get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name
    )
    
    # Проверяем аргументы команды
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "💸 Отправка рубинов\n\n"
            "Использование: /send @username количество\n\n"
            "Примеры:\n"
            "• /send @friend 10\n"
            "• /send friend 5\n\n"
            "Минимальная сумма перевода: 1 рубин"
        )
        return
    
    recipient_username = context.args[0].lstrip('@')
    
    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Неверное количество рубинов. Укажите число.")
        return
    
    if amount <= 0:
        await update.message.reply_text("❌ Количество рубинов должно быть больше 0")
        return
    
    # Проверяем баланс отправителя
    sender_balance = await db.get_user_rubies(user.id)
    
    if sender_balance < amount:
        await update.message.reply_text(
            f"❌ Недостаточно рубинов!\n\n"
            f"Ваш баланс: {sender_balance} 💎\n"
            f"Требуется: {amount} 💎\n\n"
        )
        return
    
    # Ищем получателя по username
    recipient = await db.get_user_by_username(recipient_username)
    
    if not recipient:
        await update.message.reply_text(
            f"❌ Пользователь @{recipient_username} не найден.\n\n"
            f"Убедитесь, что:\n"
            f"• Никнейм указан правильно\n"
            f"• Пользователь уже запускал этого бота (/start)"
        )
        return
    
    # Проверяем, что не отправляем сами себе
    if recipient['user_id'] == user.id:
        await update.message.reply_text("❌ Нельзя отправить рубины самому себе!")
        return
    
    # Выполняем перевод
    success = await db.transfer_rubies(user.id, recipient['user_id'], amount)
    
    if success:
        new_balance = await db.get_user_rubies(user.id)
        recipient_new_balance = await db.get_user_rubies(recipient['user_id'])
        recipient_name = f"@{recipient['username']}" if recipient['username'] else recipient['first_name']
        
        interaction_logger.info(
            f"USER: @{user.username or 'не указан'} (ID: {user.id}) | "
            f"ACTION: transfer_rubies | TO: @{recipient['username']} (ID: {recipient['user_id']}) | "
            f"AMOUNT: {amount}"
        )
        
        await update.message.reply_text(
            f"✅ Перевод выполнен!\n\n"
            f"Отправлено {recipient_name}: {amount} 💎\n"
            f"Ваш новый баланс: {new_balance} 💎"
        )
        
        # Уведомляем получателя (если возможно)
        try:
            sender_name = f"@{user.username}" if user.username else user.first_name
            await context.bot.send_message(
                chat_id=recipient['user_id'],
                text=f"🎁 Вы получили перевод!\n\n"
                     f"От: {sender_name}\n"
                     f"Сумма: {amount} 💎\n\n"
                     f"Ваш новый баланс: {recipient_new_balance} 💎"
            )
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление получателю: {e}")
    else:
        await update.message.reply_text("❌ Ошибка при выполнении перевода. Попробуйте позже.")


async def buy_rubies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /buy - покупка рубинов"""
    user = update.effective_user
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | COMMAND: /buy")
    
    text = f"""
💎 Пополнение баланса рубинов

Цена: 1 рубин = {int(RUBY_PRICE)} рубль

Введите количество рубинов, которое хотите купить (например: 10, 50, 100)

Или выберите готовый вариант:
"""
    
    keyboard = [
        [InlineKeyboardButton(f"💎 10 рубинов - 10 руб.", callback_data="buy_10")],
        [InlineKeyboardButton(f"💎 50 рубинов - 50 руб.", callback_data="buy_50")],
        [InlineKeyboardButton(f"💎 100 рубинов - 100 руб.", callback_data="buy_100")],
        [InlineKeyboardButton(f"💎 200 рубинов - 200 руб.", callback_data="buy_200")],
    ]
    inline_keyboard = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=inline_keyboard)
    
    # Устанавливаем состояние ожидания ввода количества рубинов
    context.user_data['waiting_for_rubies'] = True


async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback для покупки рубинов"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    data = query.data
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | CALLBACK: {data}")

    # Гарантируем, что пользователь существует в БД
    await db.get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name
    )
    
    # Извлекаем количество рубинов из callback_data (buy_10, buy_50 и т.д.)
    try:
        rubies_count = int(data.replace("buy_", ""))
    except ValueError:
        await query.edit_message_text("❌ Неверный формат")
        return
    
    if rubies_count <= 0:
        await query.edit_message_text("❌ Количество рубинов должно быть больше 0")
        return
    
    # Рассчитываем цену: 1 рубин = 1 рубль
    amount = rubies_count * RUBY_PRICE
    
    try:
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
(1 рубин = {int(RUBY_PRICE)} рубль)

Нажмите кнопку "Оплатить" для перехода к оплате через СБП.
После оплаты нажмите "Проверить оплату".
"""
        await query.edit_message_text(text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Ошибка при создании платежа: {e}", exc_info=True)
        await query.edit_message_text(
            "❌ Произошла ошибка при создании платежа. "
            "Пожалуйста, попробуйте позже или обратитесь к администратору."
        )


async def check_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик проверки оплаты"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    payment_id = query.data.replace("check_", "")
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | CALLBACK: check_payment | PAYMENT_ID: {payment_id}")

    # Гарантируем, что пользователь существует в БД
    await db.get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name
    )
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
    
    # Получаем информацию о текущей модели
    default_model = models_manager.get_default_model()
    model_info = ""
    if default_model:
        model_info = f"\n🤖 Модель: {default_model['display_name']}\n💎 Цена: {default_model['price_rubies']} рубин{'ов' if default_model['price_rubies'] > 1 else ''}\n"
    
    text = f"""
🎨 Генерация изображения

Отправьте описание изображения, которое вы хотите сгенерировать.
Или отправьте фото + описание для генерации на основе изображения.
{model_info}
Примеры текстовых промптов:
• "Красивый закат над горами"
• "Кот в космосе"
• "Футуристический город"

Для генерации на основе фото:
1. Отправьте фото
2. Отправьте описание того, как изменить изображение

"""
    await update.message.reply_text(text, reply_markup=get_main_menu_keyboard())


async def models_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /models - показать доступные модели с кнопками выбора"""
    user = update.effective_user
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | COMMAND: /models")
    
    # Получаем текущую выбранную модель
    current_model = context.user_data.get('selected_model')
    if not current_model:
        default = models_manager.get_default_model()
        current_model = default['openrouter_name'] if default else None
    
    # Формируем текст и кнопки
    models_text = "🤖 Доступные модели:\n\n"
    keyboard = []
    
    for model in models_manager.get_enabled_models():
        is_current = model['openrouter_name'] == current_model
        icon = "✅" if is_current else "⚪"
        
        models_text += f"{icon} **{model['display_name']}**\n"
        models_text += f"   {model['description']}\n"
        models_text += f"   💎 Цена: {model['price_rubies']} рубин{'ов' if model['price_rubies'] > 1 else ''}\n\n"
        
        # Добавляем кнопку выбора
        button_text = f"{'✅' if is_current else '⚪'} {model['display_name']} - {model['price_rubies']} 💎"
        keyboard.append([
            InlineKeyboardButton(
                button_text,
                callback_data=f"select_model_{model['openrouter_name']}"
            )
        ])
    
    models_text += "👆 Нажмите на модель, чтобы выбрать её для генерации"
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(models_text, reply_markup=reply_markup, parse_mode='Markdown')


async def select_model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора модели"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    model_name = query.data.replace("select_model_", "")
    model = models_manager.get_model_by_name(model_name)
    
    if model:
        # Сохраняем выбранную модель
        context.user_data['selected_model'] = model_name
        
        interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | ACTION: select_model | MODEL: {model['display_name']}")
        
        await query.edit_message_text(
            f"✅ Выбрана модель: **{model['display_name']}**\n\n"
            f"📝 {model['description']}\n\n"
            f"💎 Цена генерации: {model['price_rubies']} рубин{'ов' if model['price_rubies'] > 1 else ''}\n\n"
            f"Теперь все ваши генерации будут использовать эту модель.",
            parse_mode='Markdown'
        )
    else:
        await query.edit_message_text("❌ Модель не найдена")


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


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик фотографий для генерации на основе изображения"""
    user = update.effective_user
    media_group_id = update.message.media_group_id

    # Гарантируем, что пользователь существует в БД (например, если не нажимал /start)
    await db.get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name
    )
    
    # Получаем цену генерации из выбранной модели
    selected_model = get_user_selected_model(context)
    GENERATION_COST = selected_model['price_rubies'] if selected_model else 2
    
    # Проверяем баланс
    rubies = await db.get_user_rubies(user.id)
    
    if rubies < GENERATION_COST:
        interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | ACTION: photo_upload | STATUS: insufficient_balance")
        await update.message.reply_text(
            f"❌ Недостаточно рубинов для генерации!\n\n"
            f"Текущий баланс: {rubies} 💎\n"
            f"Требуется: {GENERATION_COST} 💎\n\n",
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    # Получаем фото
    photo = update.message.photo[-1]  # Берем самое большое разрешение
    photo_file = await photo.get_file()
    
    # Скачиваем фото в байты
    photo_bytes = await photo_file.download_as_bytearray()
    
    caption = update.message.caption if update.message.caption else None
    
    # Проверяем, является ли это частью медиа-группы (несколько фото)
    if media_group_id:
        # Это часть альбома - собираем все фото
        if media_group_id not in media_groups:
            media_groups[media_group_id] = {
                'photos': [],
                'caption': caption,
                'user_id': user.id,
                'update': update,
                'context': context
            }
        
        media_groups[media_group_id]['photos'].append(bytes(photo_bytes))
        
        # Устанавливаем таймер для обработки группы (ждем 2 секунды после последнего фото)
        if 'timer' in media_groups[media_group_id]:
            media_groups[media_group_id]['timer'].cancel()
        
        async def process_media_group():
            await asyncio.sleep(2)  # Ждем 2 секунды для сбора всех фото
            if media_group_id in media_groups:
                group_data = media_groups.pop(media_group_id)
                await handle_media_group(group_data)
        
        task = asyncio.create_task(process_media_group())
        media_groups[media_group_id]['timer'] = task
        
    else:
        # Одно фото - обрабатываем как раньше
        context.user_data['input_image'] = bytes(photo_bytes)
        context.user_data['waiting_for_image_prompt'] = True
        
        interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | ACTION: photo_uploaded")
        
        if caption:
            # Если есть подпись к фото, используем её как промпт
            context.user_data['waiting_for_image_prompt'] = False
            await process_image_generation(update, context, caption, bytes(photo_bytes))
        else:
            # Запрашиваем промпт
            await update.message.reply_text(
                "📸 Фото получено! Теперь отправьте описание того, как вы хотите изменить это изображение.\n\n"
                "Примеры:\n"
                "• 'Сделай это в стиле аниме'\n"
                "• 'Преврати это в картину маслом'\n"
                "• 'Добавь фантастические элементы'",
                reply_markup=get_main_menu_keyboard()
            )


async def handle_media_group(group_data):
    """Обработка группы фото (альбома)"""
    photos = group_data['photos']
    caption = group_data['caption']
    user_id = group_data['user_id']
    update = group_data['update']
    context = group_data['context']
    user = update.effective_user
    
    # Сохраняем все фото в контексте
    context.user_data['input_images'] = photos
    context.user_data['waiting_for_images_prompt'] = True
    
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user_id}) | ACTION: media_group_uploaded | COUNT: {len(photos)}")
    
    if caption:
        # Если есть подпись, используем её как промпт
        context.user_data['waiting_for_images_prompt'] = False
        await process_images_generation(update, context, caption, photos)
    else:
        # Запрашиваем промпт
        await update.message.reply_text(
            f"📸 Получено {len(photos)} фото! Теперь отправьте описание того, что вы хотите сделать.\n\n"
            f"Примеры:\n"
            f"• 'Объедини стили этих фото'\n"
            f"• 'Сделай с 1 фото такой же стиль как на 2'\n"
            f"• 'Создай коллаж из этих изображений'",
            reply_markup=get_main_menu_keyboard()
        )


async def process_images_generation(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str, input_images: list):
    """Обработка генерации изображения на основе нескольких входных изображений"""
    user = update.effective_user
    
    # Получаем цену генерации из выбранной модели
    selected_model = get_user_selected_model(context)
    GENERATION_COST = selected_model['price_rubies'] if selected_model else 2
    model_name = selected_model['display_name'] if selected_model else "Unknown"
    
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | ACTION: generate_from_images | COUNT: {len(input_images)} | PROMPT: {prompt[:100]}...")
    
    status_message = await update.message.reply_text(f"⏳ Генерирую изображение на основе {len(input_images)} фото... Это может занять некоторое время.")
    
    try:
        # Генерируем изображение на основе нескольких фото
        image_url = await openrouter.generate_image(prompt, input_images=input_images, model=selected_model['openrouter_name'])
        
        if not image_url:
            await status_message.edit_text("❌ Ошибка при генерации изображения. Попробуйте еще раз.")
            return
        
        # Обрабатываем изображение
        image_data = None
        
        if image_url.startswith("data:image"):
            image_data = openrouter.decode_base64_image(image_url)
        elif image_url.startswith("http"):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as resp:
                        if resp.status == 200:
                            image_data = await resp.read()
            except Exception as e:
                logger.error(f"Error downloading image: {e}")
        
        if image_data:
            # Списываем рубины
            success = await db.deduct_rubies(user.id, GENERATION_COST)
            
            if success:
                await db.log_generation(user.id, f"[Multi-Image] {prompt}", GENERATION_COST)
                interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | ACTION: image_generated_from_photos | COST: {GENERATION_COST} rubies | SUCCESS")
                
                await status_message.delete()
                
                # Обрезаем промпт для caption (лимит Telegram - 1024 символа)
                short_prompt = prompt[:150] + "..." if len(prompt) > 150 else prompt
                
                await update.message.reply_photo(
                    photo=io.BytesIO(image_data),
                    caption=f"🎨 Сгенерировано на основе {len(input_images)} фото\n📝 Промпт: {short_prompt}\n\n💎 Потрачено: {GENERATION_COST} рубин{'ов' if GENERATION_COST > 1 else ''}",
                    reply_markup=get_main_menu_keyboard()
                )
                
                new_rubies = await db.get_user_rubies(user.id)
                await update.message.reply_text(f"💎 Остаток рубинов: {new_rubies}", reply_markup=get_main_menu_keyboard())
            else:
                await status_message.edit_text("❌ Ошибка при списании рубинов")
        else:
            await status_message.edit_text("❌ Не удалось обработать изображение. Попробуйте еще раз.")
    
    except Exception as e:
        logger.error(f"Error in process_images_generation: {e}")
        await status_message.edit_text("❌ Произошла ошибка при генерации изображения. Попробуйте позже.")


async def process_image_generation(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str, input_image: bytes):
    """Обработка генерации изображения на основе входного"""
    user = update.effective_user
    
    # Получаем цену генерации из выбранной модели
    selected_model = get_user_selected_model(context)
    GENERATION_COST = selected_model['price_rubies'] if selected_model else 2
    model_name = selected_model['display_name'] if selected_model else "Unknown"
    
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | ACTION: generate_from_image | PROMPT: {prompt[:100]}...")
    
    status_message = await update.message.reply_text("⏳ Генерирую изображение на основе вашего фото... Это может занять некоторое время.")
    
    try:
        # Генерируем изображение
        image_url = await openrouter.generate_image(prompt, input_image=input_image, model=selected_model['openrouter_name'])
        
        if not image_url:
            await status_message.edit_text("❌ Ошибка при генерации изображения. Попробуйте еще раз.")
            return
        
        # Обрабатываем изображение
        image_data = None
        
        if image_url.startswith("data:image"):
            image_data = openrouter.decode_base64_image(image_url)
        elif image_url.startswith("http"):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as resp:
                        if resp.status == 200:
                            image_data = await resp.read()
            except Exception as e:
                logger.error(f"Error downloading image: {e}")
        
        if image_data:
            # Списываем рубины
            success = await db.deduct_rubies(user.id, GENERATION_COST)
            
            if success:
                await db.log_generation(user.id, f"[Image-to-Image] {prompt}", GENERATION_COST)
                interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | ACTION: image_generated_from_photo | COST: {GENERATION_COST} rubies | SUCCESS")
                
                await status_message.delete()
                
                # Обрезаем промпт для caption (лимит Telegram - 1024 символа)
                short_prompt = prompt[:150] + "..." if len(prompt) > 150 else prompt
                
                await update.message.reply_photo(
                    photo=io.BytesIO(image_data),
                    caption=f"🎨 Сгенерировано на основе вашего фото\n📝 Промпт: {short_prompt}\n\n💎 Потрачено: {GENERATION_COST} рубина"
                )
                
                new_rubies = await db.get_user_rubies(user.id)
                await update.message.reply_text(f"💎 Остаток рубинов: {new_rubies}")
            else:
                await status_message.edit_text("❌ Ошибка при списании рубинов")
        else:
            await status_message.edit_text("❌ Не удалось обработать изображение. Попробуйте еще раз.")
    
    except Exception as e:
        logger.error(f"Error in process_image_generation: {e}")
        await status_message.edit_text("❌ Произошла ошибка при генерации изображения. Попробуйте позже.")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений для генерации изображений и покупки рубинов"""
    user = update.effective_user
    text = update.message.text

    # Гарантируем, что пользователь существует в БД (например, если не нажимал /start)
    await db.get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name
    )
    
    # Обработка кнопок главного меню
    if text == "🎨 Генерация":
        await generate_command(update, context)
        return
    elif text == "🤖 Модели":
        await models_command(update, context)
        return
    elif text == "👤 Профиль":
        await profile(update, context)
        return
    elif text == "💎 Купить рубины":
        await buy_rubies(update, context)
        return
    elif text == "💸 Отправить рубины":
        await update.message.reply_text(
            "💸 Отправка рубинов\n\n"
            "Использование: /send @username количество\n\n"
            "Примеры:\n"
            "• /send @friend 10\n"
            "• /send friend 5",
            reply_markup=get_main_menu_keyboard()
        )
        return
    elif text == "💡 Отзыв":
        await feedback_command(update, context)
        return
    elif text == "❓ Помощь":
        await help_command(update, context)
        return
    
    # Проверяем, не ожидаем ли мы промпт для нескольких изображений
    if context.user_data.get('waiting_for_images_prompt'):
        context.user_data['waiting_for_images_prompt'] = False
        input_images = context.user_data.get('input_images')
        
        if input_images:
            await process_images_generation(update, context, text, input_images)
            # Очищаем сохраненные изображения
            context.user_data.pop('input_images', None)
        else:
            await update.message.reply_text("❌ Изображения не найдены. Пожалуйста, загрузите фото заново.", reply_markup=get_main_menu_keyboard())
        return
    
    # Проверяем, не ожидаем ли мы промпт для одного изображения
    if context.user_data.get('waiting_for_image_prompt'):
        context.user_data['waiting_for_image_prompt'] = False
        input_image = context.user_data.get('input_image')
        
        if input_image:
            await process_image_generation(update, context, text, input_image)
            # Очищаем сохраненное изображение
            context.user_data.pop('input_image', None)
        else:
            await update.message.reply_text("❌ Изображение не найдено. Пожалуйста, загрузите фото заново.", reply_markup=get_main_menu_keyboard())
        return
    
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
            
            # Рассчитываем цену: 1 рубин = 1 рубль
            amount = rubies_count * RUBY_PRICE
            
            # Логируем покупку рубинов
            interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | ACTION: buy_rubies | COUNT: {rubies_count} | AMOUNT: {amount:.2f} руб.")
            
            try:
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
(1 рубин = {int(RUBY_PRICE)} рубль)

Нажмите кнопку "Оплатить" для перехода к оплате через СБП.
После оплаты нажмите "Проверить оплату".
"""
                await update.message.reply_text(payment_text, reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Ошибка при создании платежа: {e}", exc_info=True)
                await update.message.reply_text(
                    "❌ Произошла ошибка при создании платежа. "
                    "Пожалуйста, попробуйте позже или обратитесь к администратору."
                )
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
    
    # Получаем цену генерации из выбранной модели
    selected_model = get_user_selected_model(context)
    GENERATION_COST = selected_model['price_rubies'] if selected_model else 2
    model_name = selected_model['display_name'] if selected_model else "Unknown"
    
    # Проверяем баланс
    rubies = await db.get_user_rubies(user.id)
    
    if rubies < GENERATION_COST:
        interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | ACTION: generate_image | STATUS: insufficient_balance | RUBIES: {rubies}")
        await update.message.reply_text(
            f"❌ Недостаточно рубинов!\n\n"
            f"Текущий баланс: {rubies} 💎\n"
            f"Требуется: {GENERATION_COST} 💎\n\n"
        )
        return
    
    # Отправляем сообщение о начале генерации
    status_message = await update.message.reply_text("⏳ Генерирую изображение... Это может занять некоторое время.")
    
    try:
        # Генерируем изображение
        image_url = await openrouter.generate_image(prompt, model=selected_model['openrouter_name'])
        
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
            success = await db.deduct_rubies(user.id, GENERATION_COST)
            
            if success:
                # Логируем генерацию
                await db.log_generation(user.id, prompt, GENERATION_COST)
                interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | ACTION: image_generated | COST: {GENERATION_COST} rubies | SUCCESS")
                
                # Отправляем изображение
                await status_message.delete()
                
                # Обрезаем промпт для caption (лимит Telegram - 1024 символа)
                short_prompt = prompt[:150] + "..." if len(prompt) > 150 else prompt
                
                await update.message.reply_photo(
                    photo=io.BytesIO(image_data),
                    caption=f"🎨 Сгенерировано по запросу: {short_prompt}\n\n💎 Потрачено: {GENERATION_COST} рубина"
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
    try:
        await db.init_db()
        logger.info("База данных инициализирована")
    except Exception as e:
        logger.error(f"Ошибка при инициализации БД: {e}", exc_info=True)
        raise


def main():
    """Главная функция для запуска бота"""
    # Проверка наличия токенов
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не установлен!")
        return
    
    # Проверка наличия учетных данных YooKassa
    from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY
    if not YOOKASSA_SHOP_ID or not YOOKASSA_SECRET_KEY:
        logger.error("YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY должны быть установлены в .env файле!")
        logger.error("Без этих данных функция покупки рубинов работать не будет.")
        # Не прерываем запуск, так как бот может работать без покупок
    
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    
    # Регистрируем обработчики
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
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))  # Обработчик фотографий
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    logger.info("Бот запущен...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
