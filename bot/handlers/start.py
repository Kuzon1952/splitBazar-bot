from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ContextTypes, CommandHandler,
    MessageHandler, filters
)
from bot.database.queries import save_user


def main_menu_keyboard():
    keyboard = [
        ["➕ Add Expense",  "📊 View Report"],
        ["✏️ Edit Expense", "👥 My Groups"],
        ["🎯 My Target",    "💬 Group Chat"],
        ["📝 ToDo List",    "⚙️ Settings"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user
    save_user(
        user.id, user.username,
        user.first_name, user.last_name
    )

    await update.message.reply_text(
        f"👋 *Welcome to SplitBazar, {user.first_name}!*\n\n"
        f"I help groups track shared expenses\n"
        f"and calculate who owes whom.\n\n"
        f"🚀 *Getting Started:*\n"
        f"1️⃣ Press 👥 *My Groups* to create your group\n"
        f"2️⃣ Share invite code with your roommates\n"
        f"3️⃣ Press ➕ *Add Expense* to log purchases\n"
        f"4️⃣ Press 📊 *View Report* to see who owes whom\n\n"
        f"💡 Type /help for full guide\n"
        f"💡 Type /info for about this bot\n\n"
        f"*What would you like to do?*",
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "📖 *SplitBazar Help Guide*\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🏠 *GROUPS*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "1. Press 👥 My Groups\n"
        "2. Press ➕ Create Group\n"
        "3. Enter name → select currency\n"
        "4. Set reset password + hint\n"
        "5. Share invite code with friends\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "➕ *ADD EXPENSE*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "1. Press ➕ Add Expense\n"
        "2. Select group\n"
        "3. Select date\n"
        "4. Choose type:\n"
        "   🍽️ Shared = split among everyone\n"
        "   👤 Personal = only for you\n"
        "   🔀 Mixed = partly shared\n"
        "5. Enter amount + description\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📊 *VIEW REPORT*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "1. Press 📊 View Report\n"
        "2. Select period\n"
        "3. See who paid what\n"
        "4. Download PDF or Excel\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🎯 *BUDGET TARGET*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "1. Press 🎯 My Target\n"
        "2. Set monthly budget\n"
        "3. Get warning at 80%\n"
        "4. Get alert when exceeded\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔄 *MONTHLY RESET*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "1. Go to ⚙️ Settings\n"
        "2. Press 🔄 Reset Group\n"
        "3. Enter password\n"
        "4. Fresh start! 🎉\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "📬 Contact: @virtual786",
        parse_mode="Markdown"
    )


async def info_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "ℹ️ *About SplitBazar*\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 Bot        : SplitBazar\n"
        "📌 Version    : 1.0.0\n"
        "👨‍💻 Developer  : Ovi Md Shamin Yasir\n"
        "🎓 University : SPbPU\n"
        "📚 Subject    : Digital Analytics\n"
        "🎓 Year       : 2nd year, 2026\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "👨‍🏫 *Supervisor:*\n"
        "Vladimir Alexandrovich Mulyukha\n"
        "PhD in Technical Sciences\n"
        "Director — Higher School of\n"
        "AI Technologies, SPbPU\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💡 *What is SplitBazar?*\n\n"
        "SplitBazar helps groups track\n"
        "shared expenses and calculate\n"
        "who owes whom. Perfect for\n"
        "roommates, trips and shared\n"
        "living expenses.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🛠️ *Features:*\n"
        "✅ Group expense tracking\n"
        "✅ Smart split calculation\n"
        "✅ PDF and Excel reports\n"
        "✅ Budget targets and alerts\n"
        "✅ Shopping ToDo list\n"
        "✅ Group chat\n"
        "✅ Monthly reset system\n"
        "✅ Notifications\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📬 *Contact:* @virtual786\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Press /start to begin! 🚀",
        parse_mode="Markdown"
    )


def register_start_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("info", info_command))