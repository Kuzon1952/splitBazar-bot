from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters
)
from bot.database.queries import (
    save_user, create_group, join_group,
    get_user_groups, get_group_members
)


async def my_groups(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
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


async def button_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    if query.data == "create_group":
        context.user_data['group_state'] = 'enter_name'
        await query.message.reply_text(
            "🏠 *Create New Group*\n\n"
            "Enter a name for your group:",
            parse_mode="Markdown"
        )

    elif query.data == "join_group":
        context.user_data['group_state'] = 'enter_invite'
        await query.message.reply_text(
            "🔗 *Join a Group*\n\nEnter the invite code:",
            parse_mode="Markdown"
        )

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

    elif query.data.startswith("currency_"):
        currency = query.data.split("_")[1]
        user = query.from_user
        group_name = context.user_data.get('group_name')

        if not group_name:
            await query.message.reply_text(
                "❌ Session expired. Please try again."
            )
            context.user_data.clear()
            return

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
        context.user_data['group_state'] = 'set_password'

        await query.message.reply_text(
            f"🎉 *Group Created!*\n\n"
            f"Name        : {group_name}\n"
            f"Currency    : {currency}\n"
            f"Invite Code : `{result[1]}`\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔐 *Set Reset Password*\n\n"
            f"Please set a password to protect\n"
            f"group reset.\n\n"
            f"Enter your reset password:",
            parse_mode="Markdown"
        )


async def handle_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    state = context.user_data.get('group_state')

    if state == 'enter_name':
        from bot.database.queries import is_group_name_taken
        group_name = update.message.text.strip()

        if len(group_name) < 2:
            await update.message.reply_text(
                "❌ Group name too short!\n\n"
                "Please enter at least 2 characters:"
            )
            return

        if is_group_name_taken(group_name):
            await update.message.reply_text(
                f"❌ *Group name already taken!*\n\n"
                f"'{group_name}' is already used.\n\n"
                f"Please choose a different name:",
                parse_mode="Markdown"
            )
            return

        context.user_data['group_name'] = group_name
        context.user_data['group_state'] = 'choose_currency'

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

    elif state == 'enter_invite':
        user = update.effective_user
        code = update.message.text.strip().upper()
        save_user(
            user.id, user.username,
            user.first_name, user.last_name
        )
        group = join_group(code, user.id)
        context.user_data.pop('group_state', None)

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

    elif state == 'set_password':
        password = update.message.text.strip()

        if len(password) < 4:
            await update.message.reply_text(
                "❌ Password must be at least 4 characters!\n\n"
                "Enter a stronger password:"
            )
            return

        group_id = context.user_data['new_group_id']
        from bot.database.queries import set_reset_password
        set_reset_password(group_id, password)
        context.user_data['group_state'] = 'set_hint'

        await update.message.reply_text(
            f"✅ Password set!\n\n"
            f"🔐 Now set a *password hint*\n\n"
            f"This hint will help you remember\n"
            f"your password if you forget it.\n\n"
            f"Example: 'my cat name'\n"
            f"Enter your hint:",
            parse_mode="Markdown"
        )

    elif state == 'set_hint':
        hint = update.message.text.strip()
        group_id = context.user_data['new_group_id']
        group_name = context.user_data['new_group_name']
        currency = context.user_data['new_group_currency']
        invite_code = context.user_data['new_group_invite']

        from bot.database.queries import set_password_hint
        set_password_hint(group_id, hint)
        context.user_data.pop('group_state', None)

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


def register_group_handlers(app):
    app.add_handler(
        MessageHandler(
            filters.Regex("^👥 My Groups$"),
            my_groups
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            button_handler,
            pattern="^(create_group|join_group|group_|currency_)"
        )
    )
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text
        ),
        group=1
    )