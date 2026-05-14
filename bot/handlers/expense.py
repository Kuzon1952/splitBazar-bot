from datetime import datetime, timedelta
from bot.utils.time_utils import now_moscow
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, MessageHandler, ConversationHandler,
    CallbackQueryHandler, filters, CommandHandler
)
from bot.database.queries import (
    save_user, get_user_groups, add_expense,
    add_expense_split, get_active_members_at_date,
    get_member_join_date, get_group_by_id
)
from bot.handlers.notifications import send_large_expense_alert
from bot.handlers.target import check_budget_alert
from bot.utils.menu_guard import MENU_BUTTON_FILTER, exit_to_menu

# Conversation states
SELECT_GROUP = 0
SELECT_DATE = 7
ENTER_DATE = 8
SELECT_TYPE = 1
ENTER_TOTAL = 2
ENTER_SHARED = 3
SELECT_SPLIT = 4
ENTER_DESCRIPTION = 5
UPLOAD_RECEIPT = 6
SELECT_SPECIFIC_MEMBERS = 9
ENTER_CUSTOM_PCT = 10

async def add_expense_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    save_user(user.id, user.username, user.first_name, user.last_name)

    groups = get_user_groups(user.id)

    if not groups:
        await update.message.reply_text(
            "❌ You are not in any group yet!\n\n"
            "Please create or join a group first using 👥 My Groups"
        )
        return ConversationHandler.END

    keyboard = []
    for group in groups:
        keyboard.append([InlineKeyboardButton(
            f"🏠 {group[1]} ({group[2]})",
            callback_data=f"exp_group_{group[0]}"
        )])

    await update.message.reply_text(
        "➕ *Add Expense*\n\nSelect group:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_GROUP


async def select_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    group_id = int(query.data.split("_")[2])
    context.user_data['group_id'] = group_id

    today = now_moscow()
    yesterday = today - timedelta(days=1)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            f"📅 Today ({today.strftime('%d.%m.%Y')})",
            callback_data="expdate_today"
        )],
        [InlineKeyboardButton(
            f"📅 Yesterday ({yesterday.strftime('%d.%m.%Y')})",
            callback_data="expdate_yesterday"
        )],
        [InlineKeyboardButton(
            "📅 Earlier date",
            callback_data="expdate_earlier"
        )],
    ])

    await query.message.reply_text(
        "📅 When did you make this purchase?",
        reply_markup=keyboard
    )
    return SELECT_DATE


async def select_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    purchase_type = query.data.split("_")[1]
    context.user_data['purchase_type'] = purchase_type

    await query.message.reply_text(
        "💰 Enter the *total amount* spent:\n\nExample: `500`",
        parse_mode="Markdown"
    )
    return ENTER_TOTAL


async def enter_total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        total = float(update.message.text.strip())
        context.user_data['total_amount'] = total
        purchase_type = context.user_data['purchase_type']

        if purchase_type == "personal":
            context.user_data['shared_amount'] = 0
            context.user_data['personal_amount'] = total
            await update.message.reply_text(
                "📝 Add a description: "
            )
            return ENTER_DESCRIPTION
    
        elif purchase_type == "shared":
            context.user_data['shared_amount'] = total
            context.user_data['personal_amount'] = 0
            await ask_split_type(update, context)
            return SELECT_SPLIT

        elif purchase_type == "mixed":
            await update.message.reply_text(
                f"Total: *{total}*\n\n"
                f"How much was *personal* (just for you)?\n\n"
                f"Example: if total is 500 and 100 is personal, enter `100`",
                parse_mode="Markdown"
            )
            return ENTER_SHARED

    except ValueError:
        await update.message.reply_text(
            "❌ Please enter a valid number. Example: `500`",
            parse_mode="Markdown"
        )
        return ENTER_TOTAL


async def enter_shared(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        personal = float(update.message.text.strip())
        total = context.user_data['total_amount']

        if personal > total:
            await update.message.reply_text(
                "❌ Personal amount cannot be more than total! Try again:"
            )
            return ENTER_SHARED

        context.user_data['personal_amount'] = personal
        context.user_data['shared_amount'] = total - personal

        await update.message.reply_text(
            f"✅ Total: {total}\n"
            f"👤 Personal: {personal}\n"
            f"🍽️ Shared: {total - personal}"
        )
        await ask_split_type(update, context)
        return SELECT_SPLIT

    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number.")
        return ENTER_SHARED


async def ask_split_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🟰 Equal split", callback_data="split_equal")],
        [InlineKeyboardButton("👥 Specific people", callback_data="split_specific")],
        [InlineKeyboardButton("📊 Custom %", callback_data="split_custom")],
    ])
    await update.message.reply_text(
        "How to split the shared amount?",
        reply_markup=keyboard
    )


async def select_split(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    split_type = query.data.split("_")[1]
    context.user_data['split_type'] = split_type

    if split_type == 'equal':
        await query.message.reply_text(
            "📝 Add a description (optional)\n\nOr send /skip to skip:"
        )
        return ENTER_DESCRIPTION
    elif split_type == 'specific':
        return await _start_specific_selection(query.message, context)
    else:
        return await _start_custom_pct(query.message, context)


def _build_specific_keyboard(members, selected):
    keyboard = []
    for uid, name in members:
        icon = "✅" if selected.get(uid, True) else "❌"
        keyboard.append([InlineKeyboardButton(
            f"{icon} {name}", callback_data=f"spctoggle_{uid}"
        )])
    keyboard.append([InlineKeyboardButton(
        "✔️ Confirm Selection", callback_data="spctoggle_confirm"
    )])
    return InlineKeyboardMarkup(keyboard)


async def _start_specific_selection(message, context):
    group_id = context.user_data['group_id']
    expense_date = context.user_data.get('expense_date', now_moscow().date())
    active_members = get_active_members_at_date(group_id, expense_date)

    context.user_data['specific_members'] = [(m[0], m[1]) for m in active_members]
    context.user_data['specific_selected'] = {m[0]: True for m in active_members}

    names = ", ".join(m[1] for m in active_members)
    keyboard = _build_specific_keyboard(
        context.user_data['specific_members'],
        context.user_data['specific_selected']
    )
    await message.reply_text(
        f"👥 *Select members for this expense:*\n\n"
        f"Active: {names}\n\n"
        f"Tap to toggle. ✅ = included  ❌ = excluded.",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    return SELECT_SPECIFIC_MEMBERS


async def toggle_specific_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    suffix = query.data[len("spctoggle_"):]

    if suffix == "confirm":
        selected = context.user_data.get('specific_selected', {})
        members = context.user_data.get('specific_members', [])
        chosen = [(uid, name) for uid, name in members if selected.get(uid, True)]

        if not chosen:
            await query.answer("⚠️ Select at least one member!", show_alert=True)
            return SELECT_SPECIFIC_MEMBERS

        context.user_data['specific_chosen'] = chosen
        await query.message.reply_text(
            "📝 Add a description (optional)\n\nOr send /skip to skip:"
        )
        return ENTER_DESCRIPTION

    uid = int(suffix)
    selected = context.user_data.get('specific_selected', {})
    selected[uid] = not selected.get(uid, True)
    context.user_data['specific_selected'] = selected

    members = context.user_data.get('specific_members', [])
    keyboard = _build_specific_keyboard(members, selected)
    await query.message.edit_reply_markup(reply_markup=keyboard)
    return SELECT_SPECIFIC_MEMBERS


async def _start_custom_pct(message, context):
    group_id = context.user_data['group_id']
    expense_date = context.user_data.get('expense_date', now_moscow().date())
    active_members = get_active_members_at_date(group_id, expense_date)

    context.user_data['custom_pct_members'] = [(m[0], m[1]) for m in active_members]

    n = len(active_members)
    names = "  ".join(m[1] for m in active_members)
    pct_each = round(100 / n) if n > 0 else 0
    example = " ".join([str(pct_each)] * n)

    await message.reply_text(
        f"📊 *Custom Percentages*\n\n"
        f"Members: `{names}`\n\n"
        f"Enter % for each *(space-separated)*, must total 100%\n\n"
        f"Example: `{example}`",
        parse_mode="Markdown"
    )
    return ENTER_CUSTOM_PCT


async def enter_custom_pct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    members = context.user_data.get('custom_pct_members', [])
    parts = update.message.text.strip().split()

    if len(parts) != len(members):
        names = "  ".join(name for _, name in members)
        await update.message.reply_text(
            f"❌ Expected *{len(members)}* values, got *{len(parts)}*.\n\n"
            f"Members: `{names}`\n"
            f"Enter {len(members)} numbers separated by spaces:",
            parse_mode="Markdown"
        )
        return ENTER_CUSTOM_PCT

    try:
        percentages = [float(p) for p in parts]
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid numbers. Example: `50 25 25`",
            parse_mode="Markdown"
        )
        return ENTER_CUSTOM_PCT

    total = sum(percentages)
    if abs(total - 100) > 0.5:
        await update.message.reply_text(
            f"❌ *Total must be 100%*\n\n"
            f"Your total: `{total:.1f}%`\n"
            f"Difference: `{abs(100 - total):.1f}%`\n\n"
            f"Please correct and try again:",
            parse_mode="Markdown"
        )
        return ENTER_CUSTOM_PCT

    context.user_data['custom_percentages'] = percentages
    await update.message.reply_text(
        "📝 Add a description (optional)\n\nOr send /skip to skip:"
    )
    return ENTER_DESCRIPTION


async def enter_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text != "/skip":
        context.user_data['description'] = update.message.text
    else:
        context.user_data['description'] = None

    await update.message.reply_text(
        "📸 Upload a receipt photo/PDF (optional)\n\nOr send /skip to skip:"
    )
    return UPLOAD_RECEIPT


async def upload_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    receipt_file_id = None

    if update.message.photo:
        receipt_file_id = update.message.photo[-1].file_id
    elif update.message.document:
        receipt_file_id = update.message.document.file_id

    await save_expense(update, context, receipt_file_id)
    return ConversationHandler.END


async def skip_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await save_expense(update, context, None)
    return ConversationHandler.END


async def save_expense(update: Update, context, receipt_file_id):
    user = update.effective_user
    group_id = context.user_data['group_id']
    total = context.user_data['total_amount']
    shared = context.user_data['shared_amount']
    personal = context.user_data['personal_amount']
    split_type = context.user_data.get('split_type', 'equal')
    description = context.user_data.get('description')
    now = now_moscow()
    expense_date = context.user_data.get('expense_date', now.date())
    if hasattr(expense_date, 'date'):
        expense_date = expense_date.date()

    expense_id = add_expense(
        group_id, user.id, total, shared,
        personal, split_type, description,
        receipt_file_id, expense_date
    )

    group = get_group_by_id(group_id)
    currency = group[2] if group else ""
    split_details = ""

    if shared > 0:
        active_members = get_active_members_at_date(group_id, expense_date)

        if split_type == 'equal' and active_members:
            split_amount = round(shared / len(active_members), 2)
            for member in active_members:
                add_expense_split(expense_id, member[0], split_amount)
            split_details = "\n\n📋 *Split breakdown:*\n"
            for m in active_members:
                split_details += f"   {m[1]}: `{split_amount:.2f}` {currency}\n"

        elif split_type == 'specific':
            chosen = context.user_data.get(
                'specific_chosen',
                [(m[0], m[1]) for m in active_members]
            )
            if chosen:
                split_amount = round(shared / len(chosen), 2)
                for uid, _name in chosen:
                    add_expense_split(expense_id, uid, split_amount)
                split_details = "\n\n📋 *Split breakdown:*\n"
                for uid, name in chosen:
                    split_details += f"   {name}: `{split_amount:.2f}` {currency}\n"

        elif split_type == 'custom':
            members = context.user_data.get('custom_pct_members', [])
            percentages = context.user_data.get('custom_percentages', [])
            split_details = "\n\n📋 *Split breakdown:*\n"
            for i, (uid, _name) in enumerate(members):
                if i < len(percentages) and percentages[i] > 0:
                    amount = round(shared * percentages[i] / 100, 2)
                    add_expense_split(expense_id, uid, amount, percentages[i])
                    split_details += (
                        f"   {members[i][1]}: `{amount:.2f}` {currency}"
                        f" ({percentages[i]:.0f}%)\n"
                    )

        if group:
            await check_budget_alert(
                context, user.id, group_id, group[2], group[1]
            )
            if shared > 1000:
                await send_large_expense_alert(
                    context,
                    group_id,
                    group[1],
                    group[2],
                    user.first_name,
                    total,
                    split_type,
                    description,
                    expense_date.strftime('%d.%m.%Y')
                )

    await update.message.reply_text(
        f"✅ *Expense Saved!*\n\n"
        f"💰 Total       : {total} {currency}\n"
        f"🍽️ Shared      : {shared} {currency}\n"
        f"👤 Personal    : {personal} {currency}\n"
        f"📊 Split type  : {split_type}\n"
        f"📝 Description : {description or 'None'}\n"
        f"📸 Receipt     : {'✅ Saved' if receipt_file_id else '❌ None'}"
        f"{split_details}\n\n"
        f"Use 📊 View Report to see balances!",
        parse_mode="Markdown"
    )

async def select_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    date_choice = query.data.split("_")[1]
    today = now_moscow()
    group_id = context.user_data['group_id']
    user = query.from_user

    if date_choice == "today":
        context.user_data['expense_date'] = today.date()
        await show_purchase_type(query.message)
        return SELECT_TYPE

    elif date_choice == "yesterday":
        yesterday = today - timedelta(days=1)
        context.user_data['expense_date'] = yesterday.date()
        await show_purchase_type(query.message)
        return SELECT_TYPE

    elif date_choice == "earlier":
        join_date = get_member_join_date(group_id, user.id)
        context.user_data['join_date'] = join_date
        await query.message.reply_text(
            f"📅 Enter purchase date:\n\n"
            f"Format: `DD.MM.YYYY`\n"
            f"Earliest: `{join_date.strftime('%d.%m.%Y')}` "
            f"(your join date)\n"
            f"Latest: `{today.strftime('%d.%m.%Y')}` (today)",
            parse_mode="Markdown"
        )
        return ENTER_DATE


async def enter_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = now_moscow().date()
    join_date = context.user_data['join_date']

    try:
        entered_date = datetime.strptime(
            update.message.text.strip(), "%d.%m.%Y"
        ).date()
    except ValueError:
        await update.message.reply_text(
            "❌ Wrong format!\n"
            "Please use `DD.MM.YYYY`\n"
            "Example: `20.03.2026`",
            parse_mode="Markdown"
        )
        return ENTER_DATE

    if entered_date > today:
        await update.message.reply_text(
            f"❌ Cannot enter future date!\n"
            f"Latest allowed: `{today.strftime('%d.%m.%Y')}`",
            parse_mode="Markdown"
        )
        return ENTER_DATE

    if entered_date < join_date.date():
        await update.message.reply_text(
            f"❌ Cannot enter date before you joined!\n"
            f"Earliest allowed: "
            f"`{join_date.strftime('%d.%m.%Y')}`",
            parse_mode="Markdown"
        )
        return ENTER_DATE

    context.user_data['expense_date'] = entered_date
    await update.message.reply_text(
        f"✅ Date: `{entered_date.strftime('%d.%m.%Y')}`",
        parse_mode="Markdown"
    )
    await show_purchase_type(update.message)
    return SELECT_TYPE


async def show_purchase_type(message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "🍽️ Shared (for everyone)",
            callback_data="type_shared"
        )],
        [InlineKeyboardButton(
            "👤 Personal only",
            callback_data="type_personal"
        )],
        [InlineKeyboardButton(
            "🔀 Mixed (shared + personal)",
            callback_data="type_mixed"
        )],
    ])
    await message.reply_text(
        "What type of purchase is this?",
        reply_markup=keyboard
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


def register_expense_handlers(app):
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^➕ Add Expense$"), add_expense_start),
        ],
        states={
            SELECT_GROUP: [
                CallbackQueryHandler(
                    select_group, pattern="^exp_group_"
                )
            ],
            SELECT_DATE: [
                CallbackQueryHandler(
                    select_date, pattern="^expdate_"
                )
            ],
            ENTER_DATE: [
                MessageHandler(MENU_BUTTON_FILTER, exit_to_menu),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    enter_date
                )
            ],
            SELECT_TYPE: [
                CallbackQueryHandler(
                    select_type, pattern="^type_"
                )
            ],
            ENTER_TOTAL: [
                MessageHandler(MENU_BUTTON_FILTER, exit_to_menu),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    enter_total
                )
            ],
            ENTER_SHARED: [
                MessageHandler(MENU_BUTTON_FILTER, exit_to_menu),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    enter_shared
                )
            ],
            SELECT_SPLIT: [
                CallbackQueryHandler(
                    select_split, pattern="^split_"
                )
            ],
            SELECT_SPECIFIC_MEMBERS: [
                CallbackQueryHandler(
                    toggle_specific_member, pattern="^spctoggle_"
                )
            ],
            ENTER_CUSTOM_PCT: [
                MessageHandler(MENU_BUTTON_FILTER, exit_to_menu),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    enter_custom_pct
                )
            ],
            ENTER_DESCRIPTION: [
                CommandHandler("skip", enter_description),
                MessageHandler(MENU_BUTTON_FILTER, exit_to_menu),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    enter_description
                )
            ],
            UPLOAD_RECEIPT: [
                MessageHandler(
                    filters.PHOTO | filters.Document.ALL,
                    upload_receipt
                ),
                CommandHandler("skip", skip_receipt),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("clear", cancel),
        ],
        allow_reentry=True,
    )
    app.add_handler(conv_handler)