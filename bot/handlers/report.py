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
    get_group_by_id, get_first_expense_date,
    get_members_who_left, get_members_active_during_period
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
    today = now_moscow().date()
    first_date = context.user_data['first_expense_date']
    # Normalize: psycopg2 returns date object from DATE column, not datetime
    if not isinstance(first_date, date_type):
        first_date = first_date.date()

    try:
        start_date = datetime.strptime(update.message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await update.message.reply_text(
            f"❌ *Wrong format!*\n\n"
            f"Please use `DD.MM.YYYY`\n"
            f"Example: `{first_date.strftime('%d.%m.%Y')}`",
            parse_mode="Markdown"
        )
        return ENTER_CUSTOM_START

    # Check if before first expense
    if start_date < first_date:
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
    if start_date > today:
        await update.message.reply_text(
            f"❌ *Invalid date!*\n\n"
            f"You cannot select a future date.\n"
            f"Today is `{today.strftime('%d.%m.%Y')}`\n\n"
            f"Please enter a valid start date:",
            parse_mode="Markdown"
        )
        return ENTER_CUSTOM_START

    context.user_data['custom_start'] = start_date  # always a date object now
    await update.message.reply_text(
        f"✅ Start date: `{start_date.strftime('%d.%m.%Y')}`\n\n"
        f"Now enter *end date:*\n"
        f"Max date: `{today.strftime('%d.%m.%Y')}` (today)\n\n"
        f"Format: `DD.MM.YYYY`",
        parse_mode="Markdown"
    )
    return ENTER_CUSTOM_END


async def enter_custom_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = now_moscow().date()
    start_date = context.user_data['custom_start']  # already a date object

    try:
        end_date = datetime.strptime(update.message.text.strip(), "%d.%m.%Y").date()
    except ValueError:
        await update.message.reply_text(
            f"❌ *Wrong format!*\n\n"
            f"Please use `DD.MM.YYYY`\n"
            f"Example: `{today.strftime('%d.%m.%Y')}`",
            parse_mode="Markdown"
        )
        return ENTER_CUSTOM_END

    # Check if before start date
    if end_date < start_date:
        await update.message.reply_text(
            f"❌ *End date cannot be before start date!*\n\n"
            f"Start date: `{start_date.strftime('%d.%m.%Y')}`\n\n"
            f"Please enter end date after "
            f"`{start_date.strftime('%d.%m.%Y')}`:",
            parse_mode="Markdown"
        )
        return ENTER_CUSTOM_END

    # Check if future date
    if end_date > today:
        await update.message.reply_text(
            f"❌ *Invalid date!*\n\n"
            f"End date cannot be in the future.\n"
            f"Max date: `{today.strftime('%d.%m.%Y')}` (today)\n\n"
            f"Please enter a valid end date:",
            parse_mode="Markdown"
        )
        return ENTER_CUSTOM_END

    group_id = context.user_data['report_group_id']
    period_label = f"{start_date.strftime('%d.%m.%Y')} → {end_date.strftime('%d.%m.%Y')}"

    await generate_report(
        update.message, context, group_id,
        start_date, end_date, period_label
    )
    return ConversationHandler.END


def _fmt_join(joined_date):
    """Format a joined_date (date or datetime) as 'Mon DD'."""
    if joined_date is None:
        return "?"
    if hasattr(joined_date, 'strftime'):
        return joined_date.strftime('%b %d')
    try:
        return datetime.strptime(str(joined_date), '%Y-%m-%d').strftime('%b %d')
    except Exception:
        return str(joined_date)


def _download_keyboard(group_id):
    return InlineKeyboardMarkup([
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


async def _generate_simple_report(
    message, context, group, currency,
    start_date, end_date, period_label
):
    """Single-period report (no member exits during the period)."""
    group_id = group[0]

    expenses, splits = get_balances(group_id, start_date, end_date)

    if not expenses:
        await message.reply_text(
            f"📊 *{group[1]}*\n"
            f"📅 {period_label}\n\n"
            f"❌ No expenses found in this period.",
            parse_mode="Markdown"
        )
        return

    all_members = get_members_active_during_period(
        group_id, start_date, end_date
    )
    balances = calculate_balances(expenses, splits)
    all_expenses = get_expenses_for_report(group_id, start_date, end_date)

    for m in all_members:
        uid, name = m[0], m[1]
        if uid not in balances:
            balances[uid] = {
                'name': name, 'paid': 0.0,
                'share': 0.0, 'balance': 0.0
            }

    settlements = calculate_settlements(balances)

    report = "📊 *SplitBazar — Expense Report*\n"
    report += f"🏠 {group[1]}\n"
    report += f"📅 {period_label}\n"
    report += "━━━━━━━━━━━━━━━━━━━━\n\n"

    report += "👥 *MEMBERS:*\n"
    for m in all_members:
        uid, name, joined_date, _left = m[0], m[1], m[2], m[3]
        report += f"   {name} (joined: {_fmt_join(joined_date)})\n"
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

    await message.reply_text(
        report,
        parse_mode="Markdown",
        reply_markup=_download_keyboard(group_id)
    )

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


async def _generate_split_report(
    message, context, group, currency,
    start_date, end_date, period_label, left_members
):
    """Two-part report when a member left during the period (Q2)."""
    from datetime import timedelta
    group_id = group[0]

    left_uid, left_name, left_date = left_members[0]
    part2_start = left_date + timedelta(days=1)

    # ── PART 1 ──
    exp1, splits1 = get_balances(group_id, start_date, left_date)
    balances1 = calculate_balances(exp1, splits1)
    members1 = get_members_active_during_period(
        group_id, start_date, left_date
    )
    for m in members1:
        uid, name = m[0], m[1]
        if uid not in balances1:
            balances1[uid] = {
                'name': name, 'paid': 0.0,
                'share': 0.0, 'balance': 0.0
            }
    settlements1 = calculate_settlements(balances1)

    # ── PART 2 ──
    exp2, splits2 = get_balances(group_id, part2_start, end_date)
    balances2 = calculate_balances(exp2, splits2)
    members2 = get_members_active_during_period(
        group_id, part2_start, end_date
    )
    for m in members2:
        uid, name = m[0], m[1]
        if uid not in balances2:
            balances2[uid] = {
                'name': name, 'paid': 0.0,
                'share': 0.0, 'balance': 0.0
            }

    # ── Active members combined balance ──
    active_combined = {}
    for uid, data in balances1.items():
        if uid == left_uid:
            continue
        active_combined[uid] = dict(data)

    for uid, data in balances2.items():
        if uid in active_combined:
            active_combined[uid]['paid'] += data['paid']
            active_combined[uid]['share'] += data['share']
            active_combined[uid]['balance'] += data['balance']
        else:
            active_combined[uid] = dict(data)

    final_settlements = calculate_settlements(active_combined)

    frozen_settlements = [
        s for s in settlements1
        if s['to_id'] == left_uid or s['from_id'] == left_uid
    ]

    # ── Build report text ──
    report = "📊 *SplitBazar — Complete Report*\n"
    report += f"🏠 {group[1]}\n"
    report += f"📅 {period_label}\n"
    report += "━━━━━━━━━━━━━━━━━━━━\n\n"

    n1 = len(members1)
    report += (
        f"📋 *PART 1 ({start_date.strftime('%b %d')} – "
        f"{left_date.strftime('%b %d')}) — {n1} members:*\n"
    )
    for uid, data in balances1.items():
        bal = float(data['balance'])
        frozen = " 🔒 _(FROZEN)_" if uid == left_uid else ""
        if abs(bal) < 0.01:
            s = "settled ✅"
        elif bal > 0:
            s = f"+{bal:.0f} gets back 💚"
        else:
            s = f"{bal:.0f} owes ⚠️"
        report += f"   {data['name']} : {s}{frozen}\n"

    left_bal = balances1.get(left_uid, {}).get('balance', 0)
    report += (
        f"\n🚪 *{left_name.upper()} LEFT ON "
        f"{left_date.strftime('%b %d').upper()}*\n"
    )
    if abs(left_bal) > 0.01:
        if left_bal > 0:
            report += (
                f"   {left_name} is owed: "
                f"`{left_bal:.2f}` {currency}\n"
            )
        else:
            report += (
                f"   {left_name} owes: "
                f"`{abs(left_bal):.2f}` {currency}\n"
            )
    report += f"   Record FROZEN ✅\n"
    report += (
        f"   {left_name} will NOT appear "
        f"in future expense calculations.\n\n"
    )

    report += "━━━━━━━━━━━━━━━━━━━━\n\n"

    n2 = len(members2)
    report += (
        f"📋 *PART 2 ({part2_start.strftime('%b %d')} – "
        f"{end_date.strftime('%b %d')}) — {n2} members:*\n"
    )
    if exp2:
        for uid, data in balances2.items():
            bal = float(data['balance'])
            if abs(bal) < 0.01:
                s = "settled ✅"
            elif bal > 0:
                s = f"+{bal:.0f} gets back 💚"
            else:
                s = f"{bal:.0f} owes ⚠️"
            report += f"   {data['name']} : {s}\n"
    else:
        report += "   _(No expenses in this period)_\n"

    report += "\n━━━━━━━━━━━━━━━━━━━━\n"
    report += "💸 *FINAL SETTLEMENT:*\n\n"
    report += "_Active members (combined):_\n"
    for uid, data in active_combined.items():
        b = data['balance']
        report += f"   {data['name']} : `{b:+.2f}`\n"
    report += "\n"

    if final_settlements:
        for s in final_settlements:
            report += (
                f"👤 *{s['from_name']}* → pays → "
                f"*{s['to_name']}* : "
                f"`{s['amount']:.2f}` {currency}\n"
            )
    else:
        report += "✅ All active members settled!\n"

    if frozen_settlements:
        report += "\n🔒 *Frozen record (separate):*\n"
        for s in frozen_settlements:
            report += (
                f"   {s['from_name']} → pays → "
                f"{s['to_name']} : "
                f"`{s['amount']:.2f}` {currency} _(pending)_\n"
            )

    report += "\n━━━━━━━━━━━━━━━━━━━━\n"
    report += (
        "ℹ️ _3-month lock applies to active group only — "
        "frozen debts never trigger lock._\n"
    )

    await message.reply_text(
        report,
        parse_mode="Markdown",
        reply_markup=_download_keyboard(group_id)
    )

    all_expenses = get_expenses_for_report(group_id, start_date, end_date)

    combined_for_pdf = dict(active_combined)
    if left_uid in balances1:
        frozen_entry = dict(balances1[left_uid])
        frozen_entry['name'] = f"{left_name} (FROZEN)"
        combined_for_pdf[left_uid] = frozen_entry

    if 'report_cache' not in context.bot_data:
        context.bot_data['report_cache'] = {}
    context.bot_data['report_cache'][group_id] = {
        'group_name': group[1],
        'currency': currency,
        'period_label': period_label,
        'balances': combined_for_pdf,
        'settlements': final_settlements,
        'expenses': all_expenses,
    }


async def generate_report(
    message, context, group_id, start_date, end_date, period_label
):
    try:
        group = get_group_by_id(group_id)
        currency = group[2]

        left_members = get_members_who_left(group_id, start_date, end_date)

        if left_members:
            await _generate_split_report(
                message, context, group, currency,
                start_date, end_date, period_label, left_members
            )
        else:
            await _generate_simple_report(
                message, context, group, currency,
                start_date, end_date, period_label
            )

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