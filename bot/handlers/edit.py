from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, MessageHandler, ConversationHandler,
    CallbackQueryHandler, filters, CommandHandler
)
from bot.database.queries import (
    get_user_groups, get_expenses_by_date, get_expense_by_id,
    update_expense, soft_delete_expense, get_deleted_expenses,
    restore_expense, get_group_admin, create_edit_request,
    update_edit_request, get_edit_request, get_member_join_date,
    delete_expense_splits, get_expense_splits,
    add_expense_split, get_active_members_at_date
)
from datetime import datetime, timedelta
from bot.utils.menu_guard import MENU_BUTTON_FILTER, exit_to_menu

# States
SELECT_GROUP = 0
SELECT_DATE = 1
ENTER_DATE = 2
SELECT_EXPENSE = 3
SELECT_FIELD = 4
ENTER_NEW_VALUE = 5
CONFIRM_DELETE = 6
SELECT_SPLIT_MEMBERS_EDIT = 7
ENTER_CUSTOM_PCT_EDIT = 8

# Admin states
ADMIN_DELETED_LIST = 10


async def edit_expense_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    groups = get_user_groups(user.id)

    if not groups:
        await update.message.reply_text(
            "❌ You are not in any group yet!"
        )
        return ConversationHandler.END

    keyboard = []
    for group in groups:
        keyboard.append([InlineKeyboardButton(
            f"🏠 {group[1]} ({group[2]})",
            callback_data=f"edit_group_{group[0]}"
        )])

    await update.message.reply_text(
        "✏️ *Edit Expense*\n\nSelect group:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_GROUP


async def select_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    group_id = int(query.data.split("_")[2])
    context.user_data['edit_group_id'] = group_id

    today = datetime.now()
    yesterday = today - timedelta(days=1)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"📅 Today ({today.strftime('%d.%m.%Y')})",
            callback_data="editdate_today"
        )],
        [InlineKeyboardButton(
            f"📅 Yesterday ({yesterday.strftime('%d.%m.%Y')})",
            callback_data="editdate_yesterday"
        )],
        [InlineKeyboardButton(
            "📅 Pick a date",
            callback_data="editdate_pick"
        )],
    ])

    await query.message.reply_text(
        "📅 Select date to search expenses:",
        reply_markup=keyboard
    )
    return SELECT_DATE


async def select_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    date_choice = query.data.split("_")[1]
    today = datetime.now()

    if date_choice == "today":
        context.user_data['edit_date'] = today.date()
        await show_expenses(query.message, context)
        return SELECT_EXPENSE

    elif date_choice == "yesterday":
        yesterday = today - timedelta(days=1)
        context.user_data['edit_date'] = yesterday.date()
        await show_expenses(query.message, context)
        return SELECT_EXPENSE

    elif date_choice == "pick":
        await query.message.reply_text(
            "📅 Enter date:\n\n"
            "Format: `DD.MM.YYYY`\n"
            "Example: `20.03.2026`",
            parse_mode="Markdown"
        )
        return ENTER_DATE


async def enter_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().date()

    try:
        entered_date = datetime.strptime(
            update.message.text.strip(), "%d.%m.%Y"
        ).date()
    except ValueError:
        await update.message.reply_text(
            "❌ Wrong format! Use `DD.MM.YYYY`",
            parse_mode="Markdown"
        )
        return ENTER_DATE

    if entered_date > today:
        await update.message.reply_text(
            f"❌ Cannot select future date!\n"
            f"Max: `{today.strftime('%d.%m.%Y')}`",
            parse_mode="Markdown"
        )
        return ENTER_DATE

    context.user_data['edit_date'] = entered_date
    await show_expenses(update.message, context)
    return SELECT_EXPENSE


async def show_expenses(message, context):
    group_id = context.user_data['edit_group_id']
    date = context.user_data['edit_date']

    expenses = get_expenses_by_date(group_id, date)

    if not expenses:
        await message.reply_text(
            f"❌ No expenses found on "
            f"{date.strftime('%d.%m.%Y')}"
        )
        return ConversationHandler.END

    context.user_data['edit_expenses'] = expenses

    text = f"📋 *Expenses on {date.strftime('%d.%m.%Y')}:*\n\n"
    keyboard = []

    for i, exp in enumerate(expenses, 1):
        text += (
            f"#{i} 👤 {exp[8]}\n"
            f"   💰 {exp[2]} | {exp[5]}\n"
            f"   📝 {exp[6] or 'No description'}\n\n"
        )
        keyboard.append([InlineKeyboardButton(
            f"Edit #{i}",
            callback_data=f"editexp_{exp[0]}"
        )])

    await message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def select_expense(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    expense_id = int(query.data.split("_")[1])
    expense = get_expense_by_id(expense_id)
    context.user_data['editing_expense'] = expense

    user = query.from_user
    group_id = expense[9]
    admin_id = get_group_admin(group_id)

    if expense[1] == user.id:
        await show_edit_options(query.message, expense)
        return SELECT_FIELD
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "📨 Request permission",
                callback_data=f"reqedit_{expense_id}"
            )],
            [InlineKeyboardButton(
                "❌ Cancel",
                callback_data="reqedit_cancel"
            )],
        ])
        await query.message.reply_text(
            f"🔐 *Security Check*\n\n"
            f"This expense belongs to *{expense[8]}*.\n"
            f"You need admin approval to edit it.\n\n"
            f"Send edit request to admin?",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return SELECT_FIELD


async def show_edit_options(message, expense):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Amount", callback_data="field_amount")],
        [InlineKeyboardButton("📊 Split type", callback_data="field_split")],
        [InlineKeyboardButton("📝 Description", callback_data="field_description")],
        [InlineKeyboardButton("📅 Date", callback_data="field_date")],
        [InlineKeyboardButton("🗑️ Delete", callback_data="field_delete")],
    ])

    await message.reply_text(
        f"✏️ *Editing expense:*\n\n"
        f"👤 {expense[8]}\n"
        f"💰 {expense[2]}\n"
        f"📊 {expense[5]}\n"
        f"📝 {expense[6] or 'No description'}\n"
        f"📅 {expense[7]}\n\n"
        f"What do you want to change?",
        parse_mode="Markdown",
        reply_markup=keyboard
    )


async def request_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "reqedit_cancel":
        await query.message.reply_text("❌ Cancelled.")
        return ConversationHandler.END

    expense_id = int(query.data.split("_")[1])
    expense = get_expense_by_id(expense_id)
    group_id = expense[9]
    admin_id = get_group_admin(group_id)
    user = query.from_user

    request_id = create_edit_request(expense_id, user.id, group_id)
    context.user_data['request_id'] = request_id

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✅ Approve",
                callback_data=f"adminreq_approve_{request_id}_{user.id}"
            ),
            InlineKeyboardButton(
                "❌ Reject",
                callback_data=f"adminreq_reject_{request_id}_{user.id}"
            ),
        ]
    ])

    await context.bot.send_message(
        chat_id=admin_id,
        text=(
            f"🔔 *[{get_group_by_id_name(group_id)}] Edit Request!*\n\n"
            f"👤 *{user.first_name}* wants to edit:\n\n"
            f"   Owner      : {expense[8]}\n"
            f"   Amount     : {expense[2]}\n"
            f"   Type       : {expense[5]}\n"
            f"   Date       : {expense[7]}\n"
            f"   Description: {expense[6] or 'None'}\n"
        ),
        parse_mode="Markdown",
        reply_markup=keyboard
    )

    await query.message.reply_text(
        "📨 Request sent to admin!\n"
        "You will be notified when approved."
    )
    return ConversationHandler.END


async def admin_respond(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    action = parts[1]
    request_id = int(parts[2])
    requester_id = int(parts[3])

    request = get_edit_request(request_id)
    expense = get_expense_by_id(request[1])

    if action == "approve":
        update_edit_request(request_id, "approved")
        context.user_data['editing_expense'] = expense
        context.user_data['approved_request'] = request_id

        await query.message.reply_text("✅ Request approved!")

        await context.bot.send_message(
            chat_id=requester_id,
            text=(
                f"✅ *Admin approved your request!*\n\n"
                f"Now editing:\n"
                f"👤 {expense[8]} — {expense[2]}\n\n"
                f"Use /edit to continue editing."
            ),
            parse_mode="Markdown"
        )

    else:
        update_edit_request(request_id, "rejected")
        await query.message.reply_text("❌ Request rejected!")

        await context.bot.send_message(
            chat_id=requester_id,
            text=(
                "❌ *Admin rejected your request.*\n\n"
                "You cannot edit this expense.\n"
                "Contact your admin for help."
            ),
            parse_mode="Markdown"
        )


async def select_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    field = query.data.split("_")[1]
    context.user_data['edit_field'] = field
    expense = context.user_data['editing_expense']

    if field == "delete":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "✅ Yes, Delete",
                callback_data="confirmdelete_yes"
            )],
            [InlineKeyboardButton(
                "❌ Cancel",
                callback_data="confirmdelete_no"
            )],
        ])
        await query.message.reply_text(
            f"🗑️ *Delete Expense?*\n\n"
            f"👤 {expense[8]} — {expense[2]}\n"
            f"📝 {expense[6] or 'No description'}\n"
            f"📅 {expense[7]}\n\n"
            f"⚠️ This will be soft deleted.\n"
            f"Admin can still restore it for 3 months.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return CONFIRM_DELETE

    elif field == "amount":
        old_shared = float(expense[3])
        old_personal = float(expense[4])
        if old_shared == 0:
            type_hint = "personal"
        elif old_personal == 0:
            type_hint = "shared"
        else:
            type_hint = f"mixed (personal={old_personal:.2f} fixed)"
        await query.message.reply_text(
            f"💰 Current total: `{expense[2]}`\n"
            f"   Type: {type_hint}\n\n"
            f"Enter new total amount:",
            parse_mode="Markdown"
        )
        return ENTER_NEW_VALUE

    elif field == "description":
        await query.message.reply_text(
            f"📝 Current description: "
            f"`{expense[6] or 'None'}`\n\n"
            f"Enter new description:",
            parse_mode="Markdown"
        )
        return ENTER_NEW_VALUE

    elif field == "split":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "🟰 Equal", callback_data="newfield_equal"
            )],
            [InlineKeyboardButton(
                "👥 Specific", callback_data="newfield_specific"
            )],
            [InlineKeyboardButton(
                "📊 Custom %", callback_data="newfield_custom"
            )],
        ])
        await query.message.reply_text(
            f"📊 Current split: `{expense[5]}`\n\n"
            f"Select new split type:",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return ENTER_NEW_VALUE

    elif field == "date":
        await query.message.reply_text(
            f"📅 Current date: `{expense[7]}`\n\n"
            f"Enter new date:\n"
            f"Format: `DD.MM.YYYY`",
            parse_mode="Markdown"
        )
        return ENTER_NEW_VALUE


async def enter_new_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    field = context.user_data['edit_field']
    expense = context.user_data['editing_expense']
    expense_id = expense[0]

    if field == "amount":
        try:
            new_value = float(update.message.text.strip())
            if new_value <= 0:
                await update.message.reply_text("❌ Amount must be > 0!")
                return ENTER_NEW_VALUE

            old_shared = float(expense[3])
            old_personal = float(expense[4])
            split_type = expense[5]
            group_id = expense[9]
            expense_date = expense[7]

            if old_shared == 0:
                new_shared = 0.0
                new_personal = new_value
            elif old_personal == 0:
                new_shared = new_value
                new_personal = 0.0
            else:
                new_personal = old_personal
                new_shared = new_value - old_personal
                if new_shared < 0:
                    await update.message.reply_text(
                        f"❌ New total must be ≥ {old_personal:.2f} "
                        f"(fixed personal portion)!"
                    )
                    return ENTER_NEW_VALUE

            old_splits = get_expense_splits(expense_id)

            update_expense(expense_id, "total_amount", new_value)
            update_expense(expense_id, "shared_amount", new_shared)
            update_expense(expense_id, "personal_amount", new_personal)
            delete_expense_splits(expense_id)

            if new_shared > 0:
                if split_type == 'equal':
                    members = get_active_members_at_date(
                        group_id, expense_date
                    )
                    if members:
                        per_person = round(new_shared / len(members), 2)
                        for m in members:
                            add_expense_split(expense_id, m[0], per_person)
                elif split_type == 'specific':
                    if old_splits:
                        per_person = round(new_shared / len(old_splits), 2)
                        for row in old_splits:
                            add_expense_split(expense_id, row[0], per_person)
                    else:
                        members = get_active_members_at_date(
                            group_id, expense_date
                        )
                        if members:
                            per_person = round(new_shared / len(members), 2)
                            for m in members:
                                add_expense_split(expense_id, m[0], per_person)
                elif split_type == 'custom':
                    if old_splits:
                        for row in old_splits:
                            pct = float(row[2]) if row[2] else 0
                            if pct > 0:
                                amt = round(new_shared * pct / 100, 2)
                                add_expense_split(
                                    expense_id, row[0], amt, pct
                                )
                    else:
                        members = get_active_members_at_date(
                            group_id, expense_date
                        )
                        if members:
                            per_person = round(new_shared / len(members), 2)
                            for m in members:
                                add_expense_split(expense_id, m[0], per_person)

            await update.message.reply_text(
                f"✅ *Amount updated!*\n\n"
                f"Total  : `{expense[2]}` → `{new_value}`\n"
                f"Shared : `{old_shared:.2f}` → `{new_shared:.2f}`\n"
                f"Personal: `{old_personal:.2f}` → `{new_personal:.2f}`\n\n"
                f"Splits recalculated ✅",
                parse_mode="Markdown"
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid amount! Enter a number."
            )
            return ENTER_NEW_VALUE

    elif field == "description":
        new_value = update.message.text.strip()
        old_value = expense[6]
        update_expense(expense_id, "description", new_value)
        await update.message.reply_text(
            f"✅ *Description updated!*\n\n"
            f"{old_value} → {new_value}",
            parse_mode="Markdown"
        )

    elif field == "date":
        try:
            new_date = datetime.strptime(
                update.message.text.strip(), "%d.%m.%Y"
            ).date()
            update_expense(expense_id, "expense_date", new_date)
            await update.message.reply_text(
                f"✅ *Date updated!*\n\n"
                f"{expense[7]} → {new_date}",
                parse_mode="Markdown"
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Wrong format! Use `DD.MM.YYYY`",
                parse_mode="Markdown"
            )
            return ENTER_NEW_VALUE

    return ConversationHandler.END


def _build_edit_specific_keyboard(members, selected):
    keyboard = []
    for uid, name in members:
        icon = "✅" if selected.get(uid, True) else "❌"
        keyboard.append([InlineKeyboardButton(
            f"{icon} {name}", callback_data=f"edspctoggle_{uid}"
        )])
    keyboard.append([InlineKeyboardButton(
        "✔️ Confirm Selection", callback_data="edspctoggle_confirm"
    )])
    return InlineKeyboardMarkup(keyboard)


async def enter_new_split(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    new_split = query.data.split("_")[1]
    expense = context.user_data['editing_expense']
    expense_id = expense[0]
    group_id = expense[9]
    expense_date = expense[7]
    shared = float(expense[3])

    context.user_data['edit_split_type'] = new_split

    if new_split == 'equal':
        members = get_active_members_at_date(group_id, expense_date)
        delete_expense_splits(expense_id)
        update_expense(expense_id, "split_type", "equal")
        per_person = 0.0
        if members and shared > 0:
            per_person = round(shared / len(members), 2)
            for m in members:
                add_expense_split(expense_id, m[0], per_person)
        names = ", ".join(m[1] for m in members) if members else "none"
        await query.message.reply_text(
            f"✅ *Split updated to Equal!*\n\n"
            f"Members: {names}\n"
            f"Each: `{per_person:.2f}`\n\n"
            f"Splits recalculated ✅",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    elif new_split == 'specific':
        members = get_active_members_at_date(group_id, expense_date)
        context.user_data['edit_specific_members'] = [
            (m[0], m[1]) for m in members
        ]
        context.user_data['edit_specific_selected'] = {
            m[0]: True for m in members
        }
        names = ", ".join(m[1] for m in members)
        keyboard = _build_edit_specific_keyboard(
            context.user_data['edit_specific_members'],
            context.user_data['edit_specific_selected']
        )
        await query.message.reply_text(
            f"👥 *Select members for this expense:*\n\n"
            f"Active: {names}\n\n"
            f"Tap to toggle. ✅ = included  ❌ = excluded.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return SELECT_SPLIT_MEMBERS_EDIT

    else:  # custom
        members = get_active_members_at_date(group_id, expense_date)
        context.user_data['edit_custom_members'] = [
            (m[0], m[1]) for m in members
        ]
        n = len(members)
        names = "  ".join(m[1] for m in members)
        pct_each = round(100 / n) if n > 0 else 0
        example = " ".join([str(pct_each)] * n)
        await query.message.reply_text(
            f"📊 *Custom Percentages*\n\n"
            f"Members: `{names}`\n\n"
            f"Enter % for each *(space-separated)*, must total 100%\n\n"
            f"Example: `{example}`",
            parse_mode="Markdown"
        )
        return ENTER_CUSTOM_PCT_EDIT


async def toggle_edit_split_member(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    suffix = query.data[len("edspctoggle_"):]
    expense = context.user_data['editing_expense']

    if suffix == "confirm":
        selected = context.user_data.get('edit_specific_selected', {})
        members = context.user_data.get('edit_specific_members', [])
        chosen = [
            (uid, name) for uid, name in members
            if selected.get(uid, True)
        ]

        if not chosen:
            await query.answer(
                "⚠️ Select at least one member!", show_alert=True
            )
            return SELECT_SPLIT_MEMBERS_EDIT

        expense_id = expense[0]
        shared = float(expense[3])
        per_person = round(shared / len(chosen), 2)

        delete_expense_splits(expense_id)
        update_expense(expense_id, "split_type", "specific")
        for uid, _name in chosen:
            add_expense_split(expense_id, uid, per_person)

        names_str = ", ".join(n for _, n in chosen)
        await query.message.reply_text(
            f"✅ *Split updated to Specific!*\n\n"
            f"Members: {names_str}\n"
            f"Each: `{per_person:.2f}`\n\n"
            f"Splits recalculated ✅",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    uid = int(suffix)
    selected = context.user_data.get('edit_specific_selected', {})
    selected[uid] = not selected.get(uid, True)
    context.user_data['edit_specific_selected'] = selected

    members = context.user_data.get('edit_specific_members', [])
    keyboard = _build_edit_specific_keyboard(members, selected)
    await query.message.edit_reply_markup(reply_markup=keyboard)
    return SELECT_SPLIT_MEMBERS_EDIT


async def enter_edit_custom_pct(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    expense = context.user_data['editing_expense']
    members = context.user_data.get('edit_custom_members', [])
    parts = update.message.text.strip().split()

    if len(parts) != len(members):
        names = "  ".join(name for _, name in members)
        await update.message.reply_text(
            f"❌ Expected *{len(members)}* values, got *{len(parts)}*.\n\n"
            f"Members: `{names}`\n"
            f"Enter {len(members)} numbers separated by spaces:",
            parse_mode="Markdown"
        )
        return ENTER_CUSTOM_PCT_EDIT

    try:
        percentages = [float(p) for p in parts]
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid numbers. Example: `50 25 25`",
            parse_mode="Markdown"
        )
        return ENTER_CUSTOM_PCT_EDIT

    total = sum(percentages)
    if abs(total - 100) > 0.5:
        await update.message.reply_text(
            f"❌ *Total must be 100%*\n\n"
            f"Your total: `{total:.1f}%`\n"
            f"Please correct and try again:",
            parse_mode="Markdown"
        )
        return ENTER_CUSTOM_PCT_EDIT

    expense_id = expense[0]
    shared = float(expense[3])

    delete_expense_splits(expense_id)
    update_expense(expense_id, "split_type", "custom")

    breakdown = []
    for i, (uid, name) in enumerate(members):
        if i < len(percentages) and percentages[i] > 0:
            amt = round(shared * percentages[i] / 100, 2)
            add_expense_split(expense_id, uid, amt, percentages[i])
            breakdown.append(
                f"   {name}: `{amt:.2f}` ({percentages[i]:.0f}%)"
            )

    await update.message.reply_text(
        f"✅ *Split updated to Custom %!*\n\n"
        + "\n".join(breakdown) + "\n\n"
        f"Splits recalculated ✅",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "confirmdelete_yes":
        expense = context.user_data['editing_expense']
        user = query.from_user
        soft_delete_expense(expense[0], user.id)

        await query.message.reply_text(
            f"✅ *Expense deleted!*\n\n"
            f"👤 {expense[8]} — {expense[2]}\n"
            f"📝 {expense[6] or 'No description'}\n\n"
            f"💾 Saved in admin history for 3 months.",
            parse_mode="Markdown"
        )
    else:
        await query.message.reply_text("❌ Delete cancelled.")

    return ConversationHandler.END


# ─── ADMIN DELETED LOG ───────────────────────────────────

async def admin_deleted_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    groups = get_user_groups(user.id)

    admin_groups = []
    for group in groups:
        if group[4] == user.id:
            admin_groups.append(group)

    if not admin_groups:
        await update.message.reply_text(
            "❌ You are not an admin of any group!"
        )
        return ConversationHandler.END

    keyboard = []
    for group in admin_groups:
        keyboard.append([InlineKeyboardButton(
            f"🏠 {group[1]}",
            callback_data=f"adminlog_{group[0]}"
        )])

    await update.message.reply_text(
        "🗑️ *Deleted Expenses Log*\n\nSelect group:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ADMIN_DELETED_LIST


async def show_deleted_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    group_id = int(query.data.split("_")[1])
    deleted = get_deleted_expenses(group_id)

    if not deleted:
        await query.message.reply_text(
            "✅ No deleted expenses in last 3 months!"
        )
        return ConversationHandler.END

    for exp in deleted:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "🔄 Restore",
                callback_data=f"restore_{exp[0]}"
            )]
        ])
        await query.message.reply_text(
            f"❌ *DELETED*\n\n"
            f"👤 Owner      : {exp[8]}\n"
            f"🗑️ Deleted by : {exp[9]}\n"
            f"💰 Amount     : {exp[2]}\n"
            f"📝 Description: {exp[5] or 'None'}\n"
            f"📅 Expense date: {exp[6]}\n"
            f"🕐 Deleted at : {exp[7].strftime('%d.%m.%Y %H:%M')}\n"
            f"⏳ Auto delete : in 3 months",
            parse_mode="Markdown",
            reply_markup=keyboard
        )

    return ConversationHandler.END


async def restore_deleted(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    expense_id = int(query.data.split("_")[1])
    restore_expense(expense_id)
    expense = get_expense_by_id(expense_id)

    await query.message.reply_text(
        f"✅ *Expense restored!*\n\n"
        f"👤 {expense[8]} — {expense[2]}\n"
        f"📝 {expense[6] or 'No description'}\n"
        f"📅 {expense[7]}\n\n"
        f"Now visible in reports again.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


def get_group_by_id_name(group_id):
    from bot.database.queries import get_group_by_id
    group = get_group_by_id(group_id)
    return group[1] if group else "Unknown"


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


def register_edit_handlers(app):
    edit_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^✏️ Edit Expense$"), edit_expense_start),
        ],
        states={
            SELECT_GROUP: [
                CallbackQueryHandler(
                    select_group, pattern="^edit_group_"
                )
            ],
            SELECT_DATE: [
                CallbackQueryHandler(
                    select_date, pattern="^editdate_"
                )
            ],
            ENTER_DATE: [
                MessageHandler(MENU_BUTTON_FILTER, exit_to_menu),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    enter_date
                )
            ],
            SELECT_EXPENSE: [
                CallbackQueryHandler(
                    select_expense, pattern="^editexp_"
                )
            ],
            SELECT_FIELD: [
                CallbackQueryHandler(
                    select_field, pattern="^field_"
                ),
                CallbackQueryHandler(
                    request_edit, pattern="^reqedit_"
                ),
            ],
            ENTER_NEW_VALUE: [
                MessageHandler(MENU_BUTTON_FILTER, exit_to_menu),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    enter_new_value
                ),
                CallbackQueryHandler(
                    enter_new_split, pattern="^newfield_"
                ),
            ],
            CONFIRM_DELETE: [
                CallbackQueryHandler(
                    confirm_delete, pattern="^confirmdelete_"
                )
            ],
            SELECT_SPLIT_MEMBERS_EDIT: [
                CallbackQueryHandler(
                    toggle_edit_split_member, pattern="^edspctoggle_"
                )
            ],
            ENTER_CUSTOM_PCT_EDIT: [
                MessageHandler(MENU_BUTTON_FILTER, exit_to_menu),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    enter_edit_custom_pct
                ),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
        ],
        allow_reentry=True
    )

    admin_conv = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("^🗑️ Deleted Log$"),
                admin_deleted_log
            )
        ],
        states={
            ADMIN_DELETED_LIST: [
                CallbackQueryHandler(
                    show_deleted_log, pattern="^adminlog_"
                ),
                CallbackQueryHandler(
                    restore_deleted, pattern="^restore_"
                ),
            ],
        },
        fallbacks=[]
    )

    app.add_handler(edit_conv)
    app.add_handler(admin_conv)
    app.add_handler(
        CallbackQueryHandler(
            admin_respond, pattern="^adminreq_"
        )
    )
