from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, MessageHandler, ConversationHandler,
    CallbackQueryHandler, filters, CommandHandler
)
from bot.database.queries import (
    get_user_groups, save_user,
    add_todo_item, get_todo_items,
    mark_todo_done, mark_todo_undone,
    delete_todo_item, clear_done_items
)

# States
SELECT_GROUP = 0
SHOW_LIST = 1
ENTER_ITEM = 2
ENTER_QUANTITY = 3

async def todo_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user
    save_user(
        user.id, user.username,
        user.first_name, user.last_name
    )
    groups = get_user_groups(user.id)

    if not groups:
        await update.message.reply_text(
            "❌ You are not in any group yet!\n\n"
            "Create or join a group first."
        )
        return ConversationHandler.END

    keyboard = []
    for group in groups:
        keyboard.append([InlineKeyboardButton(
            f"🏠 {group[1]} ({group[2]})",
            callback_data=f"todo_group_{group[0]}"
        )])

    await update.message.reply_text(
        "📝 *ToDo List*\n\nSelect group:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_GROUP


async def show_todo_list(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    group_id = int(query.data.split("_")[2])
    context.user_data['todo_group_id'] = group_id

    await display_todo_list(query.message, group_id)
    return SHOW_LIST


async def display_todo_list(message, group_id):
    from bot.database.queries import get_group_by_id
    group = get_group_by_id(group_id)
    items = get_todo_items(group_id)

    pending = [i for i in items if not i[3]]
    done = [i for i in items if i[3]]

    def escape(text):
        if not text:
            return ""
        chars = ['_', '*', '[', ']', '(', ')', '~', '`',
                 '>', '#', '+', '-', '=', '|', '{', '}',
                 '.', '!']
        for c in chars:
            text = text.replace(c, f"\\{c}")
        return text

    text = f"📝 *ToDo List — {escape(group[1])}*\n"
    text += f"━━━━━━━━━━━━━━━━━━━━\n\n"

    if pending:
        text += "🛒 *Shopping List:*\n\n"
        for item in pending:
            qty = f" × {escape(str(item[2]))}" if item[2] else ""
            text += f"☐ {escape(item[1])}{qty}\n"
            text += f"   Added by: {escape(item[5])}\n\n"
    else:
        text += "✅ No pending items\\!\n\n"

    if done:
        text += f"━━━━━━━━━━━━━━━━━━━━\n"
        text += f"✅ *Done \\({len(done)} items\\):*\n\n"
        for item in done:
            qty = f" × {escape(str(item[2]))}" if item[2] else ""
            text += f"☑️ {escape(item[1])}{qty}\n"
            text += f"   Bought by: {escape(item[6])}\n\n"

    keyboard = []

    # Mark done buttons for pending items
    if pending:
        for item in pending:
            qty = f" × {item[2]}" if item[2] else ""
            keyboard.append([InlineKeyboardButton(
                f"✅ {item[1]}{qty}",
                callback_data=f"todo_done_{item[0]}"
            )])

    # Action buttons
    keyboard.append([
        InlineKeyboardButton(
            "➕ Add Item",
            callback_data="todo_add"
        ),
    ])

    if done:
        keyboard.append([
            InlineKeyboardButton(
                "🗑️ Clear Done",
                callback_data="todo_cleardone"
            ),
        ])

    await message.reply_text(
        text,
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_todo_action(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    action = query.data.split("_")[1]
    group_id = context.user_data['todo_group_id']
    user = query.from_user

    if action == "add":
        await query.message.reply_text(
            "➕ *Add Item*\n\n"
            "Enter item name:\n"
            "Example: `Rice` or `Rice × 2`\n\n"
            "Or type like: `Rice, 2` to add with quantity",
            parse_mode="Markdown"
        )
        return ENTER_ITEM

    elif action == "done":
        item_id = int(query.data.split("_")[2])
        mark_todo_done(item_id, user.id)
        await query.message.reply_text(
            "✅ Item marked as done!"
        )
        await display_todo_list(query.message, group_id)
        return SHOW_LIST

    elif action == "cleardone":
        clear_done_items(group_id)
        await query.message.reply_text(
            "🗑️ Done items cleared!"
        )
        await display_todo_list(query.message, group_id)
        return SHOW_LIST

    elif action == "group":
        group_id = int(query.data.split("_")[2])
        context.user_data['todo_group_id'] = group_id
        await display_todo_list(query.message, group_id)
        return SHOW_LIST

    return SHOW_LIST


async def enter_item(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    menu_buttons = ["➕ Add Expense", "📊 View Report", "✏️ Edit Expense",
    "👥 My Groups", "🎯 My Target", "💬 Group Chat", "📝 ToDo List", "⚙️ Settings"]

    if update.message.text in menu_buttons:
        await update.message.reply_text("⚠️ Please don't use menu buttons during this step!")
        return ENTER_GROUP_NAME  # 👈 change this to match the current state
    
    user = update.effective_user
    group_id = context.user_data['todo_group_id']
    text = update.message.text.strip()

    # Parse item and quantity
    # Supports: "Rice, 2" or "Rice × 2" or just "Rice"
    item_name = text
    quantity = None

    if "," in text:
        parts = text.split(",", 1)
        item_name = parts[0].strip()
        quantity = parts[1].strip()
    elif "×" in text:
        parts = text.split("×", 1)
        item_name = parts[0].strip()
        quantity = parts[1].strip()
    elif "x" in text.lower():
        parts = text.lower().split("x", 1)
        if parts[1].strip().isdigit():
            item_name = parts[0].strip()
            quantity = parts[1].strip()

    add_todo_item(group_id, user.id, item_name, quantity)

    qty_text = f" × {quantity}" if quantity else ""

    # Notify all group members
    from bot.database.queries import (
        get_active_group_members, get_group_by_id
    )
    group = get_group_by_id(group_id)
    members = get_active_group_members(group_id)

    for member in members:
        if member[0] != user.id:
            try:
                await update.get_bot().send_message(
                    chat_id=member[0],
                    text=(
                        f"📝 *[{group[1]}] New ToDo Item!*\n\n"
                        f"➕ {item_name}{qty_text}\n"
                        f"Added by: {user.first_name}"
                    ),
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    await update.message.reply_text(
        f"✅ Added to list!\n\n"
        f"📝 {item_name}{qty_text}"
    )

    await display_todo_list(update.message, group_id)
    return SHOW_LIST


async def cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END


def register_todo_handlers(app):
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex("^📝 ToDo List$"),
                todo_start
            )
        ],
        states={
            SELECT_GROUP: [
                CallbackQueryHandler(
                    show_todo_list,
                    pattern="^todo_group_"
                )
            ],
            SHOW_LIST: [
                CallbackQueryHandler(
                    handle_todo_action,
                    pattern="^todo_"
                )
            ],
            ENTER_ITEM: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    enter_item
                )
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
        allow_reentry=True
    )
    app.add_handler(conv_handler)