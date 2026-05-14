from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, MessageHandler, ConversationHandler,
    CallbackQueryHandler, filters, CommandHandler
)
from bot.database.queries import (
    get_user_groups, get_group_by_id,
    add_expense, add_expense_split, get_active_group_members
)
from bot.utils.time_utils import now_moscow
from bot.utils.menu_guard import MENU_BUTTON_FILTER, exit_to_menu

# States
PAY_SELECT_GROUP = 0
PAY_SELECT_MEMBER = 1
PAY_ENTER_AMOUNT = 2
PAY_CONFIRM = 3


async def record_payment_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user
    groups = get_user_groups(user.id)

    if not groups:
        await update.message.reply_text(
            "❌ You are not in any group yet!\n\n"
            "Please create or join a group first."
        )
        return ConversationHandler.END

    keyboard = []
    for group in groups:
        keyboard.append([InlineKeyboardButton(
            f"🏠 {group[1]} ({group[2]})",
            callback_data=f"pay_group_{group[0]}"
        )])

    await update.message.reply_text(
        "💳 *Record Payment*\n\n"
        "Record a payment you made to settle a debt.\n\n"
        "Select group:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return PAY_SELECT_GROUP


async def pay_select_group(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    group_id = int(query.data.split("_")[2])
    context.user_data['pay_group_id'] = group_id

    user = query.from_user
    members = get_active_group_members(group_id)
    other_members = [(m[0], m[1]) for m in members if m[0] != user.id]

    if not other_members:
        await query.message.reply_text(
            "❌ No other members in this group to pay!"
        )
        return ConversationHandler.END

    context.user_data['pay_members'] = other_members

    keyboard = []
    for uid, name in other_members:
        keyboard.append([InlineKeyboardButton(
            f"👤 {name}",
            callback_data=f"pay_member_{uid}"
        )])

    await query.message.reply_text(
        "👤 Who did you pay?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return PAY_SELECT_MEMBER


async def pay_select_member(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    to_uid = int(query.data.split("_")[2])
    members = context.user_data.get('pay_members', [])
    to_name = next((n for uid, n in members if uid == to_uid), "Unknown")

    context.user_data['pay_to_uid'] = to_uid
    context.user_data['pay_to_name'] = to_name

    group_id = context.user_data['pay_group_id']
    group = get_group_by_id(group_id)
    currency = group[2] if group else ""

    await query.message.reply_text(
        f"💰 How much did you pay *{to_name}*?\n\n"
        f"Enter amount ({currency}):",
        parse_mode="Markdown"
    )
    return PAY_ENTER_AMOUNT


async def pay_enter_amount(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    try:
        amount = float(update.message.text.strip())
        if amount <= 0:
            await update.message.reply_text("❌ Amount must be > 0!")
            return PAY_ENTER_AMOUNT

        context.user_data['pay_amount'] = amount
        to_name = context.user_data['pay_to_name']
        group_id = context.user_data['pay_group_id']
        group = get_group_by_id(group_id)
        currency = group[2] if group else ""

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "✅ Confirm", callback_data="pay_confirm_yes"
                ),
                InlineKeyboardButton(
                    "❌ Cancel", callback_data="pay_confirm_no"
                ),
            ]
        ])

        await update.message.reply_text(
            f"💳 *Confirm Payment*\n\n"
            f"You → *{to_name}*\n"
            f"Amount : `{amount:.2f}` {currency}\n\n"
            f"Record this payment?",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        return PAY_CONFIRM

    except ValueError:
        await update.message.reply_text(
            "❌ Invalid amount! Enter a number.\nExample: `200`",
            parse_mode="Markdown"
        )
        return PAY_ENTER_AMOUNT


async def pay_confirm(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    if query.data == "pay_confirm_no":
        context.user_data.clear()
        await query.message.reply_text("❌ Cancelled.")
        return ConversationHandler.END

    user = query.from_user
    group_id = context.user_data['pay_group_id']
    to_uid = context.user_data['pay_to_uid']
    to_name = context.user_data['pay_to_name']
    amount = context.user_data['pay_amount']

    group = get_group_by_id(group_id)
    currency = group[2] if group else ""
    today = now_moscow().date()
    description = f"Settlement: {user.first_name} → {to_name}"

    expense_id = add_expense(
        group_id, user.id, amount, amount, 0,
        'settlement', description, None, today
    )
    add_expense_split(expense_id, to_uid, amount)

    context.user_data.clear()

    await query.message.reply_text(
        f"✅ *Payment Recorded!*\n\n"
        f"You paid *{to_name}* `{amount:.2f}` {currency}\n\n"
        f"📊 Use View Report to see updated balances!",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


def register_payment_handlers(app):
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("^💳 Record Payment$"),
                record_payment_start
            )
        ],
        states={
            PAY_SELECT_GROUP: [
                CallbackQueryHandler(
                    pay_select_group, pattern="^pay_group_"
                )
            ],
            PAY_SELECT_MEMBER: [
                CallbackQueryHandler(
                    pay_select_member, pattern="^pay_member_"
                )
            ],
            PAY_ENTER_AMOUNT: [
                MessageHandler(MENU_BUTTON_FILTER, exit_to_menu),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    pay_enter_amount
                )
            ],
            PAY_CONFIRM: [
                CallbackQueryHandler(
                    pay_confirm, pattern="^pay_confirm_"
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
        ],
        allow_reentry=True
    )
    app.add_handler(conv_handler)
