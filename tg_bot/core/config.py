import os

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    # `python-dotenv` is optional: config can work from environment variables only.
    def load_dotenv(*args, **kwargs):  # type: ignore
        return False

load_dotenv()

# Telegram Bot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# OpenRouter API
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash-image")

# YooKassa
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

# Pricing - 1 рубин = 1 рубль
RUBY_PRICE = float(os.getenv("RUBY_PRICE", "1"))

# Database
# NOTE: docker-compose already sets DATABASE_PATH; we respect it here.
DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join("data", "bot_database.db"))

# Data files
FEEDBACK_PATH = os.getenv("FEEDBACK_PATH", os.path.join("data", "feedback.jsonl"))

