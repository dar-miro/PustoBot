# status.py
import logging
from telegram import Update
from telegram.ext import ContextTypes
from PustoBot.sheets import get_title_status_data
from thread import get_thread_number 

logger = logging.getLogger(__name__)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Надає статус усіх розділів для вказаного тайтлу (завдання 4)."""
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

    response_lines = [f"📊 *Статус тайтлу '{original_title}':*\\n"]
    
    for item in status_report:
        chapter_number = item['chapter']
        
        # Ролі
        role_statuses = []
        role_order = ["клін", "переклад", "тайп", "редакт"]
        for role_key in role_order:
            role_info = item['roles'].get(role_key)
            if role_info is not None:
                status_char = "✅" if role_info['status'] else "❌"
                person = role_info['person']
                person_text = f" ({person})" if person else ""
                
                # Формат: роль: ✅ (Нік)
                role_statuses.append(f"{role_key.capitalize()}: {status_char}{person_text}")
        
        roles_text = " | ".join(role_statuses)
        
        # Загальний статус та дедлайн
        published_status = "✅ Опубліковано" if item['published'] else "❌ В роботі"
        deadline = item.get('deadline', '—') 
        
        response_lines.append(f"\\n*Розділ {chapter_number}:*")
        response_lines.append(f"  {roles_text}")
        response_lines.append(f"  Дедлайн: {deadline}")
        response_lines.append(f"  Статус: {published_status}")

    await update.message.reply_text("\n".join(response_lines), parse_mode="Markdown")