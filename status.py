import logging
from telegram import Update
from telegram.ext import ContextTypes
from PustoBot.sheets import get_title_status_data
from thread import get_thread_number # Новий імпорт

logger = logging.getLogger(__name__)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Надає статус усіх розділів для вказаного тайтлу."""
    message = update.message
    text = message.text[len("/status "):].strip()
    title_identifier = text
    
    if not title_identifier:
        # Якщо в гілці і немає тексту, шукаємо Номер Тайтлу з гілки
        title_identifier = get_thread_number(message.message_thread_id)
    
    if not title_identifier:
        await update.message.reply_text("⚠️ Будь ласка, вкажіть назву тайтлу або його номер. Наприклад: `/status Відьмоварта` або `/status 1`.")
        return
    
    # title_identifier може бути Назва або Номер
    original_title, status_report = get_title_status_data(title_identifier)

    if original_title is None:
        await update.message.reply_text(f"⚠️ Тайтл '{title_identifier}' не знайдено або для нього немає даних.")
        return

    if not status_report:
        await update.message.reply_text(f"📊 Для тайтлу '{original_title}' ще немає жодного розділу.")
        return

    response_lines = [f"📊 *Статус тайтлу '{original_title}':*\n"]
    
    for item in status_report:
        chapter_number = item['chapter']
        # Ролі
        role_statuses = []
        role_order = ["клін", "переклад", "тайп", "редакт"]
        for role_key in role_order:
            status = item['roles'].get(role_key)
            if status is not None:
                status_char = "✅" if status else "❌"
                role_statuses.append(f"{role_key}: {status_char}")
        
        roles_text = " | ".join(role_statuses)
        
        # Статус публікації
        status_pub = "✅ Опубліковано" if item['published'] else "❌ В роботі"
        
        response_lines.append(f"*{chapter_number}* — {status_pub}\n  _({roles_text})_")

    await update.message.reply_text("\n".join(response_lines), parse_mode="Markdown")