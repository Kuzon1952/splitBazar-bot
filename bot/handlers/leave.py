from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, MessageHandler, ConversationHandler,
    CallbackQueryHandler, filters, CommandHandler
)
from bot.database.queries import (
    get_user_groups, get_group_by_id,
    get_active_group_members, leave_group,
    get_frozen_balance, remove_member,
    get_group_admin
)
from datetime import datetime

# States
SELECT_GROUP = 0
CONFIRM_REQUEST = 1
SELECT_MEMBER = 2
CONFIRM_REMOVE = 3


# ─── LEAVE GROUP (needs admin approval) ──────────────────

async def leave_group_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user
    groups = get_user_groups(user.id)

    if not groups:
        await update.message.reply_text(
            "❌ You are not in any group!"
        )
        return ConversationHandler.END

    keyboard = []
    for group in groups:
        # Don't show groups where user is admin
        if group[4] != user.id:
            keyboard.append([InlineKeyboardButton(
                f"🏠 {group[1]} ({group[2]})",
                callback_data=f"leave_group_{group[0]}"
            )])

    if not keyboard:
        await update.message.reply_text(
            "❌ You are admin of all your groups!\n\n"
            "Admins cannot leave their own group.\n"
            "Transfer admin role first or delete the group."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "❌ *Leave Group*\n\nSelect group to leave:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_GROUP


async def select_group_leave(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    group_id = int(query.data.split("_")[2])
    context.user_data['leave_group_id'] = group_id

    user = query.from_user
    group = get_group_by_id(group_id)
    currency = group[2]
    balance_data = get_frozen_balance(group_id, user.id)
    balance = balance_data['balance']

    if balance > 0.01:
        balance_text = (
            f"💚 Group owes you: {balance:.2f} {currency}"
        )
    elif balance < -0.01:
        balance_text = (
            f"⚠️ You owe group: {abs(balance):.2f} {currency}"
        )
    else:
        balance_text = "✅ You are settled!"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "📨 Send Request",
            callback_data="sendleave_yes"
        )],
        [InlineKeyboardButton(
            "❌ Cancel",
            callback_data="sendleave_no"
        )],
    ])

    await query.message.reply_text(
        f"⚠️ *Leave Request*\n\n"
        f"You want to leave *{group[1]}*.\n\n"
        f"Your current balance:\n"
        f"{balance_text}\n\n"
        f"Your request will be sent to the\n"
        f"admin for approval.\n\n"
        f"Send leave request?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    return CONFIRM_REQUEST


async def send_leave_request(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    if query.data == "sendleave_no":
        await query.message.reply_text("❌ Cancelled.")
        return ConversationHandler.END

    user = query.from_user
    group_id = context.user_data['leave_group_id']
    group = get_group_by_id(group_id)
    currency = group[2]
    admin_id = get_group_admin(group_id)

    balance_data = get_frozen_balance(group_id, user.id)
    balance = balance_data['balance']

    if balance > 0.01:
        balance_text = (
            f"💚 Group owes {user.first_name}: "
            f"{balance:.2f} {currency}"
        )
    elif balance < -0.01:
        balance_text = (
            f"⚠️ {user.first_name} owes group: "
            f"{abs(balance):.2f} {currency}"
        )
    else:
        balance_text = "✅ Settled!"

    # Notify admin
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Approve",
                callback_data=(
                    f"adminleave_approve_"
                    f"{group_id}_{user.id}"
                )
            ),
            InlineKeyboardButton(
                "❌ Reject",
                callback_data=(
                    f"adminleave_reject_"
                    f"{group_id}_{user.id}"
                )
            ),
        ]
    ])

    try:
        await context.bot.send_message(
            chat_id=admin_id,
            text=(
                f"🔔 *[{group[1]}] Leave Request!*\n\n"
                f"👤 *{user.first_name}* wants to "
                f"leave the group.\n\n"
                f"Current balance:\n"
                f"{balance_text}\n\n"
                f"Date: "
                f"{datetime.now().strftime('%d.%m.%Y')}"
            ),
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    except Exception as e:
        await query.message.reply_text(
            "❌ Could not reach admin. Try again later."
        )
        return ConversationHandler.END

    await query.message.reply_text(
        f"✅ *Leave request sent to admin!*\n\n"
        f"You will be notified when admin responds.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


async def admin_respond_leave(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    action = parts[1]
    group_id = int(parts[2])
    member_id = int(parts[3])

    group = get_group_by_id(group_id)
    currency = group[2]
    balance_data = get_frozen_balance(group_id, member_id)
    balance = balance_data['balance']

    members = get_active_group_members(group_id)
    member_name = next(
        (m[1] for m in members if m[0] == member_id),
        "Unknown"
    )

    if action == "approve":
        # Remove member from group
        leave_group(group_id, member_id)

        await query.message.reply_text(
            f"✅ *{member_name}'s leave approved!*\n\n"
            f"Balance frozen: {balance:+.2f} {currency}",
            parse_mode="Markdown"
        )

        # Notify the member
        if balance > 0.01:
            balance_text = (
                f"💚 Group owes you: {balance:.2f} {currency}"
            )
        elif balance < -0.01:
            balance_text = (
                f"⚠️ You owe group: "
                f"{abs(balance):.2f} {currency}"
            )
        else:
            balance_text = "✅ You are settled!"

        try:
            await context.bot.send_message(
                chat_id=member_id,
                text=(
                    f"✅ *Admin approved your leave request!*\n\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"📊 Final Balance — {member_name}\n"
                    f"Left: {datetime.now().strftime('%d.%m.%Y')}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"Shared paid    : "
                    f"{balance_data['paid']:.2f} {currency}\n"
                    f"Your fair share: "
                    f"{balance_data['share']:.2f} {currency}\n"
                    f"Balance        : {balance:+.2f} {currency}\n\n"
                    f"{balance_text}\n\n"
                    f"Record frozen ✅\n"
                    f"Report automatically split at "
                    f"{datetime.now().strftime('%d.%m.%Y')}"
                ),
                parse_mode="Markdown"
            )
        except Exception:
            pass

        # Notify all remaining members
        remaining = get_active_group_members(group_id)
        for member in remaining:
            if member[0] != query.from_user.id:
                try:
                    await context.bot.send_message(
                        chat_id=member[0],
                        text=(
                            f"🚪 *[{group[1]}]*\n\n"
                            f"*{member_name}* has left "
                            f"the group!\n"
                            f"Balance frozen: "
                            f"{balance:+.2f} {currency}\n\n"
                            f"⚠️ Please settle before "
                            f"end of period!\n\n"
                            f"📅 Report automatically split at "
                            f"{datetime.now().strftime('%d.%m.%Y')}"
                        ),
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

    else:
        # Rejected
        await query.message.reply_text(
            f"❌ *{member_name}'s leave request rejected.*",
            parse_mode="Markdown"
        )

        try:
            await context.bot.send_message(
                chat_id=member_id,
                text=(
                    f"❌ *Admin rejected your leave request.*\n\n"
                    f"You are still in *{group[1]}*.\n"
                    f"Contact your admin for more info."
                ),
                parse_mode="Markdown"
            )
        except Exception:
            pass


# ─── REMOVE MEMBER (Admin only) ──────────────────────────

async def remove_member_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user
    groups = get_user_groups(user.id)

    admin_groups = [g for g in groups if g[4] == user.id]

    if not admin_groups:
        await update.message.reply_text(
            "❌ You are not an admin of any group!"
        )
        return ConversationHandler.END

    keyboard = []
    for group in admin_groups:
        keyboard.append([InlineKeyboardButton(
            f"👑 {group[1]} ({group[2]})",
            callback_data=f"removegrp_{group[0]}"
        )])

    await update.message.reply_text(
        "🚪 *Remove Member*\n\nSelect group:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_GROUP


async def select_group_remove(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    group_id = int(query.data.split("_")[1])
    context.user_data['remove_group_id'] = group_id

    user = query.from_user
    members = get_active_group_members(group_id)
    members = [m for m in members if m[0] != user.id]

    if not members:
        await query.message.reply_text(
            "❌ No members to remove!"
        )
        return ConversationHandler.END

    keyboard = []
    for member in members:
        keyboard.append([InlineKeyboardButton(
            f"👤 {member[1]}",
            callback_data=f"removemember_{member[0]}"
        )])

    await query.message.reply_text(
        "Select member to remove:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_MEMBER


async def select_member_remove(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    member_id = int(query.data.split("_")[1])
    context.user_data['remove_member_id'] = member_id

    group_id = context.user_data['remove_group_id']
    group = get_group_by_id(group_id)
    currency = group[2]

    balance_data = get_frozen_balance(group_id, member_id)
    balance = balance_data['balance']

    members = get_active_group_members(group_id)
    member_name = next(
        (m[1] for m in members if m[0] == member_id),
        "Unknown"
    )
    context.user_data['remove_member_name'] = member_name

    if balance > 0.01:
        balance_text = (
            f"💚 Group owes them: {balance:.2f} {currency}"
        )
    elif balance < -0.01:
        balance_text = (
            f"⚠️ They owe group: {abs(balance):.2f} {currency}"
        )
    else:
        balance_text = "✅ Settled!"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "✅ Yes, Remove",
            callback_data="confirmremove_yes"
        )],
        [InlineKeyboardButton(
            "❌ Cancel",
            callback_data="confirmremove_no"
        )],
    ])

    await query.message.reply_text(
        f"🚪 *Remove {member_name}?*\n\n"
        f"⚠️ Their balance will be frozen.\n\n"
        f"Current balance:\n"
        f"{balance_text}\n\n"
        f"Are you sure?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    return CONFIRM_REMOVE


async def confirm_remove(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    if query.data == "confirmremove_no":
        await query.message.reply_text("❌ Cancelled.")
        return ConversationHandler.END

    admin = query.from_user
    group_id = context.user_data['remove_group_id']
    member_id = context.user_data['remove_member_id']
    member_name = context.user_data['remove_member_name']
    group = get_group_by_id(group_id)
    currency = group[2]

    balance_data = get_frozen_balance(group_id, member_id)
    balance = balance_data['balance']

    # Remove member
    remove_member(group_id, member_id, admin.id)

    # Notify removed member
    if balance > 0.01:
        balance_text = (
            f"💚 Group owes you: {balance:.2f} {currency}"
        )
    elif balance < -0.01:
        balance_text = (
            f"⚠️ You owe group: {abs(balance):.2f} {currency}"
        )
    else:
        balance_text = "✅ You are settled!"

    try:
        await context.bot.send_message(
            chat_id=member_id,
            text=(
                f"🚪 *You were removed from {group[1]}*\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 Final Balance\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"Shared paid    : "
                f"{balance_data['paid']:.2f} {currency}\n"
                f"Your fair share: "
                f"{balance_data['share']:.2f} {currency}\n"
                f"Balance        : {balance:+.2f} {currency}\n\n"
                f"{balance_text}\n\n"
                f"Record frozen ✅\n"
                f"Report split at "
                f"{datetime.now().strftime('%d.%m.%Y')}"
            ),
            parse_mode="Markdown"
        )
    except Exception:
        pass

    await query.message.reply_text(
        f"✅ *{member_name} removed from {group[1]}!*\n\n"
        f"Balance frozen: {balance:+.2f} {currency}",
        parse_mode="Markdown"
    )

    # Notify remaining members
    members = get_active_group_members(group_id)
    for member in members:
        if member[0] != admin.id:
            try:
                await context.bot.send_message(
                    chat_id=member[0],
                    text=(
                        f"🚪 *[{group[1]}]*\n\n"
                        f"*{member_name}* was removed "
                        f"by admin.\n"
                        f"Balance frozen: "
                        f"{balance:+.2f} {currency}\n\n"
                        f"📅 Report split at "
                        f"{datetime.now().strftime('%d.%m.%Y')}"
                    ),
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    return ConversationHandler.END


async def cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


def register_leave_handlers(app):
    # Leave group conversation
    leave_conv = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("^❌ Leave Group$"),
                leave_group_start
            )
        ],
        states={
            SELECT_GROUP: [
                CallbackQueryHandler(
                    select_group_leave,
                    pattern="^leave_group_"
                )
            ],
            CONFIRM_REQUEST: [
                CallbackQueryHandler(
                    send_leave_request,
                    pattern="^sendleave_"
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
        allow_reentry=True
    )

    # Remove member conversation
    remove_conv = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("^🚪 Remove Member$"),
                remove_member_start
            )
        ],
        states={
            SELECT_GROUP: [
                CallbackQueryHandler(
                    select_group_remove,
                    pattern="^removegrp_"
                )
            ],
            SELECT_MEMBER: [
                CallbackQueryHandler(
                    select_member_remove,
                    pattern="^removemember_"
                )
            ],
            CONFIRM_REMOVE: [
                CallbackQueryHandler(
                    confirm_remove,
                    pattern="^confirmremove_"
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
        allow_reentry=True
    )

    app.add_handler(leave_conv)
    app.add_handler(remove_conv)
    app.add_handler(
        CallbackQueryHandler(
            admin_respond_leave,
            pattern="^adminleave_"
        )
    )