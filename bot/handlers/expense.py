from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, MessageHandler, ConversationHandler,
    CallbackQueryHandler, filters
)
from bot.database.queries import (
    save_user, get_user_groups, add_expense,
    add_expense_split, get_active_members_at_date
)
from datetime import datetime

# Conversation states
SELECT_GROUP = 0
SELECT_TYPE = 1
ENTER_TOTAL = 2
ENTER_SHARED = 3
SELECT_SPLIT = 4
ENTER_DESCRIPTION = 5
UPLOAD_RECEIPT = 6


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

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🍽️ Shared (for everyone)", callback_data="type_shared")],
        [InlineKeyboardButton("👤 Personal only", callback_data="type_personal")],
        [InlineKeyboardButton("🔀 Mixed (shared + personal)", callback_data="type_mixed")],
    ])

    await query.message.reply_text(
        "What type of purchase is this?",
        reply_markup=keyboard
    )
    return SELECT_TYPE


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
                "📝 Add a description (optional)\n\nOr send /skip to skip:"
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

    await query.message.reply_text(
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
    now = datetime.now()

    expense_id = add_expense(
        group_id, user.id, total, shared,
        personal, split_type, description, receipt_file_id
    )

    if shared > 0:
        active_members = get_active_members_at_date(group_id, now)
        if split_type == 'equal' and active_members:
            split_amount = round(shared / len(active_members), 2)
            for member in active_members:
                add_expense_split(expense_id, member[0], split_amount)

    await update.message.reply_text(
        f"✅ *Expense Saved!*\n\n"
        f"💰 Total       : {total}\n"
        f"🍽️ Shared      : {shared}\n"
        f"👤 Personal    : {personal}\n"
        f"📊 Split type  : {split_type}\n"
        f"📝 Description : {description or 'None'}\n"
        f"📸 Receipt     : {'✅ Saved' if receipt_file_id else '❌ None'}\n\n"
        f"Use 📊 View Report to see balances!",
        parse_mode="Markdown"
    )


def register_expense_handlers(app):
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^➕ Add Expense$"), add_expense_start)
        ],
        states={
            SELECT_GROUP: [CallbackQueryHandler(select_group, pattern="^exp_group_")],
            SELECT_TYPE: [CallbackQueryHandler(select_type, pattern="^type_")],
            ENTER_TOTAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_total)],
            ENTER_SHARED: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_shared)],
            SELECT_SPLIT: [CallbackQueryHandler(select_split, pattern="^split_")],
            ENTER_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_description),
                MessageHandler(filters.Regex("^/skip$"), enter_description)
            ],
            UPLOAD_RECEIPT: [
                MessageHandler(filters.PHOTO | filters.Document.ALL, upload_receipt),
                MessageHandler(filters.Regex("^/skip$"), skip_receipt)
            ],
        },
        fallbacks=[]
    )
    app.add_handler(conv_handler)