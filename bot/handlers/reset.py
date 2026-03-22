from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, MessageHandler, ConversationHandler,
    CallbackQueryHandler, filters, CommandHandler
)
from bot.database.queries import (
    get_user_groups, get_group_by_id,
    get_active_group_members,
    get_balances, get_group_by_id,
    update_group_last_reset,
    set_group_locked, archive_expenses,
    get_reset_status, get_total_expenses_count,
    get_first_expense_date
)
from bot.utils.calculations import (
    calculate_balances, calculate_settlements
)
from bot.utils.report_generator import (
    generate_pdf_report, generate_excel_report
)
from datetime import datetime
import os

# States
SELECT_GROUP = 0
CONFIRM_RESET = 1
VERIFY_PASSWORD = 2


async def reset_check(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Check reset status — called from notifications"""
    pass


async def reset_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user
    groups = get_user_groups(user.id)

    # Only admin can reset
    admin_groups = [g for g in groups if g[4] == user.id]

    if not admin_groups:
        await update.message.reply_text(
            "❌ Only group admin can reset the group!"
        )
        return ConversationHandler.END

    keyboard = []
    for group in admin_groups:
        reset_status = get_reset_status(group[0])
        last_reset = reset_status[0] if reset_status else None
        is_locked = reset_status[1] if reset_status else False

        lock_icon = "🔒" if is_locked else "🏠"
        last_reset_text = (
            last_reset.strftime('%d.%m.%Y')
            if last_reset else "Never"
        )

        keyboard.append([InlineKeyboardButton(
            f"{lock_icon} {group[1]} "
            f"(Last reset: {last_reset_text})",
            callback_data=f"reset_group_{group[0]}"
        )])

    await update.message.reply_text(
        "🔄 *Reset Group*\n\n"
        "Select group to reset:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_GROUP


async def select_reset_group(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    group_id = int(query.data.split("_")[2])
    context.user_data['reset_group_id'] = group_id

    group = get_group_by_id(group_id)
    expense_count = get_total_expenses_count(group_id)
    first_date = get_first_expense_date(group_id)
    now = datetime.now()

    if expense_count == 0:
        await query.message.reply_text(
            "❌ No expenses to reset!"
        )
        return ConversationHandler.END

    context.user_data['reset_expense_count'] = expense_count
    context.user_data['reset_first_date'] = first_date
    context.user_data['reset_now'] = now

    await query.message.reply_text(
        f"🔄 *Reset {group[1]}?*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 Total expenses : {expense_count}\n"
        f"📅 Period start   : "
        f"{first_date.strftime('%d.%m.%Y') if first_date else 'N/A'}\n"
        f"📅 Period end     : {now.strftime('%d.%m.%Y')}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🔐 *Enter your reset password\n"
        f"to confirm:*",
        parse_mode="Markdown"
    )
    return VERIFY_PASSWORD


async def verify_password(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    password = update.message.text.strip()
    group_id = context.user_data['reset_group_id']
    group = get_group_by_id(group_id)

    from bot.database.queries import verify_reset_password
    is_correct = verify_reset_password(group_id, password)

    if not is_correct:
        await update.message.reply_text(
            "❌ *Wrong password!*\n\n"
            "Reset cancelled for security.\n"
            "Please try again from Settings.",
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    # Password correct — show options
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "📥 Download & Reset",
            callback_data="resetconfirm_download"
        )],
        [InlineKeyboardButton(
            "🔄 Reset Only",
            callback_data="resetconfirm_only"
        )],
        [InlineKeyboardButton(
            "❌ Cancel",
            callback_data="resetconfirm_cancel"
        )],
    ])

    await update.message.reply_text(
        f"✅ *Password correct!*\n\n"
        f"Choose reset option:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    return CONFIRM_RESET

async def confirm_reset(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    action = query.data.split("_")[1]

    if action == "cancel":
        await query.message.reply_text("❌ Reset cancelled.")
        return ConversationHandler.END

    group_id = context.user_data['reset_group_id']
    group = get_group_by_id(group_id)
    currency = group[2]
    members = get_active_group_members(group_id)

    await query.message.reply_text(
        "⏳ Generating final report...\n"
        "Please wait."
    )

    # Generate final report
    now = datetime.now()
    first_date = get_first_expense_date(group_id)

    if first_date:
        start_date = first_date
    else:
        start_date = now.replace(day=1)

    period_label = (
        f"{start_date.strftime('%d.%m.%Y')} → "
        f"{now.strftime('%d.%m.%Y')}"
    )

    expenses, splits = get_balances(
        group_id, start_date, now
    )

    if expenses:
        from bot.database.queries import get_expenses_for_report
        balances = calculate_balances(expenses, splits)
        settlements = calculate_settlements(balances)
        all_expenses = get_expenses_for_report(
            group_id, start_date, now
        )

        # Build text report
        report = f"📊 FINAL REPORT — {group[1]}\n"
        report += f"📅 {period_label}\n"
        report += f"━━━━━━━━━━━━━━━━━━━━\n\n"
        report += f"💰 Summary per person:\n\n"

        for user_id, data in balances.items():
            if abs(data['balance']) < 0.01:
                emoji = "✅"
            elif data['balance'] > 0:
                emoji = "💚"
            else:
                emoji = "⚠️"

            report += (
                f"{emoji} {data['name']}\n"
                f"   Paid   : {data['paid']:.2f} {currency}\n"
                f"   Share  : {data['share']:.2f} {currency}\n"
                f"   Balance: {data['balance']:+.2f} {currency}\n\n"
            )

        report += f"━━━━━━━━━━━━━━━━━━━━\n"
        report += f"💸 Final Settlement:\n\n"

        if settlements:
            for s in settlements:
                report += (
                    f"{s['from_name']} → pays → "
                    f"{s['to_name']}: "
                    f"{s['amount']:.2f} {currency}\n"
                )
        else:
            report += "✅ Everyone is settled!\n"

        # Send report to all members
        for member in members:
            try:
                await context.bot.send_message(
                    chat_id=member[0],
                    text=(
                        f"📊 *[{group[1]}] Final Report*\n\n"
                        + report
                    ),
                    parse_mode="Markdown"
                )
            except Exception:
                pass

        # Generate and send files if requested
        if action == "download":
            try:
                pdf_path = generate_pdf_report(
                    group[1], currency, period_label,
                    balances, settlements, all_expenses
                )
                excel_path = generate_excel_report(
                    group[1], currency, period_label,
                    balances, settlements, all_expenses
                )

                for member in members:
                    try:
                        with open(pdf_path, 'rb') as f:
                            await context.bot.send_document(
                                chat_id=member[0],
                                document=f,
                                filename=f"FinalReport_{group[1]}.pdf",
                                caption=f"📄 Final PDF Report\n{period_label}"
                            )
                        with open(excel_path, 'rb') as f:
                            await context.bot.send_document(
                                chat_id=member[0],
                                document=f,
                                filename=f"FinalReport_{group[1]}.xlsx",
                                caption=f"📊 Final Excel Report\n{period_label}"
                            )
                    except Exception:
                        pass

                # Cleanup
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)
                if os.path.exists(excel_path):
                    os.remove(excel_path)

            except Exception as e:
                await query.message.reply_text(
                    f"⚠️ Could not generate files: {e}"
                )

    # Archive all expenses
    archive_expenses(group_id)

    # Update reset timestamp
    update_group_last_reset(group_id)

    # Unlock group if locked
    set_group_locked(group_id, False)

    # Notify all members
    for member in members:
        try:
            await context.bot.send_message(
                chat_id=member[0],
                text=(
                    f"✅ *[{group[1]}] Group Reset!*\n\n"
                    f"📊 Final report sent above.\n"
                    f"🗓️ New period started: "
                    f"{now.strftime('%d.%m.%Y')}\n\n"
                    f"Fresh start! 🎉"
                ),
                parse_mode="Markdown"
            )
        except Exception:
            pass

    await query.message.reply_text(
        f"✅ *Group Reset Complete!*\n\n"
        f"🏠 Group    : {group[1]}\n"
        f"📅 Period   : {period_label}\n"
        f"👥 Members  : {len(members)}\n\n"
        f"📊 Final report sent to all members.\n"
        f"🗓️ New period: {now.strftime('%d.%m.%Y')}\n\n"
        f"Fresh start! 🎉",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


async def cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


def register_reset_handlers(app):
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("^🔄 Reset Group$"),
                reset_start
            )
        ],
        states={
            SELECT_GROUP: [
                CallbackQueryHandler(
                    select_reset_group,
                    pattern="^reset_group_"
                )
            ],
            VERIFY_PASSWORD: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    verify_password
                )
            ],
            CONFIRM_RESET: [
                CallbackQueryHandler(
                    confirm_reset,
                    pattern="^resetconfirm_"
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
        allow_reentry=True
    )
    app.add_handler(conv_handler)