from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler


# Main menu keyboard
def main_menu_keyboard():
    keyboard = [
        ["➕ Add Expense", "📊 View Report"],
        ["👥 My Groups", "🎯 My Target"],
        ["⚙️ Settings"]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Welcome to *SplitBazar*, {user.first_name}!\n\n"
        f"I help groups track shared expenses and calculate who owes whom.\n\n"
        f"*What would you like to do?*",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "*SplitBazar Commands:*\n\n"
        "/start — Main menu\n"
        "/help — Show this message\n\n"
        "*How to use:*\n"
        "1. Create or join a group\n"
        "2. Add your expenses\n"
        "3. View report to see who owes whom",
        parse_mode="Markdown"
    )


def register_start_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))