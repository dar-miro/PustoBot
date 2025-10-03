from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, filters
)

from PustoBot.sheets import set_main_roles, normalize_title, get_title_number_and_name # Додано імпорт

# Стан розмови
ASK_TITLE_AND_NUMBER, ASK_MEMBERS = range(2) 

# 🧠 Памʼять тайтлів за гілкою: { thread_id: (title_number, original_title) }
thread_title_map = {} 

def set_thread_title_and_number(thread_id, title_number, title_name):
    """Зберігає прив'язку гілка → (Номер, Назва)."""
    thread_title_map[thread_id] = (title_number, title_name)

def get_thread_title_and_number(thread_id):
    """Повертає (title_number, title_name)."""
    return thread_title_map.get(thread_id, (None, None))

def get_thread_number(thread_id):
    """Повертає лише номер тайтлу для використання в інших модулях."""
    return thread_title_map.get(thread_id, (None, None))[0]

# 🧵 /thread — старт розмови. Тепер очікує Номер та Назву.
async def thread_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📝 Введи *Номер Тайтлу* та його *Назву* для цієї гілки. Наприклад: `1 Відьмоварта`", parse_mode="Markdown")
    return ASK_TITLE_AND_NUMBER

# Обробка Номера та Назви тайтлу
async def ask_title_and_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Очікуємо: [Номер] [Назва Тайтлу...]
    parts = update.message.text.strip().split(maxsplit=1)
    
    if len(parts) < 2 or not parts[0].isdigit():
        await update.message.reply_text("⚠️ Невірний формат. Введи у форматі: `1 Назва Тайтлу`")
        return ASK_TITLE_AND_NUMBER
        
    title_number = parts[0]
    title_name = parts[1]
    
    thread_id = update.message.message_thread_id or update.message.chat_id

    # Зберігаємо привʼязку гілка → (Номер, Назва)
    set_thread_title_and_number(thread_id, title_number, title_name)
    context.user_data["title_number"] = title_number 
    context.user_data["original_title"] = title_name 

    await update.message.reply_text(
        f"✅ Тайтл *№{title_number} - {title_name}* збережено. Тепер введи учасників проєкту у форматі:\n"
        "`клін - Nick1, переклад - Nick2, тайп - Nick3, ред - Nick4`",
        parse_mode="Markdown"
    )
    return ASK_MEMBERS

# Учасники
async def ask_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    members_text = update.message.text.strip()
    title_number = context.user_data.get("title_number")

    roles_map = {}
    for part in members_text.split(","):
        if "-" in part:
            role, nick = [p.strip() for p in part.split("-", 1)]
            roles_map[role.lower()] = nick 

    # Передаємо Номер Тайтлу у функцію збереження
    success = set_main_roles(title_number, roles_map) 

    if success:
        await update.message.reply_text("✅ Команду збережено.")
    else:
        await update.message.reply_text("⚠️ Не вдалося зберегти команду. Можливо, тайтл з таким номером не знайдено в таблиці.")
    return ConversationHandler.END

# Нова команда /threadNum
async def threadnum_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Відповідає [назва_тайтлу - номер] для поточної гілки."""
    thread_id = update.message.message_thread_id or update.message.chat_id
    title_number, title_name = get_thread_title_and_number(thread_id)
    
    if title_number and title_name:
        await update.message.reply_text(f"*{title_name}* - *{title_number}*", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ Ця гілка не прив'язана до жодного тайтлу. Використайте `/thread` для прив'язки.")


# Вихід
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Дію скасовано.")
    return ConversationHandler.END

# Handler для додавання в main.py
def get_thread_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("thread", thread_command)],
        states={
            ASK_TITLE_AND_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_title_and_number)],
            ASK_MEMBERS: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_members)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="thread_conversation",
        persistent=False
    )

def get_threadnum_handler():
    """Повертає хендлер для команди /threadNum."""
    return CommandHandler("threadNum", threadnum_command)