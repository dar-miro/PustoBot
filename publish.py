import logging
from telegram import Update
from telegram.ext import ContextTypes
from .PustoBot.sheets import set_publish_status
from thread import get_thread_title

logger = logging.getLogger(__name__)

async def publish_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Оновлює статус розділу на 'Опубліковано'."""
    message = update.message
    text = message.text[len("/publish "):].strip()

    thread_title = get_thread_title(message.message_thread_id)
    parts = text.split()
    
    title = None
    chapter = None

    if thread_title and len(parts) >= 1:
        chapter = parts[0]
        title = thread_title
    elif len(parts) >= 2:
        title = " ".join(parts[:-1])
        chapter = parts[-1]

    if not title or not chapter:
        await update.message.reply_text(
            "⚠️ Невірний формат. Використайте `/publish Назва Тайтлу Номер` або `/publish Номер` у гілці тайтлу."
        )
        return
    
    result, data = set_publish_status(title, chapter)

    if result == "success":
        original_title = data
        await update.message.reply_text(f"✅ Успішно оновлено: *{original_title}* (розділ *{chapter}*) тепер позначено як 'Опубліковано'.", parse_mode="Markdown")
    elif result == "not_found":
        await update.message.reply_text(f"⚠️ Тайтл '{title}' не знайдено.")
    elif result == "chapter_not_found":
        await update.message.reply_text(f"⚠️ Не знайдено розділ '{chapter}' для тайтлу '{title}'.")
    else: # result == "error"
        await update.message.reply_text("⚠️ Виникла внутрішня помилка при оновленні статусу публікації.")