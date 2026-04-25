from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, MessageHandler, ConversationHandler,
    CallbackQueryHandler, filters, CommandHandler
)
from bot.database.queries import (
    get_user_groups, set_budget_target,
    get_budget_target, get_user_spending_this_month
)
from datetime import datetime

# States
SELECT_GROUP = 0
ENTER_TARGET = 1


async def my_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    groups = get_user_groups(user.id)

    if not groups:
        await update.message.reply_text(
            "❌ You are not in any group yet!\n\n"
            "Please create or join a group first."
        )
        return ConversationHandler.END

    now = datetime.now()
    month = now.month
    year = now.year

    # Show current targets for all groups
    text = "🎯 *My Budget Targets*\n\n"

    for group in groups:
        target = get_budget_target(user.id, group[0], month, year)
        spent = get_user_spending_this_month(
            user.id, group[0], month, year
        )

        if target:
            percentage = (spent / float(target)) * 100
            if percentage >= 100:
                status = "🚨 EXCEEDED"
            elif percentage >= 80:
                status = "⚠️ Near limit"
            else:
                status = "✅ On track"

            bar = get_progress_bar(percentage)

            text += (
                f"🏠 *{group[1]}*\n"
                f"   Target : {float(target):.2f} {group[2]}\n"
                f"   Spent  : {spent:.2f} {group[2]}\n"
                f"   Left   : {max(0, float(target)-spent):.2f} {group[2]}\n"
                f"   {bar} {percentage:.1f}%\n"
                f"   Status : {status}\n\n"
            )
        else:
            text += (
                f"🏠 *{group[1]}*\n"
                f"   No target set yet\n\n"
            )

    keyboard = []
    for group in groups:
        keyboard.append([InlineKeyboardButton(
            f"🎯 Set target for {group[1]}",
            callback_data=f"target_group_{group[0]}"
        )])

    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_GROUP


def get_progress_bar(percentage):
    filled = int(min(percentage, 100) / 10)
    empty = 10 - filled
    if percentage >= 100:
        return "🟥" * 10
    elif percentage >= 80:
        return "🟨" * filled + "⬜" * empty
    else:
        return "🟩" * filled + "⬜" * empty


async def select_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    group_id = int(query.data.split("_")[2])
    context.user_data['target_group_id'] = group_id

    now = datetime.now()
    user = query.from_user

    current_target = get_budget_target(
        user.id, group_id, now.month, now.year
    )
    current_spent = get_user_spending_this_month(
        user.id, group_id, now.month, now.year
    )

    text = (
        f"🎯 *Set Budget Target*\n\n"
        f"Month: {now.strftime('%B %Y')}\n\n"
    )

    if current_target:
        text += (
            f"Current target : {float(current_target):.2f}\n"
            f"Already spent  : {current_spent:.2f}\n\n"
        )

    text += "Enter your new budget target amount:"

    await query.message.reply_text(
        text,
        parse_mode="Markdown"
    )
    return ENTER_TARGET


async def enter_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    menu_buttons = ["➕ Add Expense", "📊 View Report", "✏️ Edit Expense",
    "👥 My Groups", "🎯 My Target", "💬 Group Chat", "📝 ToDo List", "⚙️ Settings"]

    if update.message.text in menu_buttons:
        await update.message.reply_text("⚠️ Please don't use menu buttons during this step!")
        return ENTER_TARGET # 👈 change this to match the current state
    
    try:
        amount = float(update.message.text.strip())
        if amount <= 0:
            await update.message.reply_text(
                "❌ Amount must be greater than 0!"
            )
            return ENTER_TARGET

        user = update.effective_user
        group_id = context.user_data['target_group_id']
        now = datetime.now()

        set_budget_target(
            user.id, group_id,
            amount, now.month, now.year
        )

        current_spent = get_user_spending_this_month(
            user.id, group_id, now.month, now.year
        )

        percentage = (current_spent / amount) * 100
        bar = get_progress_bar(percentage)

        await update.message.reply_text(
            f"✅ *Budget Target Set!*\n\n"
            f"Month  : {now.strftime('%B %Y')}\n"
            f"Target : {amount:.2f}\n"
            f"Spent  : {current_spent:.2f}\n"
            f"Left   : {max(0, amount-current_spent):.2f}\n\n"
            f"{bar} {percentage:.1f}%\n\n"
            f"You will get alerts at:\n"
            f"⚠️ 80% — {amount * 0.8:.2f}\n"
            f"🚨 100% — {amount:.2f}",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    except ValueError:
        await update.message.reply_text(
            "❌ Please enter a valid number.\n"
            "Example: `5000`",
            parse_mode="Markdown"
        )
        return ENTER_TARGET


async def check_budget_alert(
    context, user_id, group_id, currency
):
    """Call this after every expense to check budget"""
    now = datetime.now()
    target = get_budget_target(
        user_id, group_id, now.month, now.year
    )

    if not target:
        return

    spent = get_user_spending_this_month(
        user_id, group_id, now.month, now.year
    )
    percentage = (spent / target) * 100

    if percentage >= 100:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"🚨 *Budget Exceeded!*\n\n"
                f"Target : {target:.2f} {currency}\n"
                f"Spent  : {spent:.2f} {currency}\n"
                f"Over by: {spent-target:.2f} {currency}\n\n"
                f"You have exceeded your monthly budget!"
            ),
            parse_mode="Markdown"
        )
    elif percentage >= 80:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"⚠️ *Budget Warning!*\n\n"
                f"Target : {target:.2f} {currency}\n"
                f"Spent  : {spent:.2f} {currency}\n"
                f"Left   : {target-spent:.2f} {currency}\n\n"
                f"You have used {percentage:.1f}% of your budget!"
            ),
            parse_mode="Markdown"
        )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END



async def end_conversation(update, context):
    context.user_data.clear()
    return -1  # ConversationHandler.END

def register_target_handlers(app):
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🎯 My Target$"), my_target),
            MessageHandler(filters.Regex("^➕ Add Expense$"), end_conversation),
            MessageHandler(filters.Regex("^📊 View Report$"), end_conversation),
            MessageHandler(filters.Regex("^✏️ Edit Expense$"), end_conversation),
            MessageHandler(filters.Regex("^👥 My Groups$"), end_conversation),
            MessageHandler(filters.Regex("^💬 Group Chat$"), end_conversation),
            MessageHandler(filters.Regex("^📝 ToDo List$"), end_conversation),
            MessageHandler(filters.Regex("^⚙️ Settings$"), end_conversation),
        ],
        states={
            SELECT_GROUP: [
                CallbackQueryHandler(
                    select_group, pattern="^target_group_"
                )
            ],
            ENTER_TARGET: [
                MessageHandler(filters.Regex("^➕ Add Expense$"), end_conversation),
                MessageHandler(filters.Regex("^📊 View Report$"), end_conversation),
                MessageHandler(filters.Regex("^✏️ Edit Expense$"), end_conversation),
                MessageHandler(filters.Regex("^👥 My Groups$"), end_conversation),
                MessageHandler(filters.Regex("^🎯 My Target$"), end_conversation),
                MessageHandler(filters.Regex("^💬 Group Chat$"), end_conversation),
                MessageHandler(filters.Regex("^📝 ToDo List$"), end_conversation),
                MessageHandler(filters.Regex("^⚙️ Settings$"), end_conversation),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    enter_target
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
        ],
        allow_reentry=True
    )
    app.add_handler(conv_handler)