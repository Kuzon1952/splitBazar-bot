import logging
from telegram.ext import Application
from dotenv import load_dotenv
import os

from bot.handlers.start import register_start_handlers

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError("BOT_TOKEN not found in .env file!")

    app = Application.builder().token(token).build()

    # Register handlers
    register_start_handlers(app)

    logger.info("SplitBazar Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()