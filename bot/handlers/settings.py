from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, MessageHandler, ConversationHandler,
    CallbackQueryHandler, filters, CommandHandler
)
from bot.database.queries import (
    get_user_groups, get_group_by_id,
    get_active_group_members, get_group_admin,
    transfer_admin, generate_new_invite_code,
    get_user_expense_history, get_user_summary,
    get_budget_target, get_user_spending_this_month,
    get_deleted_expenses, remove_member,
    get_frozen_balance, leave_group,
    get_notification_settings,
    update_notification_settings
)
from datetime import datetime

# States
SELECT_GROUP = 0
SHOW_MENU = 1
SELECT_NEW_ADMIN = 2
CONFIRM_TRANSFER = 3
SELECT_REMOVE_MEMBER = 4
CONFIRM_REMOVE = 5
CONFIRM_LEAVE = 6
SEND_LEAVE_REQUEST = 7
VERIFY_RESET_PASSWORD = 10


async def settings_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user
    groups = get_user_groups(user.id)

    if not groups:
        await update.message.reply_text(
            "❌ You are not in any group yet!\n\n"
            "Create or join a group first."
        )
        return ConversationHandler.END

    keyboard = []
    for group in groups:
        is_admin = group[4] == user.id
        label = (
            f"👑 {group[1]} (Admin)"
            if is_admin
            else f"🏠 {group[1]}"
        )
        keyboard.append([InlineKeyboardButton(
            label,
            callback_data=f"settings_group_{group[0]}"
        )])

    await update.message.reply_text(
        "⚙️ *Settings*\n\nSelect group:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_GROUP


async def show_settings_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    group_id = int(query.data.split("_")[2])
    context.user_data['settings_group_id'] = group_id

    user = query.from_user
    group = get_group_by_id(group_id)
    is_admin = group[4] == user.id

    # Member buttons
    keyboard = [
        [InlineKeyboardButton(
            "📊 My Summary",
            callback_data="set_summary"
        )],
        [InlineKeyboardButton(
            "🔔 Notifications",
            callback_data="set_notifications"
        )],
        [InlineKeyboardButton(
            "📅 My History",
            callback_data="set_history"
        )],
        [InlineKeyboardButton(
            "❌ Leave Group",
            callback_data="set_leave"
        )],
    ]

    # Admin only buttons
    if is_admin:
        keyboard.append([InlineKeyboardButton(
            "── Admin Only ──",
            callback_data="set_nothing"
        )])
        keyboard.append([InlineKeyboardButton(
            "🔑 New Invite Code",
            callback_data="set_invitecode"
        )])
        keyboard.append([InlineKeyboardButton(
            "👑 Transfer Admin",
            callback_data="set_transferadmin"
        )])
        keyboard.append([InlineKeyboardButton(
            "🚪 Remove Member",
            callback_data="set_removemember"
        )])
        keyboard.append([InlineKeyboardButton(
            "🗑️ Deleted Log",
            callback_data="set_deletedlog"
        )])
        keyboard.append([InlineKeyboardButton(
            "🔄 Reset Group",
            callback_data="set_reset"
        )])

    await query.message.reply_text(
        f"⚙️ *{group[1]} Settings*\n\n"
        f"{'👑 You are admin' if is_admin else '👤 Member'}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SHOW_MENU


async def handle_settings_action(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    action = query.data.split("_")[1]
    group_id = context.user_data['settings_group_id']
    user = query.from_user
    group = get_group_by_id(group_id)
    currency = group[2]

    # ── My Summary ───────────────────────────────────────
    if action == "summary":
        now = datetime.now()
        summary = get_user_summary(user.id, group_id)
        target = get_budget_target(
            user.id, group_id, now.month, now.year
        )
        spent = get_user_spending_this_month(
            user.id, group_id, now.month, now.year
        )

        if target:
            percentage = (spent / float(target)) * 100
            target_text = (
                f"🎯 Budget Target : "
                f"{float(target):.2f} {currency}\n"
                f"💸 Spent         : {spent:.2f} {currency}\n"
                f"📊 Used          : {percentage:.1f}%\n"
                f"💰 Remaining     : "
                f"{max(0, float(target)-spent):.2f} {currency}"
            )
        else:
            target_text = "🎯 No budget target set"

        if summary['balance'] > 0.01:
            balance_text = (
                f"💚 Group owes you: "
                f"{summary['balance']:.2f} {currency}"
            )
        elif summary['balance'] < -0.01:
            balance_text = (
                f"⚠️ You owe group: "
                f"{abs(summary['balance']):.2f} {currency}"
            )
        else:
            balance_text = "✅ You are settled!"

        await query.message.reply_text(
            f"📊 *My Summary — {group[1]}*\n"
            f"📅 {now.strftime('%B %Y')}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Total spent   : "
            f"{summary['total_spent']:.2f} {currency}\n"
            f"🍽️ Shared paid   : "
            f"{summary['shared_spent']:.2f} {currency}\n"
            f"📐 Fair share    : "
            f"{summary['fair_share']:.2f} {currency}\n\n"
            f"{balance_text}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{target_text}",
            parse_mode="Markdown"
        )
        return SHOW_MENU

    # ── Notifications ────────────────────────────────────
    elif action == "notifications":
        settings = get_notification_settings(user.id)
        inactivity = settings[0] if settings else True
        large_exp = settings[1] if settings else True

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                f"😴 Inactivity: "
                f"{'✅ ON' if inactivity else '❌ OFF'}",
                callback_data="notif_inactivity"
            )],
            [InlineKeyboardButton(
                f"💸 Large Expense: "
                f"{'✅ ON' if large_exp else '❌ OFF'}",
                callback_data="notif_largeexp"
            )],
        ])

        await query.message.reply_text(
            "🔔 *Notification Settings*\n\n"
            "Toggle your notifications:",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return SHOW_MENU

    # ── My History ───────────────────────────────────────
    elif action == "history":
        history = get_user_expense_history(
            user.id, group_id
        )

        if not history:
            await query.message.reply_text(
                "📅 No expense history yet!"
            )
            return SHOW_MENU

        text = f"📅 *My Last 10 Expenses*\n"
        text += f"🏠 {group[1]}\n"
        text += f"━━━━━━━━━━━━━━━━━━━━\n\n"

        for exp in history:
            text += (
                f"📌 {exp[6]}\n"
                f"   💰 {exp[1]:.2f} {currency} "
                f"| {exp[4]}\n"
                f"   📝 {exp[5] or 'No description'}\n\n"
            )

        await query.message.reply_text(
            text, parse_mode="Markdown"
        )
        return SHOW_MENU

    # ── Leave Group ──────────────────────────────────────
    elif action == "leave":
        is_admin = group[4] == user.id
        if is_admin:
            await query.message.reply_text(
                "❌ *You are the admin!*\n\n"
                "You cannot leave your own group.\n"
                "Please transfer admin role first.",
                parse_mode="Markdown"
            )
            return SHOW_MENU

        balance_data = get_frozen_balance(
            group_id, user.id
        )
        balance = balance_data['balance']

        if balance > 0.01:
            balance_text = (
                f"💚 Group owes you: "
                f"{balance:.2f} {currency}"
            )
        elif balance < -0.01:
            balance_text = (
                f"⚠️ You owe group: "
                f"{abs(balance):.2f} {currency}"
            )
        else:
            balance_text = "✅ You are settled!"

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "📨 Send Request",
                callback_data="leavereq_yes"
            )],
            [InlineKeyboardButton(
                "❌ Cancel",
                callback_data="leavereq_no"
            )],
        ])

        await query.message.reply_text(
            f"⚠️ *Leave Request — {group[1]}*\n\n"
            f"Your current balance:\n"
            f"{balance_text}\n\n"
            f"Your request will be sent to admin\n"
            f"for approval.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return SEND_LEAVE_REQUEST

    # ── New Invite Code ──────────────────────────────────
    elif action == "invitecode":
        new_code = generate_new_invite_code(group_id)
        await query.message.reply_text(
            f"🔑 *New Invite Code Generated!*\n\n"
            f"Old code: expired ❌\n"
            f"New code: `{new_code}` ✅\n\n"
            f"Share this with your friends!",
            parse_mode="Markdown"
        )
        return SHOW_MENU

    # ── Transfer Admin ───────────────────────────────────
    elif action == "transferadmin":
        members = get_active_group_members(group_id)
        members = [
            m for m in members if m[0] != user.id
        ]

        if not members:
            await query.message.reply_text(
                "❌ No other members to transfer to!"
            )
            return SHOW_MENU

        keyboard = []
        for member in members:
            keyboard.append([InlineKeyboardButton(
                f"👤 {member[1]}",
                callback_data=f"newadmin_{member[0]}"
            )])

        await query.message.reply_text(
            "👑 *Transfer Admin*\n\n"
            "Select new admin:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_NEW_ADMIN

    # ── Remove Member ────────────────────────────────────
    elif action == "removemember":
        members = get_active_group_members(group_id)
        members = [
            m for m in members if m[0] != user.id
        ]

        if not members:
            await query.message.reply_text(
                "❌ No members to remove!"
            )
            return SHOW_MENU

        keyboard = []
        for member in members:
            keyboard.append([InlineKeyboardButton(
                f"👤 {member[1]}",
                callback_data=f"setremove_{member[0]}"
            )])

        await query.message.reply_text(
            "🚪 *Remove Member*\n\nSelect member:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_REMOVE_MEMBER

    # ── Deleted Log ──────────────────────────────────────
    elif action == "deletedlog":
        deleted = get_deleted_expenses(group_id)

        if not deleted:
            await query.message.reply_text(
                "✅ No deleted expenses in last 3 months!"
            )
            return SHOW_MENU

        for exp in deleted:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "🔄 Restore",
                    callback_data=f"setrestore_{exp[0]}"
                )]
            ])
            await query.message.reply_text(
                f"❌ *DELETED*\n\n"
                f"👤 Owner      : {exp[8]}\n"
                f"🗑️ Deleted by : {exp[9]}\n"
                f"💰 Amount     : {exp[2]}\n"
                f"📝 Description: {exp[5] or 'None'}\n"
                f"📅 Date       : {exp[6]}\n"
                f"🕐 Deleted at : "
                f"{exp[7].strftime('%d.%m.%Y %H:%M')}\n"
                f"⏳ Auto delete: in 3 months",
                parse_mode="Markdown",
                reply_markup=keyboard
            )
        return SHOW_MENU

    # ── Reset Group ──────────────────────────────────────
    elif action == "reset":
        await query.message.reply_text(
            f"🔄 *Reset Group — {group[1]}?*\n\n"
            f"⚠️ This cannot be undone!\n\n"
            f"🔐 Enter your reset password to continue:",
            parse_mode="Markdown"
        )
        context.user_data['settings_resetting'] = True
        return VERIFY_RESET_PASSWORD

    elif action == "nothing":
        return SHOW_MENU

    return SHOW_MENU


async def handle_notification_toggle(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    notif_type = query.data.split("_")[1]
    settings = get_notification_settings(user.id)
    inactivity = settings[0] if settings else True
    large_exp = settings[1] if settings else True

    if notif_type == "inactivity":
        inactivity = not inactivity
    elif notif_type == "largeexp":
        large_exp = not large_exp

    update_notification_settings(
        user.id, inactivity, large_exp
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"😴 Inactivity: "
            f"{'✅ ON' if inactivity else '❌ OFF'}",
            callback_data="notif_inactivity"
        )],
        [InlineKeyboardButton(
            f"💸 Large Expense: "
            f"{'✅ ON' if large_exp else '❌ OFF'}",
            callback_data="notif_largeexp"
        )],
    ])

    await query.message.edit_reply_markup(
        reply_markup=keyboard
    )


async def handle_new_admin(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    new_admin_id = int(query.data.split("_")[1])
    group_id = context.user_data['settings_group_id']
    group = get_group_by_id(group_id)
    user = query.from_user

    members = get_active_group_members(group_id)
    new_admin_name = next(
        (m[1] for m in members if m[0] == new_admin_id),
        "Unknown"
    )
    context.user_data['new_admin_id'] = new_admin_id
    context.user_data['new_admin_name'] = new_admin_name

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "✅ Yes, Transfer",
            callback_data="confirmtransfer_yes"
        )],
        [InlineKeyboardButton(
            "❌ Cancel",
            callback_data="confirmtransfer_no"
        )],
    ])

    await query.message.reply_text(
        f"👑 *Transfer Admin to {new_admin_name}?*\n\n"
        f"You will become a regular member.\n"
        f"{new_admin_name} will become admin.\n\n"
        f"Are you sure?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    return CONFIRM_TRANSFER


async def confirm_transfer(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    if query.data == "confirmtransfer_no":
        await query.message.reply_text("❌ Cancelled.")
        return ConversationHandler.END

    group_id = context.user_data['settings_group_id']
    new_admin_id = context.user_data['new_admin_id']
    new_admin_name = context.user_data['new_admin_name']
    group = get_group_by_id(group_id)
    user = query.from_user

    transfer_admin(group_id, new_admin_id)

    await query.message.reply_text(
        f"✅ *Admin transferred!*\n\n"
        f"👑 {new_admin_name} is now the admin "
        f"of {group[1]}!\n"
        f"You are now a regular member.",
        parse_mode="Markdown"
    )

    # Notify new admin
    try:
        await context.bot.send_message(
            chat_id=new_admin_id,
            text=(
                f"👑 *You are now admin of {group[1]}!*\n\n"
                f"{user.first_name} transferred admin "
                f"role to you."
            ),
            parse_mode="Markdown"
        )
    except Exception:
        pass

    return ConversationHandler.END


async def handle_remove_member(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    member_id = int(query.data.split("_")[1])
    group_id = context.user_data['settings_group_id']
    group = get_group_by_id(group_id)
    currency = group[2]

    balance_data = get_frozen_balance(group_id, member_id)
    balance = balance_data['balance']

    members = get_active_group_members(group_id)
    member_name = next(
        (m[1] for m in members if m[0] == member_id),
        "Unknown"
    )
    context.user_data['setremove_id'] = member_id
    context.user_data['setremove_name'] = member_name

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "✅ Yes, Remove",
            callback_data="setconfirmremove_yes"
        )],
        [InlineKeyboardButton(
            "❌ Cancel",
            callback_data="setconfirmremove_no"
        )],
    ])

    await query.message.reply_text(
        f"🚪 *Remove {member_name}?*\n\n"
        f"Balance: {balance:+.2f} {currency}\n\n"
        f"Are you sure?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    return CONFIRM_REMOVE


async def confirm_remove_member(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    if query.data == "setconfirmremove_no":
        await query.message.reply_text("❌ Cancelled.")
        return ConversationHandler.END

    admin = query.from_user
    group_id = context.user_data['settings_group_id']
    member_id = context.user_data['setremove_id']
    member_name = context.user_data['setremove_name']
    group = get_group_by_id(group_id)
    currency = group[2]

    balance_data = get_frozen_balance(group_id, member_id)
    balance = balance_data['balance']

    remove_member(group_id, member_id, admin.id)

    await query.message.reply_text(
        f"✅ *{member_name} removed!*\n\n"
        f"Balance frozen: {balance:+.2f} {currency}",
        parse_mode="Markdown"
    )

    try:
        await context.bot.send_message(
            chat_id=member_id,
            text=(
                f"🚪 *You were removed from {group[1]}*\n\n"
                f"Balance frozen: {balance:+.2f} {currency}"
            ),
            parse_mode="Markdown"
        )
    except Exception:
        pass

    return ConversationHandler.END


async def handle_restore(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    from bot.database.queries import restore_expense, get_expense_by_id
    expense_id = int(query.data.split("_")[1])
    restore_expense(expense_id)
    expense = get_expense_by_id(expense_id)

    await query.message.reply_text(
        f"✅ *Expense restored!*\n\n"
        f"👤 {expense[8]} — {expense[2]}\n"
        f"📝 {expense[6] or 'No description'}\n"
        f"Now visible in reports again.",
        parse_mode="Markdown"
    )
    return SHOW_MENU


async def handle_leave_request(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    if query.data == "leavereq_no":
        await query.message.reply_text("❌ Cancelled.")
        return ConversationHandler.END

    user = query.from_user
    group_id = context.user_data['settings_group_id']
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
                f"👤 *{user.first_name}* wants to leave.\n\n"
                f"Balance:\n{balance_text}\n\n"
                f"Date: "
                f"{datetime.now().strftime('%d.%m.%Y')}"
            ),
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        await query.message.reply_text(
            "✅ *Leave request sent to admin!*\n\n"
            "You will be notified when admin responds.",
            parse_mode="Markdown"
        )
    except Exception:
        await query.message.reply_text(
            "❌ Could not reach admin. Try again later."
        )

    return ConversationHandler.END


async def cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


async def verify_reset_password_settings(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    from bot.database.queries import (
        verify_reset_password, archive_expenses,
        update_group_last_reset, set_group_locked,
        get_first_expense_date, get_balances,
        get_expenses_for_report
    )
    from bot.utils.calculations import (
        calculate_balances, calculate_settlements
    )

    password = update.message.text.strip()
    group_id = context.user_data['settings_group_id']
    group = get_group_by_id(group_id)
    members = get_active_group_members(group_id)

    is_correct = verify_reset_password(group_id, password)

    if not is_correct:
        await update.message.reply_text(
            "❌ *Wrong password!*\n\n"
            "Reset cancelled for security.\n"
            "Please try again from Settings.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    # Password correct — proceed with reset
    await update.message.reply_text(
        "✅ Password correct!\n\n"
        "⏳ Processing reset..."
    )

    now = datetime.now()
    first_date = get_first_expense_date(group_id)
    start_date = first_date if first_date else now.replace(day=1)
    period_label = (
        f"{start_date.strftime('%d.%m.%Y')} → "
        f"{now.strftime('%d.%m.%Y')}"
    )
    currency = group[2]

    expenses, splits = get_balances(
        group_id, start_date, now
    )

    if expenses:
        balances = calculate_balances(expenses, splits)
        settlements = calculate_settlements(balances)

        report = f"📊 FINAL REPORT — {group[1]}\n"
        report += f"📅 {period_label}\n"
        report += f"━━━━━━━━━━━━━━━━━━━━\n\n"

        for user_id, data in balances.items():
            emoji = "✅" if abs(data['balance']) < 0.01 else (
                "💚" if data['balance'] > 0 else "⚠️"
            )
            report += (
                f"{emoji} {data['name']}\n"
                f"   Balance: {data['balance']:+.2f} {currency}\n\n"
            )

        if settlements:
            report += "💸 Settlement:\n"
            for s in settlements:
                report += (
                    f"{s['from_name']} → {s['to_name']}: "
                    f"{s['amount']:.2f} {currency}\n"
                )

        for member in members:
            try:
                await context.bot.send_message(
                    chat_id=member[0],
                    text=report
                )
            except Exception:
                pass

    archive_expenses(group_id)
    update_group_last_reset(group_id)
    set_group_locked(group_id, False)

    for member in members:
        try:
            await context.bot.send_message(
                chat_id=member[0],
                text=(
                    f"✅ [{group[1]}] Group Reset!\n\n"
                    f"New period: {now.strftime('%d.%m.%Y')}\n"
                    f"Fresh start! 🎉"
                )
            )
        except Exception:
            pass

    await update.message.reply_text(
        f"✅ *Group Reset Complete!*\n\n"
        f"Fresh start! 🎉",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

def register_settings_handlers(app):
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("^⚙️ Settings$"),
                settings_start
            )
        ],
        states={
            SELECT_GROUP: [
                CallbackQueryHandler(
                    show_settings_menu,
                    pattern="^settings_group_"
                )
            ],
            SHOW_MENU: [
                CallbackQueryHandler(
                    handle_settings_action,
                    pattern="^set_"
                ),
                CallbackQueryHandler(
                    handle_notification_toggle,
                    pattern="^notif_"
                ),
                CallbackQueryHandler(
                    handle_restore,
                    pattern="^setrestore_"
                ),
            ],
            SELECT_NEW_ADMIN: [
                CallbackQueryHandler(
                    handle_new_admin,
                    pattern="^newadmin_"
                )
            ],
            CONFIRM_TRANSFER: [
                CallbackQueryHandler(
                    confirm_transfer,
                    pattern="^confirmtransfer_"
                )
            ],
            SELECT_REMOVE_MEMBER: [
                CallbackQueryHandler(
                    handle_remove_member,
                    pattern="^setremove_"
                )
            ],
            CONFIRM_REMOVE: [
                CallbackQueryHandler(
                    confirm_remove_member,
                    pattern="^setconfirmremove_"
                )
            ],
            SEND_LEAVE_REQUEST: [
                CallbackQueryHandler(
                    handle_leave_request,
                    pattern="^leavereq_"
                )
            ],
            VERIFY_RESET_PASSWORD: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    verify_reset_password_settings
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
        allow_reentry=True
    )
    app.add_handler(conv_handler)