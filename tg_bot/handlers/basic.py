import json
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from tg_bot.core.config import FEEDBACK_PATH
from tg_bot.deps import deps_from_context, ensure_user
from tg_bot.keyboards import get_main_menu_keyboard
from tg_bot.state import WAITING_FOR_FEEDBACK

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    d = deps_from_context(context)
    db = d["db"]
    interaction_logger = d["interaction_logger"]

    user = update.effective_user
    interaction_logger.info(
        f"USER: @{user.username or 'не указан'} (ID: {user.id}) | COMMAND: /start | NAME: {user.first_name}"
    )

    await ensure_user(update, context)
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
    """Обработчик команды /help."""
    d = deps_from_context(context)
    interaction_logger = d["interaction_logger"]

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
    """Обработчик команды /profile."""
    d = deps_from_context(context)
    db = d["db"]
    interaction_logger = d["interaction_logger"]

    user = update.effective_user
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | COMMAND: /profile")

    user_data = await db.get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

    # NOTE: transfer history currently not shown in message (kept as-is)
    _ = await db.get_transfer_history(user.id, limit=5)

    profile_text = f"""
👤 Профиль пользователя

Имя: {user_data['first_name']}
Username: @{user_data['username'] or 'не указан'}
💎 Рубины: {user_data['rubies']}

"""
    await update.message.reply_text(profile_text, reply_markup=get_main_menu_keyboard())


async def save_feedback_to_jsonl(username: str, text: str, user_id: int) -> bool:
    """Сохраняет отзыв в JSONL файл."""
    feedback_file = FEEDBACK_PATH

    feedback_entry = {
        "user_id": user_id,
        "username": username or "не указан",
        "text": text,
        "timestamp": datetime.now().isoformat(),
    }

    try:
        with open(feedback_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(feedback_entry, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        logger.error(f"Error saving feedback: {e}")
        return False


async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /feedback - сбор советов для улучшения."""
    d = deps_from_context(context)
    interaction_logger = d["interaction_logger"]

    user = update.effective_user
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | COMMAND: /feedback")

    text = """
💡 Совет для улучшения бота

Мы ценим ваше мнение! Пожалуйста, отправьте ваш совет или пожелание по улучшению бота.

Ваш отзыв поможет нам сделать бота лучше! 🙏
"""
    await update.message.reply_text(text)
    context.user_data[WAITING_FOR_FEEDBACK] = True


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок."""
    logger.error(f"Update {update} caused error {context.error}")

