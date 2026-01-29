import logging

from telegram import Update
from telegram.ext import ContextTypes

from tg_bot.deps import deps_from_context, ensure_user

logger = logging.getLogger(__name__)


async def send_rubies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /send - отправка рубинов другому пользователю."""
    d = deps_from_context(context)
    db = d["db"]
    interaction_logger = d["interaction_logger"]

    user = update.effective_user
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | COMMAND: /send")

    await ensure_user(update, context)

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

    recipient_username = context.args[0].lstrip("@")

    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Неверное количество рубинов. Укажите число.")
        return

    if amount <= 0:
        await update.message.reply_text("❌ Количество рубинов должно быть больше 0")
        return

    sender_balance = await db.get_user_rubies(user.id)
    if sender_balance < amount:
        await update.message.reply_text(
            f"❌ Недостаточно рубинов!\n\n"
            f"Ваш баланс: {sender_balance} 💎\n"
            f"Требуется: {amount} 💎\n\n"
        )
        return

    recipient = await db.get_user_by_username(recipient_username)
    if not recipient:
        await update.message.reply_text(
            f"❌ Пользователь @{recipient_username} не найден.\n\n"
            f"Убедитесь, что:\n"
            f"• Никнейм указан правильно\n"
            f"• Пользователь уже запускал этого бота (/start)"
        )
        return

    if recipient["user_id"] == user.id:
        await update.message.reply_text("❌ Нельзя отправить рубины самому себе!")
        return

    success = await db.transfer_rubies(user.id, recipient["user_id"], amount)
    if not success:
        await update.message.reply_text("❌ Ошибка при выполнении перевода. Попробуйте позже.")
        return

    new_balance = await db.get_user_rubies(user.id)
    recipient_new_balance = await db.get_user_rubies(recipient["user_id"])
    recipient_name = f"@{recipient['username']}" if recipient["username"] else recipient["first_name"]

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

    try:
        sender_name = f"@{user.username}" if user.username else user.first_name
        await context.bot.send_message(
            chat_id=recipient["user_id"],
            text=(
                "🎁 Вы получили перевод!\n\n"
                f"От: {sender_name}\n"
                f"Сумма: {amount} 💎\n\n"
                f"Ваш новый баланс: {recipient_new_balance} 💎"
            ),
        )
    except Exception as e:
        logger.error(f"Не удалось отправить уведомление получателю: {e}")

