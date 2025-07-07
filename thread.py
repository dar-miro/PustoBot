from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, filters
)

from PustoBot.sheets import set_main_roles, normalize_title

# Стан розмови
ASK_TITLE, ASK_MEMBERS = range(2)

# 🧠 Памʼять тайтлів за гілкою
thread_title_map = {}  # { thread_id: normalized_title }

def set_thread_title(thread_id, title):
    thread_title_map[thread_id] = normalize_title(title)

def get_thread_title(thread_id):
    return thread_title_map.get(thread_id)

# 🧵 /thread — старт розмови
async def thread_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 Введи назву тайтлу для цієї гілки:")
    return ASK_TITLE

# Назва тайтлу
async def ask_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title = update.message.text.strip()
    thread_id = update.message.message_thread_id or update.message.chat_id

    # Зберігаємо привʼязку гілка → тайтл
    set_thread_title(thread_id, title)
    context.user_data["original_title"] = title  # збережемо без normalize

    await update.message.reply_text(
        "✅ Тайтл збережено. Тепер введи учасників проєкту у форматі:\n"
        "`клін - Nick1, переклад - Nick2, тайп - Nick3, ред - Nick4`",
        parse_mode="Markdown"
    )
    return ASK_MEMBERS

# Учасники
async def ask_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    members_text = update.message.text.strip()
    title = context.user_data.get("original_title")

    roles_map = {}
    for part in members_text.split(","):
        if "-" in part:
            role, nick = [p.strip() for p in part.split("-", 1)]
            roles_map[role.lower()] = nick  # роль — у нижньому регістрі, нік — як є

    success = set_main_roles(title, roles_map)

    if success:
        await update.message.reply_text("✅ Команду збережено.")
    else:
        await update.message.reply_text("⚠️ Не вдалося зберегти команду. Можливо, тайтл не знайдено в таблиці.")
    return ConversationHandler.END

# Вихід
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Дію скасовано.")
    return ConversationHandler.END

# Handler для додавання в main.py
def get_thread_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("thread", thread_command)],
        states={
            ASK_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_title)],
            ASK_MEMBERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_members)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="thread_conversation",
        persistent=False
    )
