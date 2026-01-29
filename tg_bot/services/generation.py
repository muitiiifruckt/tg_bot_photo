import io
import logging

import aiohttp
from telegram import Update
from telegram.ext import ContextTypes

from tg_bot.deps import deps_from_context
from tg_bot.keyboards import get_main_menu_keyboard
from tg_bot.services.models import get_user_selected_model

logger = logging.getLogger(__name__)


async def process_images_generation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    input_images: list,
):
    """Обработка генерации изображения на основе нескольких входных изображений."""
    d = deps_from_context(context)
    db = d["db"]
    openrouter = d["openrouter"]
    interaction_logger = d["interaction_logger"]

    user = update.effective_user
    if not user:
        return

    selected_model = get_user_selected_model(context)
    generation_cost = selected_model["price_rubies"] if selected_model else 2

    interaction_logger.info(
        f"USER: @{user.username or 'не указан'} (ID: {user.id}) | "
        f"ACTION: generate_from_images | COUNT: {len(input_images)} | PROMPT: {prompt[:100]}..."
    )

    status_message = await update.message.reply_text(
        f"⏳ Генерирую изображение на основе {len(input_images)} фото... Это может занять некоторое время."
    )

    try:
        image_url = await openrouter.generate_image(
            prompt,
            input_images=input_images,
            model=selected_model["openrouter_name"],
        )

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

        await db.log_generation(user.id, f"[Multi-Image] {prompt}", generation_cost)
        interaction_logger.info(
            f"USER: @{user.username or 'не указан'} (ID: {user.id}) | "
            f"ACTION: image_generated_from_photos | COST: {generation_cost} rubies | SUCCESS"
        )

        await status_message.delete()

        short_prompt = prompt[:150] + "..." if len(prompt) > 150 else prompt
        await update.message.reply_photo(
            photo=io.BytesIO(image_data),
            caption=(
                f"🎨 Сгенерировано на основе {len(input_images)} фото\n"
                f"📝 Промпт: {short_prompt}\n\n"
                f"💎 Потрачено: {generation_cost} рубин{'ов' if generation_cost > 1 else ''}"
            ),
            reply_markup=get_main_menu_keyboard(),
        )

        new_rubies = await db.get_user_rubies(user.id)
        await update.message.reply_text(f"💎 Остаток рубинов: {new_rubies}", reply_markup=get_main_menu_keyboard())

    except Exception as e:
        logger.error(f"Error in process_images_generation: {e}")
        await status_message.edit_text("❌ Произошла ошибка при генерации изображения. Попробуйте позже.")


async def process_image_generation(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    prompt: str,
    input_image: bytes,
):
    """Обработка генерации изображения на основе входного."""
    d = deps_from_context(context)
    db = d["db"]
    openrouter = d["openrouter"]
    interaction_logger = d["interaction_logger"]

    user = update.effective_user
    if not user:
        return

    selected_model = get_user_selected_model(context)
    generation_cost = selected_model["price_rubies"] if selected_model else 2

    interaction_logger.info(
        f"USER: @{user.username or 'не указан'} (ID: {user.id}) | "
        f"ACTION: generate_from_image | PROMPT: {prompt[:100]}..."
    )

    status_message = await update.message.reply_text(
        "⏳ Генерирую изображение на основе вашего фото... Это может занять некоторое время."
    )

    try:
        image_url = await openrouter.generate_image(
            prompt,
            input_image=input_image,
            model=selected_model["openrouter_name"],
        )

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

        await db.log_generation(user.id, f"[Image-to-Image] {prompt}", generation_cost)
        interaction_logger.info(
            f"USER: @{user.username or 'не указан'} (ID: {user.id}) | "
            f"ACTION: image_generated_from_photo | COST: {generation_cost} rubies | SUCCESS"
        )

        await status_message.delete()

        short_prompt = prompt[:150] + "..." if len(prompt) > 150 else prompt
        await update.message.reply_photo(
            photo=io.BytesIO(image_data),
            caption=(
                f"🎨 Сгенерировано на основе вашего фото\n"
                f"📝 Промпт: {short_prompt}\n\n"
                f"💎 Потрачено: {generation_cost} рубина"
            ),
        )

        new_rubies = await db.get_user_rubies(user.id)
        await update.message.reply_text(f"💎 Остаток рубинов: {new_rubies}")

    except Exception as e:
        logger.error(f"Error in process_image_generation: {e}")
        await status_message.edit_text("❌ Произошла ошибка при генерации изображения. Попробуйте позже.")

