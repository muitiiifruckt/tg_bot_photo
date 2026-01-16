import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# OpenRouter API
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = "google/gemini-3-pro-image-preview"

# YooKassa
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

# Pricing
PRICE_PER_GENERATION = int(os.getenv("PRICE_PER_GENERATION", "10"))

# Database
DATABASE_PATH = "bot_database.db"
