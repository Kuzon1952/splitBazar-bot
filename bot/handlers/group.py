from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, CommandHandler, MessageHandler,
    ConversationHandler, CallbackQueryHandler, filters
)
from bot.database.queries import (
    save_user, create_group, join_group,
    get_user_groups, get_group_members
)

# Conversation states
CHOOSING_ACTION = 0
ENTER_GROUP_NAME = 1
CHOOSE_CURRENCY = 2
ENTER_INVITE_CODE = 3
SET_PASSWORD = 4
SET_HINT = 5


async def my_groups(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    print("MY_GROUPS_TRIGGERED")
    user = update.effective_user
    save_user(
        user.id, user.username,
        user.first_name, user.last_name
    )
    groups = get_user_groups(user.id)

    keyboard = []
    if groups:
        for group in groups:
            keyboard.append([InlineKeyboardButton(
                f"🏠 {group[1]} ({group[2]})",
                callback_data=f"group_{group[0]}"
            )])

    keyboard.append([
        InlineKeyboardButton(
            "➕ Create Group",
            callback_data="create_group"
        ),
        InlineKeyboardButton(
            "🔗 Join Group",
            callback_data="join_group"
        )
    ])

    await update.message.reply_text(
        "👥 *Your Groups*\n\n" +
        (
            f"You are in {len(groups)} group(s).\n\n"
            f"Select a group or create a new one:"
            if groups else
            "You are not in any group yet.\nCreate or join one!"
        ),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return CHOOSING_ACTION


async def button_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    if query.data == "create_group":
        await query.message.reply_text(
            "🏠 *Create New Group*\n\n"
            "Enter a name for your group:",
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
        member_list = "\n".join(
            [f"👤 {m[1]}" for m in members]
        )
        await query.message.reply_text(
            f"👥 *Group Members:*\n\n{member_list}",
            parse_mode="Markdown"
        )
        return ConversationHandler.END


async def enter_group_name(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    from bot.database.queries import is_group_name_taken
    group_name = update.message.text.strip()

    if len(group_name) < 2:
        await update.message.reply_text(
            "❌ Group name too short!\n\n"
            "Please enter at least 2 characters:"
        )
        return ENTER_GROUP_NAME

    if is_group_name_taken(group_name):
        await update.message.reply_text(
            f"❌ *Group name already taken!*\n\n"
            f"'{group_name}' is already used.\n\n"
            f"Please choose a different name:",
            parse_mode="Markdown"
        )
        return ENTER_GROUP_NAME

    context.user_data['group_name'] = group_name

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "₽ Rubles", callback_data="currency_RUB"
            ),
            InlineKeyboardButton(
                "$ USD", callback_data="currency_USD"
            ),
        ],
        [
            InlineKeyboardButton(
                "€ Euro", callback_data="currency_EUR"
            ),
            InlineKeyboardButton(
                "৳ Taka", callback_data="currency_BDT"
            ),
        ]
    ])

    await update.message.reply_text(
        f"✅ Group name: *{group_name}*\n\n"
        f"Now select currency:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    return CHOOSE_CURRENCY


async def choose_currency(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    print("CLICKED:", query.data)
    query = update.callback_query
    await query.answer()

    currency = query.data.split("_")[1]
    user = query.from_user
    group_name = context.user_data.get('group_name')

    if not group_name:
        # fallback: recover from last message
        text = query.message.text

        if "Group name:" in text:
            group_name = text.split("Group name:")[1].split("\n")[0].strip()
        else:
            await query.message.reply_text(
                "⚠️ Session expired. Please try again."
            )
            return ConversationHandler.END

    save_user(
        user.id, user.username,
        user.first_name, user.last_name
    )
    result = create_group(group_name, currency, user.id)
    join_group(result[1], user.id)

    context.user_data['new_group_id'] = result[0]
    context.user_data['new_group_invite'] = result[1]
    context.user_data['new_group_name'] = group_name
    context.user_data['new_group_currency'] = currency

    await query.message.reply_text(
        f"🎉 *Group Created!*\n\n"
        f"Name        : {group_name}\n"
        f"Currency    : {currency}\n"
        f"Invite Code : `{result[1]}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔐 *Set Reset Password*\n\n"
        f"Please set a password to protect\n"
        f"group reset. You will need this\n"
        f"password every time you reset.\n\n"
        f"Enter your reset password:",
        parse_mode="Markdown"
    )
    return SET_PASSWORD


async def set_group_password(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    password = update.message.text.strip()

    if len(password) < 4:
        await update.message.reply_text(
            "❌ Password must be at least 4 characters!\n\n"
            "Enter a stronger password:"
        )
        return SET_PASSWORD

    group_id = context.user_data['new_group_id']
    from bot.database.queries import set_reset_password
    set_reset_password(group_id, password)

    await update.message.reply_text(
        f"✅ Password set!\n\n"
        f"🔐 Now set a *password hint*\n\n"
        f"This hint will help you remember\n"
        f"your password if you forget it.\n\n"
        f"Example: 'my cat name'\n"
        f"Enter your hint:",
        parse_mode="Markdown"
    )
    return SET_HINT


async def set_password_hint_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    hint = update.message.text.strip()
    group_id = context.user_data['new_group_id']
    group_name = context.user_data['new_group_name']
    currency = context.user_data['new_group_currency']
    invite_code = context.user_data['new_group_invite']

    from bot.database.queries import set_password_hint
    set_password_hint(group_id, hint)

    await update.message.reply_text(
        f"🎉 *Group Setup Complete!*\n\n"
        f"🏠 Group     : {group_name}\n"
        f"💰 Currency  : {currency}\n"
        f"🔑 Invite    : `{invite_code}`\n"
        f"🔐 Password  : set ✅\n"
        f"💡 Hint      : {hint}\n\n"
        f"⚠️ Remember your reset password!\n\n"
        f"Share invite code with your friends!",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


async def enter_invite_code(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user
    code = update.message.text.strip().upper()

    save_user(
        user.id, user.username,
        user.first_name, user.last_name
    )
    group = join_group(code, user.id)

    if group:
        await update.message.reply_text(
            f"🎉 *Successfully joined!*\n\n"
            f"Welcome to *{group[1]}*!",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "❌ Invalid invite code. Please try again."
        )
    return ConversationHandler.END


async def cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


def register_group_handlers(app):
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("^👥 My Groups$"),
                my_groups
            ),
        ],
        states={
            CHOOSING_ACTION: [
                CallbackQueryHandler(
                    button_handler,
                    pattern=r"^(create_group|join_group|group_\d+)$"
                )
            ],
            ENTER_GROUP_NAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    enter_group_name
                )
            ],
            CHOOSE_CURRENCY: [
                CallbackQueryHandler(
                    choose_currency,
                    pattern=r"^currency_(RUB|USD|EUR|BDT)$"
                )
            ],
            ENTER_INVITE_CODE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    enter_invite_code
                )
            ],
            SET_PASSWORD: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    set_group_password
                )
            ],
            SET_HINT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    set_password_hint_handler
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
        ],
        allow_reentry=True,
        per_message=False,
        conversation_timeout=300
    )
    app.add_handler(conv_handler)