from telegram.ext import ContextTypes

from tg_bot.deps import deps_from_context
from tg_bot.state import SELECTED_MODEL


def get_user_selected_model(context: ContextTypes.DEFAULT_TYPE):
    """Получить выбранную пользователем модель или модель по умолчанию."""
    d = deps_from_context(context)
    models_manager = d["models_manager"]

    selected_model_name = context.user_data.get(SELECTED_MODEL)
    if selected_model_name:
        model = models_manager.get_model_by_name(selected_model_name)
        if model:
            return model

    return models_manager.get_default_model()

