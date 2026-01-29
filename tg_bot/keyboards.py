from telegram import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Создает главное меню с кнопками."""
    keyboard = [
        [KeyboardButton("🎨 Генерация"), KeyboardButton("🤖 Модели")],
        [KeyboardButton("👤 Профиль"), KeyboardButton("💎 Купить рубины")],
        [KeyboardButton("💸 Отправить рубины"), KeyboardButton("💡 Отзыв")],
        [KeyboardButton("❓ Помощь")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

