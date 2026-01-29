from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from tg_bot.deps import deps_from_context, ensure_user
from tg_bot.state import SELECTED_MODEL


async def models_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /models - показать доступные модели с кнопками выбора."""
    d = deps_from_context(context)
    models_manager = d["models_manager"]
    interaction_logger = d["interaction_logger"]

    user = update.effective_user
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | COMMAND: /models")

    await ensure_user(update, context)

    current_model = context.user_data.get(SELECTED_MODEL)
    if not current_model:
        default = models_manager.get_default_model()
        current_model = default["openrouter_name"] if default else None

    models_text = "🤖 Доступные модели:\n\n"
    keyboard = []

    for model in models_manager.get_enabled_models():
        is_current = model["openrouter_name"] == current_model
        icon = "✅" if is_current else "⚪"

        models_text += f"{icon} **{model['display_name']}**\n"
        models_text += f"   {model['description']}\n"
        models_text += f"   💎 Цена: {model['price_rubies']} рубин{'ов' if model['price_rubies'] > 1 else ''}\n\n"

        button_text = f"{'✅' if is_current else '⚪'} {model['display_name']} - {model['price_rubies']} 💎"
        keyboard.append(
            [
                InlineKeyboardButton(
                    button_text,
                    callback_data=f"select_model_{model['openrouter_name']}",
                )
            ]
        )

    models_text += "👆 Нажмите на модель, чтобы выбрать её для генерации"
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(models_text, reply_markup=reply_markup, parse_mode="Markdown")


async def select_model_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик выбора модели."""
    d = deps_from_context(context)
    models_manager = d["models_manager"]
    interaction_logger = d["interaction_logger"]

    query = update.callback_query
    await query.answer()

    user = update.effective_user
    model_name = query.data.replace("select_model_", "")
    model = models_manager.get_model_by_name(model_name)

    if model:
        context.user_data[SELECTED_MODEL] = model_name

        interaction_logger.info(
            f"USER: @{user.username or 'не указан'} (ID: {user.id}) | ACTION: select_model | MODEL: {model['display_name']}"
        )

        await query.edit_message_text(
            f"✅ Выбрана модель: **{model['display_name']}**\n\n"
            f"📝 {model['description']}\n\n"
            f"💎 Цена генерации: {model['price_rubies']} рубин{'ов' if model['price_rubies'] > 1 else ''}\n\n"
            f"Теперь все ваши генерации будут использовать эту модель.",
            parse_mode="Markdown",
        )
    else:
        await query.edit_message_text("❌ Модель не найдена")

