from bot.utils.report_generator import (
    generate_pdf_report, generate_excel_report
)
from bot.database.queries import get_expenses_for_report
import os
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, MessageHandler, ConversationHandler,
    CallbackQueryHandler, filters, CommandHandler
)
from bot.database.queries import (
    get_user_groups, get_balances,
    get_group_by_id, get_first_expense_date
)
from bot.utils.calculations import calculate_balances, calculate_settlements
from datetime import datetime, timedelta, date as date_type
from bot.utils.time_utils import now_moscow
from bot.utils.menu_guard import MENU_BUTTON_FILTER, exit_to_menu

# States
SELECT_GROUP = 0
SELECT_PERIOD = 1
ENTER_CUSTOM_START = 2
ENTER_CUSTOM_END = 3


async def view_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            callback_data=f"rep_group_{group[0]}"
        )])

    await update.message.reply_text(
        "📊 *View Report*\n\nSelect group:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_GROUP


async def select_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    group_id = int(query.data.split("_")[2])
    context.user_data['report_group_id'] = group_id

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 Last 2 weeks",  callback_data="period_2w")],
        #[InlineKeyboardButton("📅 Last 4 weeks",  callback_data="period_4w")],
        [InlineKeyboardButton("📅 This month",    callback_data="period_month")],
        [InlineKeyboardButton("📅 Custom dates",  callback_data="period_custom")],
    ])

    await query.message.reply_text(
        "Select report period:",
        reply_markup=keyboard
    )
    return SELECT_PERIOD


async def select_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    period = query.data.split("_")[1]
    now = now_moscow()

    if period == "custom":
        group_id = context.user_data['report_group_id']
        first_date = get_first_expense_date(group_id)

        if not first_date:
            await query.message.reply_text(
                "❌ No expenses found in this group yet!"
            )
            return ConversationHandler.END

        context.user_data['first_expense_date'] = first_date
        await query.message.reply_text(
            f"📅 Enter *start date:*\n\n"
            f"Your group has data from: "
            f"`{first_date.strftime('%d.%m.%Y')}`\n"
            f"Until today: `{now.strftime('%d.%m.%Y')}`\n\n"
            f"Format: `DD.MM.YYYY`\n"
            f"Example: `{first_date.strftime('%d.%m.%Y')}`",
            parse_mode="Markdown"
        )
        return ENTER_CUSTOM_START

    if period == "2w":
        start_date = (now - timedelta(weeks=2)).date()
        period_label = f"{start_date.strftime('%d.%m.%Y')} → {now.strftime('%d.%m.%Y')}"
    elif period == "4w":
        start_date = (now - timedelta(weeks=4)).date()
        period_label = f"{start_date.strftime('%d.%m.%Y')} → {now.strftime('%d.%m.%Y')}"
    else:
        start_date = now.replace(day=1).date()
        period_label = f"{start_date.strftime('%d.%m.%Y')} → {now.strftime('%d.%m.%Y')}"

    group_id = context.user_data['report_group_id']
    await generate_report(query.message, context, group_id, start_date, now.date(), period_label)
    return ConversationHandler.END


async def enter_custom_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = now_moscow().replace(hour=23, minute=59, second=59)
    first_date = context.user_data['first_expense_date']

    try:
        start_date = datetime.strptime(update.message.text.strip(), "%d.%m.%Y")
    except ValueError:
        await update.message.reply_text(
            f"❌ *Wrong format!*\n\n"
            f"Please use `DD.MM.YYYY`\n"
            f"Example: `{first_date.strftime('%d.%m.%Y')}`",
            parse_mode="Markdown"
        )
        return ENTER_CUSTOM_START

    # Check if before first expense
    if start_date.date() < first_date.date():
        await update.message.reply_text(
            f"❌ *Invalid start date!*\n\n"
            f"Your group has expenses starting from:\n"
            f"📅 `{first_date.strftime('%d.%m.%Y')}`\n\n"
            f"Please enter a date from "
            f"`{first_date.strftime('%d.%m.%Y')}` "
            f"until today `{today.strftime('%d.%m.%Y')}`:",
            parse_mode="Markdown"
        )
        return ENTER_CUSTOM_START

    # Check if future date
    if start_date.date() > today.date():
        await update.message.reply_text(
            f"❌ *Invalid date!*\n\n"
            f"You cannot select a future date.\n"
            f"Today is `{today.strftime('%d.%m.%Y')}`\n\n"
            f"Please enter a valid start date:",
            parse_mode="Markdown"
        )
        return ENTER_CUSTOM_START

    context.user_data['custom_start'] = start_date
    await update.message.reply_text(
        f"✅ Start date: `{start_date.strftime('%d.%m.%Y')}`\n\n"
        f"Now enter *end date:*\n"
        f"Max date: `{today.strftime('%d.%m.%Y')}` (today)\n\n"
        f"Format: `DD.MM.YYYY`",
        parse_mode="Markdown"
    )
    return ENTER_CUSTOM_END


async def enter_custom_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = now_moscow().replace(hour=23, minute=59, second=59)
    start_date = context.user_data['custom_start']

    try:
        end_date = datetime.strptime(update.message.text.strip(), "%d.%m.%Y")
        end_date = end_date.replace(hour=23, minute=59, second=59)
    except ValueError:
        await update.message.reply_text(
            f"❌ *Wrong format!*\n\n"
            f"Please use `DD.MM.YYYY`\n"
            f"Example: `{today.strftime('%d.%m.%Y')}`",
            parse_mode="Markdown"
        )
        return ENTER_CUSTOM_END

    # Check if before start date
    if end_date.date() < start_date.date():
        await update.message.reply_text(
            f"❌ *End date cannot be before start date!*\n\n"
            f"Start date: `{start_date.strftime('%d.%m.%Y')}`\n\n"
            f"Please enter end date after "
            f"`{start_date.strftime('%d.%m.%Y')}`:",
            parse_mode="Markdown"
        )
        return ENTER_CUSTOM_END

    # Check if future date
    if end_date.date() > today.date():
        await update.message.reply_text(
            f"❌ *Invalid date!*\n\n"
            f"End date cannot be in the future.\n"
            f"Max date: `{today.strftime('%d.%m.%Y')}` (today)\n\n"
            f"Please enter a valid end date:",
            parse_mode="Markdown"
        )
        return ENTER_CUSTOM_END

    group_id = context.user_data['report_group_id']
    period_label = (
        f"{start_date.strftime('%d.%m.%Y')} → "
        f"{end_date.strftime('%d.%m.%Y')}"
    )

    # Normalize to date objects
    start = start_date.date() if hasattr(start_date, 'date') else start_date
    end = end_date.date() if hasattr(end_date, 'date') else end_date

    await generate_report(
        update.message, context, group_id,
        start, end, period_label
    )
    return ConversationHandler.END


async def generate_report(
    message, context, group_id, start_date, end_date, period_label
):
    try:
        group = get_group_by_id(group_id)
        currency = group[2]

        expenses, splits = get_balances(
            group_id, start_date, end_date
        )

        if not expenses:
            await message.reply_text(
                f"📊 *{group[1]}*\n"
                f"📅 {period_label}\n\n"
                f"❌ No expenses found in this period.",
                parse_mode="Markdown"
            )
            return

        from bot.database.queries import get_group_members
        all_members = get_group_members(group_id)  # all active members

        balances = calculate_balances(expenses, splits)
        all_expenses = get_expenses_for_report(
            group_id, start_date, end_date
        )

        # Ensure ALL group members appear in balances (even if 0 paid, 0 share)
        for m in all_members:
            uid, name = m[0], m[1]
            if uid not in balances:
                balances[uid] = {'name': name, 'paid': 0.0, 'share': 0.0, 'balance': 0.0}

        # Recalculate settlements with full member list
        settlements = calculate_settlements(balances)

        # Build report text
        report = "📊 *SplitBazar — Expense Report*\n"
        report += f"🏠 {group[1]}\n"
        report += f"📅 {period_label}\n"
        report += "━━━━━━━━━━━━━━━━━━━━\n\n"

        report += "👥 *MEMBERS:*\n"
        for m in all_members:
            report += f"   {m[1]}\n"
        report += "\n"

        report += "━━━━━━━━━━━━━━━━━━━━\n"
        report += "💰 *SUMMARY:*\n\n"

        settled_users = []
        for uid, data in balances.items():
            balance = float(data['balance'])
            paid = float(data['paid'])
            share = float(data['share'])
            name = data['name']

            if abs(balance) < 0.01:
                status = "settled ✅"
                emoji = "✅"
                settled_users.append(name)
            elif balance > 0:
                status = f"+{balance:.2f} gets back 💚"
                emoji = "💚"
            else:
                status = f"{balance:.2f} owes ⚠️"
                emoji = "⚠️"

            report += (
                f"{emoji} *{name}*\n"
                f"   Paid: `{paid:.2f}` {currency}  "
                f"Share: `{share:.2f}` {currency}  "
                f"│ {status}\n\n"
            )

        report += "━━━━━━━━━━━━━━━━━━━━\n"
        report += "💸 *SETTLEMENT:*\n\n"

        if settlements:
            for s in settlements:
                report += (
                    f"👤 *{s['from_name']}* → pays → "
                    f"*{s['to_name']}* : "
                    f"`{s['amount']:.2f}` {currency}\n"
                )
            for name in settled_users:
                report += f"✅ *{name}* → settled\n"
        else:
            report += "✅ All settled — no payments needed!\n"

        # Download buttons
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    "📄 Download PDF",
                    callback_data=f"download_pdf_{group_id}"
                ),
                InlineKeyboardButton(
                    "📊 Download Excel",
                    callback_data=f"download_excel_{group_id}"
                ),
            ]
        ])

        await message.reply_text(
            report,
            parse_mode="Markdown",
            reply_markup=keyboard
        )

        # Store data for download using bot_data
        if 'report_cache' not in context.bot_data:
            context.bot_data['report_cache'] = {}

        context.bot_data['report_cache'][group_id] = {
            'group_name': group[1],
            'currency': currency,
            'period_label': period_label,
            'balances': balances,
            'settlements': settlements,
            'expenses': all_expenses,
        }

    except Exception as e:
        await message.reply_text(
            f"❌ Error generating report: {str(e)}\n\n"
            "Please try again or contact support."
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "❌ Cancelled. Use the menu to continue.",
    )
    return ConversationHandler.END


async def handle_download(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    parts = query.data.split("_")
    file_type = parts[1]
    group_id = int(parts[2])

    cache = context.bot_data.get('report_cache', {})
    data = cache.get(group_id)

    if not data:
        await query.message.reply_text(
            "❌ Report expired. Please generate again."
        )
        return

    await query.message.reply_text(
        "⏳ Generating file, please wait..."
    )

    try:
        if file_type == "pdf":
            filepath = generate_pdf_report(
                data['group_name'],
                data['currency'],
                data['period_label'],
                data['balances'],
                data['settlements'],
                data['expenses']
            )
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=f"SplitBazar_{data['group_name']}.pdf",
                    caption=f"📄 PDF Report\n{data['period_label']}"
                )
        else:
            filepath = generate_excel_report(
                data['group_name'],
                data['currency'],
                data['period_label'],
                data['balances'],
                data['settlements'],
                data['expenses']
            )
            with open(filepath, 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=f"SplitBazar_{data['group_name']}.xlsx",
                    caption=f"📊 Excel Report\n{data['period_label']}"
                )

        # Cleanup temp file
        os.remove(filepath)

    except Exception as e:
        await query.message.reply_text(
            f"❌ Error generating file: {str(e)}"
        )

def register_report_handlers(app):
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("^📊 View Report$"),
                view_report
            )
        ],
        states={
            SELECT_GROUP: [
                CallbackQueryHandler(
                    select_group, pattern="^rep_group_"
                )
            ],
            SELECT_PERIOD: [
                CallbackQueryHandler(
                    select_period, pattern="^period_"
                )
            ],
            ENTER_CUSTOM_START: [
                MessageHandler(MENU_BUTTON_FILTER, exit_to_menu),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    enter_custom_start
                )
            ],
            ENTER_CUSTOM_END: [
                MessageHandler(MENU_BUTTON_FILTER, exit_to_menu),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    enter_custom_end
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
        ],
        allow_reentry=True
    )

    app.add_handler(conv_handler)
    app.add_handler(
        CallbackQueryHandler(
            handle_download, pattern="^download_"
        )
    )