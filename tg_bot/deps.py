from __future__ import annotations

from typing import Any, Dict, TypedDict

from telegram import Update
from telegram.ext import ContextTypes

from tg_bot.clients.openrouter_client import OpenRouterClient
from tg_bot.db.database import Database
from tg_bot.models.models_manager import ModelsManager
from tg_bot.payments.yookassa_payment import YooKassaPayment

from tg_bot.logging_setup import setup_logging


class BotDeps(TypedDict):
    db: Database
    openrouter: OpenRouterClient
    yookassa: YooKassaPayment
    models_manager: ModelsManager
    interaction_logger: Any
    media_groups: Dict[str, Any]


def init_deps() -> BotDeps:
    """Create singleton dependencies for the bot runtime."""
    interaction_logger = setup_logging()
    return {
        "db": Database(),
        "openrouter": OpenRouterClient(),
        "yookassa": YooKassaPayment(),
        "models_manager": ModelsManager(),
        "interaction_logger": interaction_logger,
        "media_groups": {},
    }


def deps_from_context(context: ContextTypes.DEFAULT_TYPE) -> BotDeps:
    return context.application.bot_data  # type: ignore[return-value]


async def ensure_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ensure user exists in DB (if they never pressed /start)."""
    user = update.effective_user
    if not user:
        return
    d = deps_from_context(context)
    await d["db"].get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
    )

