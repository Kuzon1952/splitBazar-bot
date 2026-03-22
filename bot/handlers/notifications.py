from telegram import Update
import logging
from datetime import datetime, timedelta
from telegram.ext import ContextTypes
from bot.database.queries import (
    get_all_active_groups,
    get_active_group_members,
    get_last_expense_date,
    get_group_last_reset,
    is_group_locked,
    set_group_locked
)

logger = logging.getLogger(__name__)


# ─── INACTIVITY REMINDER ─────────────────────────────────

async def check_inactivity(context: ContextTypes.DEFAULT_TYPE):
    """Runs every day — reminds members inactive for 3+ days"""
    logger.info("Running inactivity check...")
    today = datetime.now().date()
    groups = get_all_active_groups()

    for group in groups:
        group_id = group[0]
        group_name = group[1]

        if is_group_locked(group_id):
            continue

        members = get_active_group_members(group_id)

        for member in members:
            user_id = member[0]
            name = member[1]

            last_date = get_last_expense_date(group_id, user_id)

            if last_date is None:
                days_inactive = 999
            else:
                days_inactive = (today - last_date).days

            if days_inactive >= 3:
                try:
                    await context.bot.send_message(
                        chat_id=user_id,
                        text=(
                            f"😴 *[{group_name}]*\n\n"
                            f"You haven't added any expenses "
                            f"for *{days_inactive} days!*\n\n"
                            f"Last entry : "
                            f"{last_date.strftime('%d.%m.%Y') if last_date else 'Never'}\n"
                            f"Today      : {today.strftime('%d.%m.%Y')}\n\n"
                            f"Did you forget to log something?"
                        ),
                        parse_mode="Markdown"
                    )
                    logger.info(
                        f"Inactivity reminder sent to {name} "
                        f"for group {group_name}"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to send inactivity reminder "
                        f"to {user_id}: {e}"
                    )


# ─── LARGE EXPENSE ALERT ─────────────────────────────────

async def send_large_expense_alert(
    context, group_id, group_name,
    currency, payer_name, amount,
    expense_type, description, date
):
    """Call this after saving a large expense"""
    members = get_active_group_members(group_id)

    for member in members:
        try:
            await context.bot.send_message(
                chat_id=member[0],
                text=(
                    f"💸 *[{group_name}]*\n\n"
                    f"*{payer_name}* added a large expense!\n\n"
                    f"Amount     : {amount:.2f} {currency}\n"
                    f"Type       : {expense_type}\n"
                    f"Date       : {date}\n"
                    f"Description: {description or 'None'}"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(
                f"Failed to send large expense alert "
                f"to {member[0]}: {e}"
            )


# ─── RESET DEADLINE WARNING ──────────────────────────────

async def check_reset_deadline(
    context: ContextTypes.DEFAULT_TYPE
):
    """Runs every day — warns 7 days before month end"""
    logger.info("Running reset deadline check...")
    today = datetime.now()
    groups = get_all_active_groups()

    for group in groups:
        group_id = group[0]
        group_name = group[1]

        if is_group_locked(group_id):
            continue

        # Check if today is 7 days before month end
        days_in_month = (
            today.replace(month=today.month % 12 + 1, day=1)
            - timedelta(days=1)
        ).day
        days_left = days_in_month - today.day

        if days_left == 7:
            members = get_active_group_members(group_id)
            for member in members:
                try:
                    await context.bot.send_message(
                        chat_id=member[0],
                        text=(
                            f"📅 *[{group_name}]*\n\n"
                            f"Settlement period ends in "
                            f"*7 days!*\n\n"
                            f"Please:\n"
                            f"1. View your final report\n"
                            f"2. Download PDF or Excel\n"
                            f"3. Confirm reset\n\n"
                            f"Deadline: "
                            f"{(today + timedelta(days=7)).strftime('%d.%m.%Y')}"
                        ),
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to send reset warning "
                        f"to {member[0]}: {e}"
                    )


# ─── 3-MONTH FORCE LOCK ──────────────────────────────────

async def check_force_lock(
    context: ContextTypes.DEFAULT_TYPE
):
    """Runs every day — locks group after 3 months no reset"""
    logger.info("Running force lock check...")
    groups = get_all_active_groups()
    today = datetime.now()

    for group in groups:
        group_id = group[0]
        group_name = group[1]
        admin_id = group[3]

        last_reset = get_group_last_reset(group_id)

        if last_reset is None:
            # Use group creation as reference
            continue

        months_since_reset = (
            (today.year - last_reset.year) * 12
            + today.month - last_reset.month
        )

        if months_since_reset >= 3 and not is_group_locked(group_id):
            # Lock the group
            set_group_locked(group_id, True)

            members = get_active_group_members(group_id)
            for member in members:
                try:
                    await context.bot.send_message(
                        chat_id=member[0],
                        text=(
                            f"🔒 *[{group_name}] GROUP LOCKED!*\n\n"
                            f"Your group has not been reset "
                            f"for *3 months!*\n\n"
                            f"You must reset the group before "
                            f"adding new expenses.\n\n"
                            f"Please contact your group admin."
                        ),
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to send lock warning "
                        f"to {member[0]}: {e}"
                    )

            # Extra message to admin
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=(
                        f"🔒 *[{group_name}] GROUP LOCKED!*\n\n"
                        f"Your group has been locked after "
                        f"3 months without reset.\n\n"
                        f"Go to ⚙️ Settings → Reset Group "
                        f"to unlock."
                    ),
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(
                    f"Failed to send lock warning "
                    f"to admin {admin_id}: {e}"
                )

async def test_notifications(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Test command — triggers all notifications immediately"""
    await update.message.reply_text(
        "🧪 Testing all notifications..."
    )

    # Test inactivity
    await check_inactivity(context)
    await update.message.reply_text(
        "✅ Inactivity check done!"
    )

    # Test reset deadline
    await check_reset_deadline(context)
    await update.message.reply_text(
        "✅ Reset deadline check done!"
    )

    # Test force lock
    await check_force_lock(context)
    await update.message.reply_text(
        "✅ Force lock check done!"
    )

    # Test large expense alert
    groups = get_all_active_groups()
    if groups:
        group = groups[0]
        await send_large_expense_alert(
            context,
            group[0],
            group[1],
            group[2],
            update.effective_user.first_name,
            1500.00,
            "Shared",
            "Test large expense",
            datetime.now().strftime('%d.%m.%Y')
        )
        await update.message.reply_text(
            "✅ Large expense alert sent!"
        )

    await update.message.reply_text(
        "🎉 All notification tests complete!"
    )

def setup_notifications(app):
    job_queue = app.job_queue

    # Scheduled jobs
    job_queue.run_daily(
        check_inactivity,
        time=datetime.strptime("10:00", "%H:%M").time(),
        name="inactivity_check"
    )
    job_queue.run_daily(
        check_reset_deadline,
        time=datetime.strptime("09:00", "%H:%M").time(),
        name="reset_deadline_check"
    )
    job_queue.run_daily(
        check_force_lock,
        time=datetime.strptime("08:00", "%H:%M").time(),
        name="force_lock_check"
    )

    # Test command
    from telegram.ext import CommandHandler
    app.add_handler(
        CommandHandler("test_notify", test_notifications)
    )

    logger.info("Notification jobs scheduled ✅")