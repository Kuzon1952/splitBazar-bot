from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, MessageHandler, ConversationHandler,
    CallbackQueryHandler, filters, CommandHandler
)
from bot.database.queries import (
    get_user_groups, save_user, get_group_by_id,
    get_active_group_members,
    send_group_message, get_group_messages
)
from datetime import datetime

# States
SELECT_GROUP = 0
IN_CHAT = 1


async def group_chat_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user
    save_user(
        user.id, user.username,
        user.first_name, user.last_name
    )
    groups = get_user_groups(user.id)

    if not groups:
        await update.message.reply_text(
            "❌ You are not in any group yet!\n\n"
            "Create or join a group first."
        )
        return ConversationHandler.END

    keyboard = []
    for group in groups:
        keyboard.append([InlineKeyboardButton(
            f"🏠 {group[1]} ({group[2]})",
            callback_data=f"chat_group_{group[0]}"
        )])

    await update.message.reply_text(
        "💬 *Group Chat*\n\nSelect group:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_GROUP


async def select_chat_group(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    group_id = int(query.data.split("_")[2])
    context.user_data['chat_group_id'] = group_id

    await show_chat(query.message, group_id, context)
    return IN_CHAT


async def show_chat(message, group_id, context):
    group = get_group_by_id(group_id)
    messages = get_group_messages(group_id, limit=20)
    members = get_active_group_members(group_id)

    member_names = ", ".join([m[1] for m in members])

    text = f"💬 {group[1]} — Group Chat\n"
    text += f"👥 {member_names}\n"
    text += f"━━━━━━━━━━━━━━━━━━━━\n\n"

    if messages:
        for msg in messages:
            msg_time = msg[2].strftime('%H:%M')
            msg_date = msg[2].strftime('%d.%m')
            today = datetime.now().strftime('%d.%m')

            if msg_date == today:
                time_label = msg_time
            else:
                time_label = f"{msg_date} {msg_time}"

            text += (
                f"👤 {msg[3]} {time_label}\n"
                f"{msg[1]}\n\n"
            )
    else:
        text += "No messages yet. Be the first to say hello! 👋\n\n"

    text += "━━━━━━━━━━━━━━━━━━━━\n"
    text += "💬 Type your message below:"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🔄 Refresh",
            callback_data="chat_refresh"
        )],
        [InlineKeyboardButton(
            "❌ Leave Chat",
            callback_data="chat_leave"
        )],
    ])

    await message.reply_text(
        text,
        reply_markup=keyboard
    )


async def handle_chat_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
   
    menu_buttons = ["➕ Add Expense", "📊 View Report", "✏️ Edit Expense",
        "👥 My Groups", "🎯 My Target", "💬 Group Chat", "📝 ToDo List", "⚙️ Settings"]

    if update.message.text in menu_buttons:
        context.user_data.clear()  # ← exit chat state
        return ConversationHandler.END  # ← free the user

    user = update.effective_user
    group_id = context.user_data.get('chat_group_id')

    if not group_id:
        await update.message.reply_text(
            "❌ Please select a group first!"
        )
        return ConversationHandler.END

    message_text = update.message.text
    group = get_group_by_id(group_id)

    send_group_message(group_id, user.id, message_text)

    members = get_active_group_members(group_id)
    for member in members:
        if member[0] != user.id:
            try:
                await context.bot.send_message(
                    chat_id=member[0],
                    text=(
                        f"💬 *[{group[1]}]*\n\n"
                        f"👤 *{user.first_name}*:\n"
                        f"{message_text}"
                    ),
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    await update.message.reply_text(
        f"✅ Message sent to {group[1]}!"
    )
    return IN_CHAT


async def handle_chat_action(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    action = query.data.split("_")[1]
    group_id = context.user_data.get('chat_group_id')

    if action == "refresh":
        await show_chat(query.message, group_id, context)
        return IN_CHAT

    elif action == "leave":
        context.user_data.clear()
        await query.message.reply_text(
            "👋 Left the chat. Use 💬 Group Chat to rejoin!"
        )
        return ConversationHandler.END

    return IN_CHAT


async def cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


def register_chat_handlers(app):
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("^💬 Group Chat$"),
                group_chat_start
            )
        ],
        states={
            SELECT_GROUP: [
                CallbackQueryHandler(
                    select_chat_group,
                    pattern="^chat_group_"
                )
            ],
            IN_CHAT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    handle_chat_message
                ),
                CallbackQueryHandler(
                    handle_chat_action,
                    pattern="^chat_"
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
        allow_reentry=True
    )
    app.add_handler(conv_handler)