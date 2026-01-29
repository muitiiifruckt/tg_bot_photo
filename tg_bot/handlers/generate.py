import asyncio
import io
import logging

import aiohttp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from tg_bot.core.config import RUBY_PRICE
from tg_bot.deps import deps_from_context, ensure_user
from tg_bot.keyboards import get_main_menu_keyboard
from tg_bot.services.generation import process_image_generation, process_images_generation
from tg_bot.services.models import get_user_selected_model
from tg_bot.state import (
    INPUT_IMAGE,
    INPUT_IMAGES,
    WAITING_FOR_FEEDBACK,
    WAITING_FOR_IMAGE_PROMPT,
    WAITING_FOR_IMAGES_PROMPT,
    WAITING_FOR_RUBIES,
)

from tg_bot.handlers.basic import feedback_command, help_command, profile, save_feedback_to_jsonl
from tg_bot.handlers.models import models_command
from tg_bot.handlers.payments import buy_rubies

logger = logging.getLogger(__name__)


async def generate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /generate."""
    d = deps_from_context(context)
    models_manager = d["models_manager"]
    interaction_logger = d["interaction_logger"]

    user = update.effective_user
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | COMMAND: /generate")

    default_model = models_manager.get_default_model()
    model_info = ""
    if default_model:
        model_info = (
            f"\n🤖 Модель: {default_model['display_name']}\n"
            f"💎 Цена: {default_model['price_rubies']} рубин{'ов' if default_model['price_rubies'] > 1 else ''}\n"
        )

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


async def handle_media_group(group_data):
    """Обработка группы фото (альбома)."""
    photos = group_data["photos"]
    caption = group_data["caption"]
    user_id = group_data["user_id"]
    update = group_data["update"]
    context = group_data["context"]
    user = update.effective_user

    context.user_data[INPUT_IMAGES] = photos
    context.user_data[WAITING_FOR_IMAGES_PROMPT] = True

    d = deps_from_context(context)
    interaction_logger = d["interaction_logger"]
    interaction_logger.info(
        f"USER: @{user.username or 'не указан'} (ID: {user_id}) | ACTION: media_group_uploaded | COUNT: {len(photos)}"
    )

    if caption:
        context.user_data[WAITING_FOR_IMAGES_PROMPT] = False
        await process_images_generation(update, context, caption, photos)
    else:
        await update.message.reply_text(
            f"📸 Получено {len(photos)} фото! Теперь отправьте описание того, что вы хотите сделать.\n\n"
            f"Примеры:\n"
            f"• 'Объедини стили этих фото'\n"
            f"• 'Сделай с 1 фото такой же стиль как на 2'\n"
            f"• 'Создай коллаж из этих изображений'",
            reply_markup=get_main_menu_keyboard(),
        )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик фотографий для генерации на основе изображения."""
    d = deps_from_context(context)
    db = d["db"]
    media_groups = d["media_groups"]
    interaction_logger = d["interaction_logger"]

    user = update.effective_user
    media_group_id = update.message.media_group_id

    await ensure_user(update, context)

    selected_model = get_user_selected_model(context)
    generation_cost = selected_model["price_rubies"] if selected_model else 2

    rubies = await db.get_user_rubies(user.id)
    if rubies < generation_cost:
        interaction_logger.info(
            f"USER: @{user.username or 'не указан'} (ID: {user.id}) | ACTION: photo_upload | STATUS: insufficient_balance"
        )
        await update.message.reply_text(
            f"❌ Недостаточно рубинов для генерации!\n\n"
            f"Текущий баланс: {rubies} 💎\n"
            f"Требуется: {generation_cost} 💎\n\n",
            reply_markup=get_main_menu_keyboard(),
        )
        return

    photo = update.message.photo[-1]
    photo_file = await photo.get_file()
    photo_bytes = await photo_file.download_as_bytearray()
    caption = update.message.caption if update.message.caption else None

    if media_group_id:
        if media_group_id not in media_groups:
            media_groups[media_group_id] = {
                "photos": [],
                "caption": caption,
                "user_id": user.id,
                "update": update,
                "context": context,
            }

        media_groups[media_group_id]["photos"].append(bytes(photo_bytes))

        if "timer" in media_groups[media_group_id]:
            media_groups[media_group_id]["timer"].cancel()

        async def process_media_group():
            await asyncio.sleep(2)
            if media_group_id in media_groups:
                group_data = media_groups.pop(media_group_id)
                await handle_media_group(group_data)

        task = asyncio.create_task(process_media_group())
        media_groups[media_group_id]["timer"] = task
        return

    context.user_data[INPUT_IMAGE] = bytes(photo_bytes)
    context.user_data[WAITING_FOR_IMAGE_PROMPT] = True
    interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | ACTION: photo_uploaded")

    if caption:
        context.user_data[WAITING_FOR_IMAGE_PROMPT] = False
        await process_image_generation(update, context, caption, bytes(photo_bytes))
        return

    await update.message.reply_text(
        "📸 Фото получено! Теперь отправьте описание того, как вы хотите изменить это изображение.\n\n"
        "Примеры:\n"
        "• 'Сделай это в стиле аниме'\n"
        "• 'Преврати это в картину маслом'\n"
        "• 'Добавь фантастические элементы'",
        reply_markup=get_main_menu_keyboard(),
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений для генерации изображений и покупки рубинов."""
    d = deps_from_context(context)
    db = d["db"]
    openrouter = d["openrouter"]
    yookassa = d["yookassa"]
    interaction_logger = d["interaction_logger"]

    user = update.effective_user
    text = update.message.text

    await ensure_user(update, context)

    # Главное меню
    if text == "🎨 Генерация":
        await generate_command(update, context)
        return
    if text == "🤖 Модели":
        await models_command(update, context)
        return
    if text == "👤 Профиль":
        await profile(update, context)
        return
    if text == "💎 Купить рубины":
        await buy_rubies(update, context)
        return
    if text == "💸 Отправить рубины":
        await update.message.reply_text(
            "💸 Отправка рубинов\n\n"
            "Использование: /send @username количество\n\n"
            "Примеры:\n"
            "• /send @friend 10\n"
            "• /send friend 5",
            reply_markup=get_main_menu_keyboard(),
        )
        return
    if text == "💡 Отзыв":
        await feedback_command(update, context)
        return
    if text == "❓ Помощь":
        await help_command(update, context)
        return

    # Ожидаем промпт для нескольких изображений
    if context.user_data.get(WAITING_FOR_IMAGES_PROMPT):
        context.user_data[WAITING_FOR_IMAGES_PROMPT] = False
        input_images = context.user_data.get(INPUT_IMAGES)
        if input_images:
            await process_images_generation(update, context, text, input_images)
            context.user_data.pop(INPUT_IMAGES, None)
        else:
            await update.message.reply_text(
                "❌ Изображения не найдены. Пожалуйста, загрузите фото заново.",
                reply_markup=get_main_menu_keyboard(),
            )
        return

    # Ожидаем промпт для одного изображения
    if context.user_data.get(WAITING_FOR_IMAGE_PROMPT):
        context.user_data[WAITING_FOR_IMAGE_PROMPT] = False
        input_image = context.user_data.get(INPUT_IMAGE)
        if input_image:
            await process_image_generation(update, context, text, input_image)
            context.user_data.pop(INPUT_IMAGE, None)
        else:
            await update.message.reply_text(
                "❌ Изображение не найдено. Пожалуйста, загрузите фото заново.",
                reply_markup=get_main_menu_keyboard(),
            )
        return

    # Ожидаем отзыв
    if context.user_data.get(WAITING_FOR_FEEDBACK):
        context.user_data[WAITING_FOR_FEEDBACK] = False
        interaction_logger.info(f"USER: @{user.username or 'не указан'} (ID: {user.id}) | FEEDBACK: {text[:100]}...")

        success = await save_feedback_to_jsonl(username=user.username, text=text, user_id=user.id)
        if success:
            await update.message.reply_text("✅ Спасибо за ваш отзыв! Мы обязательно учтем ваши пожелания. 🙏")
        else:
            await update.message.reply_text("❌ Произошла ошибка при сохранении отзыва. Попробуйте позже.")
        return

    # Ожидаем ввод количества рубинов
    if context.user_data.get(WAITING_FOR_RUBIES):
        context.user_data[WAITING_FOR_RUBIES] = False
        try:
            rubies_count = int(text.strip())
            if rubies_count <= 0:
                await update.message.reply_text("❌ Количество рубинов должно быть больше 0")
                return
            if rubies_count > 10000:
                await update.message.reply_text("❌ Максимальное количество рубинов за раз: 10000")
                return

            amount = rubies_count * RUBY_PRICE
            interaction_logger.info(
                f"USER: @{user.username or 'не указан'} (ID: {user.id}) | ACTION: buy_rubies | COUNT: {rubies_count} | AMOUNT: {amount:.2f} руб."
            )

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
            context.user_data[WAITING_FOR_RUBIES] = False

    # Обычная генерация по тексту
    prompt = text
    interaction_logger.info(
        f"USER: @{user.username or 'не указан'} (ID: {user.id}) | ACTION: generate_image | PROMPT: {text[:100]}..."
    )

    selected_model = get_user_selected_model(context)
    generation_cost = selected_model["price_rubies"] if selected_model else 2

    rubies = await db.get_user_rubies(user.id)
    if rubies < generation_cost:
        interaction_logger.info(
            f"USER: @{user.username or 'не указан'} (ID: {user.id}) | ACTION: generate_image | STATUS: insufficient_balance | RUBIES: {rubies}"
        )
        await update.message.reply_text(
            f"❌ Недостаточно рубинов!\n\n"
            f"Текущий баланс: {rubies} 💎\n"
            f"Требуется: {generation_cost} 💎\n\n"
        )
        return

    status_message = await update.message.reply_text("⏳ Генерирую изображение... Это может занять некоторое время.")

    try:
        image_url = await openrouter.generate_image(prompt, model=selected_model["openrouter_name"])
        if not image_url:
            await status_message.edit_text("❌ Ошибка при генерации изображения. Попробуйте еще раз.")
            return

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

        if not image_data:
            await status_message.edit_text("❌ Не удалось обработать изображение. Попробуйте еще раз.")
            return

        success = await db.deduct_rubies(user.id, generation_cost)
        if not success:
            await status_message.edit_text("❌ Ошибка при списании рубинов")
            return

        await db.log_generation(user.id, prompt, generation_cost)
        interaction_logger.info(
            f"USER: @{user.username or 'не указан'} (ID: {user.id}) | ACTION: image_generated | COST: {generation_cost} rubies | SUCCESS"
        )

        await status_message.delete()
        short_prompt = prompt[:150] + "..." if len(prompt) > 150 else prompt
        await update.message.reply_photo(
            photo=io.BytesIO(image_data),
            caption=f"🎨 Сгенерировано по запросу: {short_prompt}\n\n💎 Потрачено: {generation_cost} рубина",
        )

        new_rubies = await db.get_user_rubies(user.id)
        await update.message.reply_text(f"💎 Остаток рубинов: {new_rubies}")

    except Exception as e:
        logger.error(f"Error in handle_message: {e}")
        await status_message.edit_text("❌ Произошла ошибка при генерации изображения. Попробуйте позже.")

