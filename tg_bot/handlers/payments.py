import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from tg_bot.core.config import RUBY_PRICE
from tg_bot.deps import deps_from_context, ensure_user

logger = logging.getLogger(__name__)


async def buy_rubies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /buy - покупка рубинов."""
    d = deps_from_context(context)
    interaction_logger = d["interaction_logger"]

    user = update.effective_user
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | COMMAND: /buy")

    text = f"""
💎 Пополнение баланса рубинов

Цена: 1 рубин = {int(RUBY_PRICE)} рубль

Введите количество рубинов, которое хотите купить (например: 10, 50, 100)

Или выберите готовый вариант:
"""

    keyboard = [
        [InlineKeyboardButton("💎 10 рубинов - 10 руб.", callback_data="buy_10")],
        [InlineKeyboardButton("💎 50 рубинов - 50 руб.", callback_data="buy_50")],
        [InlineKeyboardButton("💎 100 рубинов - 100 руб.", callback_data="buy_100")],
        [InlineKeyboardButton("💎 200 рубинов - 200 руб.", callback_data="buy_200")],
    ]
    inline_keyboard = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(text, reply_markup=inline_keyboard)
    context.user_data["waiting_for_rubies"] = True


async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик callback для покупки рубинов."""
    d = deps_from_context(context)
    db = d["db"]
    yookassa = d["yookassa"]
    interaction_logger = d["interaction_logger"]

    query = update.callback_query
    await query.answer()

    user = update.effective_user
    data = query.data
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | CALLBACK: {data}")

    await ensure_user(update, context)

    try:
        rubies_count = int(data.replace("buy_", ""))
    except ValueError:
        await query.edit_message_text("❌ Неверный формат")
        return

    if rubies_count <= 0:
        await query.edit_message_text("❌ Количество рубинов должно быть больше 0")
        return

    amount = rubies_count * RUBY_PRICE

    try:
        payment_info = yookassa.create_payment(amount=amount, user_id=user.id, rubies=rubies_count)

        await db.create_payment(
            payment_id=payment_info["payment_id"],
            user_id=user.id,
            amount=amount,
            rubies=rubies_count,
        )

        keyboard = [
            [InlineKeyboardButton("💳 Оплатить", url=payment_info["confirmation_url"])],
            [InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_{payment_info['payment_id']}")],
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
    """Обработчик проверки оплаты."""
    d = deps_from_context(context)
    db = d["db"]
    yookassa = d["yookassa"]
    interaction_logger = d["interaction_logger"]

    query = update.callback_query
    await query.answer()

    user = update.effective_user
    payment_id = query.data.replace("check_", "")
    interaction_logger.info(
        f"USER: @{user.username or 'не указан'} (ID: {user.id}) | CALLBACK: check_payment | PAYMENT_ID: {payment_id}"
    )

    await ensure_user(update, context)

    payment_data = await db.get_payment(payment_id)
    if not payment_data:
        await query.edit_message_text("❌ Платеж не найден")
        return

    yookassa_status = yookassa.check_payment_status(payment_id)

    if yookassa_status and yookassa_status["paid"]:
        if payment_data["status"] != "succeeded":
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

