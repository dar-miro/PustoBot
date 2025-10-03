import logging
import re
from telegram import Update
from telegram.ext import ContextTypes
from PustoBot.sheets import set_publish_status
from thread import get_thread_number # Оновлений імпорт

logger = logging.getLogger(__name__)

async def publish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Оновлює статус розділу на 'Опубліковано'."""
    message = update.message
    text = message.text[len("/publish "):].strip()
    
    bot_username = context.bot.username
    if text.lower().startswith(f"@{bot_username.lower()}"):
        text = text[len(f"@{bot_username.lower()}"):].strip()

    # Отримуємо Номер Тайтлу з гілки
    thread_title_number = get_thread_number(message.message_thread_id) 
    parts = text.split()
    
    title_identifier = None
    chapter = None

    if thread_title_number and thread_title_number.isdigit() and len(parts) >= 1:
        # У гілці: /publish [НомерРозділу]
        chapter = parts[0]
        title_identifier = thread_title_number
    elif len(parts) >= 2 and re.match(r"^\d+$", parts[-1]):
        # Повний формат: /publish [Назва Тайтлу] [НомерРозділу]
        chapter = parts[-1]
        title_identifier = " ".join(parts[:-1]) # Тут може бути Назва Тайтлу

    if not title_identifier or not re.match(r"^\d+$", chapter):
        await update.message.reply_text(
            "⚠️ Невірний формат. Використайте `/publish Назва Тайтлу Номер` або `/publish Номер` у гілці тайтлу."
        )
        return
    
    # title_identifier може бути Номер або Назва
    result, data = set_publish_status(title_identifier, chapter)

    if result == "success":
        original_title = data
        await update.message.reply_text(f"✅ Успішно опубліковано: *{original_title}* (розділ *{chapter}*).", parse_mode="Markdown")
    elif result == "not_found":
        await update.message.reply_text(f"⚠️ Не вдалося знайти тайтл, його номер або розділ для оновлення.")
    else:
        await update.message.reply_text(f"❌ Помилка при оновленні статусу публікації: {data}")