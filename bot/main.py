import logging
from telegram.ext import Application
from dotenv import load_dotenv
import os

from bot.handlers.start import register_start_handlers
from bot.handlers.group import register_group_handlers
from bot.handlers.expense import register_expense_handlers
from bot.handlers.report import register_report_handlers
from bot.handlers.edit import register_edit_handlers
from bot.handlers.target import register_target_handlers
from bot.handlers.notifications import setup_notifications
from bot.handlers.leave import register_leave_handlers
from bot.handlers.settings import register_settings_handlers
from bot.handlers.todo import register_todo_handlers
from bot.handlers.reset import register_reset_handlers
from bot.handlers.chat import register_chat_handlers

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
    register_chat_handlers(app)
    register_group_handlers(app)
    register_expense_handlers(app)
    register_report_handlers(app)
    register_edit_handlers(app)
    register_target_handlers(app)
    setup_notifications(app)
    register_leave_handlers(app)
    register_settings_handlers(app)
    register_todo_handlers(app)
    register_reset_handlers(app)

    logger.info("SplitBazar Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()