import logging
from telegram import Update
from telegram.ext import ContextTypes
from PustoBot.sheets import get_title_status_data

logger = logging.getLogger(__name__)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Надає статус усіх розділів для вказаного тайтлу."""
    message = update.message
    text = message.text[len("/status "):].strip()
    title = text
    
    if not title:
        await update.message.reply_text("⚠️ Будь ласка, вкажіть назву тайтлу. Наприклад: `/status Відьмоварта`")
        return
    
    original_title, status_report = get_title_status_data(title)

    if original_title is None:
        await update.message.reply_text(f"⚠️ Тайтл '{title}' не знайдено або для нього немає даних.")
        return

    if not status_report:
        await update.message.reply_text(f"📊 Для тайтлу '{original_title}' ще немає жодного розділу.")
        return

    response_lines = [f"📊 *Статус тайтлу '{original_title}':*\n"]
    
    for item in status_report:
        chapter_number = item['chapter']
        status_text = "✅ Опубліковано" if item['published'] else "❌ В роботі"
        response_lines.append(f"Розділ *{chapter_number}* — {status_text}")

    await update.message.reply_text("\n".join(response_lines), parse_mode="Markdown")