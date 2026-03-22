from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, CommandHandler, MessageHandler,
    ConversationHandler, CallbackQueryHandler, filters
)
from bot.database.queries import (
    save_user, create_group, join_group, get_user_groups, get_group_members
)

# Conversation states
CHOOSING_ACTION = 0
ENTER_GROUP_NAME = 1
CHOOSE_CURRENCY = 2
ENTER_INVITE_CODE = 3


async def my_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.username, user.first_name, user.last_name)

    groups = get_user_groups(user.id)

    keyboard = []
    if groups:
        for group in groups:
            keyboard.append([InlineKeyboardButton(
                f"🏠 {group[1]} ({group[2]})",
                callback_data=f"group_{group[0]}"
            )])

    keyboard.append([
        InlineKeyboardButton("➕ Create Group", callback_data="create_group"),
        InlineKeyboardButton("🔗 Join Group", callback_data="join_group")
    ])

    await update.message.reply_text(
        "👥 *Your Groups*\n\n" +
        (f"You are in {len(groups)} group(s).\n\nSelect a group or create a new one:"
         if groups else "You are not in any group yet.\nCreate or join one!"),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "create_group":
        await query.message.reply_text(
            "🏠 *Create New Group*\n\nEnter a name for your group:",
            parse_mode="Markdown"
        )
        return ENTER_GROUP_NAME

    elif query.data == "join_group":
        await query.message.reply_text(
            "🔗 *Join a Group*\n\nEnter the invite code:",
            parse_mode="Markdown"
        )
        return ENTER_INVITE_CODE

    elif query.data.startswith("group_"):
        group_id = int(query.data.split("_")[1])
        members = get_group_members(group_id)
        member_list = "\n".join([f"👤 {m[1]}" for m in members])
        await query.message.reply_text(
            f"👥 *Group Members:*\n\n{member_list}",
            parse_mode="Markdown"
        )
        return ConversationHandler.END


async def enter_group_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['group_name'] = update.message.text

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("₽ Rubles", callback_data="currency_RUB"),
            InlineKeyboardButton("$ USD", callback_data="currency_USD"),
        ],
        [
            InlineKeyboardButton("€ Euro", callback_data="currency_EUR"),
            InlineKeyboardButton("৳ Taka", callback_data="currency_BDT"),
        ]
    ])

    await update.message.reply_text(
        f"✅ Group name: *{update.message.text}*\n\nNow select currency:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    return CHOOSE_CURRENCY


async def choose_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    currency = query.data.split("_")[1]
    user = query.from_user
    group_name = context.user_data.get('group_name')

    save_user(user.id, user.username, user.first_name, user.last_name)
    result = create_group(group_name, currency, user.id)

    # Also add creator as member
    join_group(result[1], user.id)

    await query.message.reply_text(
        f"🎉 *Group Created!*\n\n"
        f"Name     : {group_name}\n"
        f"Currency : {currency}\n"
        f"Invite Code : `{result[1]}`\n\n"
        f"Share this code with your friends to join!",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


async def enter_invite_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    code = update.message.text.strip().upper()

    save_user(user.id, user.username, user.first_name, user.last_name)
    group = join_group(code, user.id)

    if group:
        await update.message.reply_text(
            f"🎉 *Successfully joined!*\n\nWelcome to *{group[1]}*!",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "❌ Invalid invite code. Please try again."
        )
    return ConversationHandler.END


def register_group_handlers(app):
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^👥 My Groups$"), my_groups),
            CallbackQueryHandler(button_handler, pattern="^(create_group|join_group|group_)")
        ],
        states={
            ENTER_GROUP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_group_name)],
            CHOOSE_CURRENCY: [CallbackQueryHandler(choose_currency, pattern="^currency_")],
            ENTER_INVITE_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_invite_code)],
        },
        fallbacks=[]
    )
    app.add_handler(conv_handler)