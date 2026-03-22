import logging
from telegram.ext import Application
from dotenv import load_dotenv
import os

from bot.handlers.start import register_start_handlers
from bot.handlers.group import register_group_handlers
from bot.handlers.expense import register_expense_handlers

load_dotenv()

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

    register_start_handlers(app)
    register_group_handlers(app)
    register_expense_handlers(app)

    logger.info("SplitBazar Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()