from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler, filters

MENU_BUTTON_FILTER = filters.Regex(
    r"^(➕ Add Expense|📊 View Report|✏️ Edit Expense|"
    r"👥 My Groups|🎯 My Target|📝 ToDo List|"
    r"⚙️ Settings|💬 Group Chat)$"
)


async def exit_to_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """End the current conversation and re-inject the update so the
    correct handler processes the menu button press in one step."""
    context.user_data.clear()
    await context.application.update_queue.put(update)
    return ConversationHandler.END
