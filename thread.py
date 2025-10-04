# thread.py
from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CommandHandler,
    MessageHandler, filters
)

from PustoBot.sheets import get_title_number_and_name 

# Стан розмови
ASK_TITLE_IDENTIFIER = range(1) 

# 🧠 Памʼять тайтлів за гілкою: { thread_id: (title_number, original_title) }
thread_title_map = {} 

def set_thread_title_and_number(thread_id, title_number, title_name):
    """Зберігає прив'язку гілка → (Номер, Назва)."""
    thread_title_map[thread_id] = (str(title_number), title_name)

def get_thread_title_and_number(thread_id):
    """Повертає (title_number, title_name)."""
    return thread_title_map.get(thread_id, (None, None))

def get_thread_number(thread_id):
    """Повертає лише номер тайтлу для використання в інших модулях (завдання 2)."""
    return thread_title_map.get(thread_id, (None, None))[0]

# 🧵 /thread — старт розмови. Очікує Назву або Номер тайтлу.
async def thread_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "supergroup":
        await update.message.reply_text("⚠️ Команда `/thread` доступна лише в гілках супергруп.")
        return ConversationHandler.END
    
    # Використовуємо message_thread_id для прив'язки
    if not update.message.message_thread_id:
        await update.message.reply_text("⚠️ Цю команду потрібно використовувати в гілці (топіку)!")
        return ConversationHandler.END

    await update.message.reply_text("📝 Введи *Назву* або *Номер* тайтлу для прив'язки до цієї гілки:", parse_mode="Markdown")
    return ASK_TITLE_IDENTIFIER

# Назва або Номер тайтлу
async def ask_title_identifier(update: Update, context: ContextTypes.DEFAULT_TYPE):
    title_identifier = update.message.text.strip()
    thread_id = update.message.message_thread_id 

    # 1. Знаходимо номер та назву тайтлу
    title_number, original_title = get_title_number_and_name(title_identifier)

    if not original_title:
        await update.message.reply_text(f"⚠️ Тайтл '{title_identifier}' не знайдено в таблиці.")
        return ConversationHandler.END

    # 2. Зберігаємо прив'язку гілка → (Номер, Назва)
    set_thread_title_and_number(thread_id, title_number, original_title)
    
    await update.message.reply_text(
        f"✅ Гілка успішно прив'язана до тайтлу:\n*{original_title}* (Номер: *{title_number}*).",
        parse_mode="Markdown"
    )
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
            ASK_TITLE_IDENTIFIER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_title_identifier)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )