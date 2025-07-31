import logging
from telegram import Update
from telegram.ext import ContextTypes
from PustoBot.sheets import get_title_data, normalize_title, titles_sheet

logger = logging.getLogger(__name__)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    """Надає статус усіх розділів для вказаного тайтлу."""
    message = update.message
    if not message or not message.text:
        return
    
    text = message.text[len("/status "):].strip()
    title = text
    
    if not title:
        await update.message.reply_text("⚠️ Будь ласка, вкажіть назву тайтлу. Наприклад: `/status Відьмоварта`")
        return
    
    if titles_sheet is None:
        logger.error("titles_sheet не ініціалізовано. Неможливо отримати статус.")
        await update.message.reply_text("⚠️ Внутрішня помилка: аркуш 'Тайтли' не ініціалізовано.")
        return

    try:
        title_data, headers = get_title_data(title, titles_sheet)
        if title_data is None:
            await update.message.reply_text(f"⚠️ Тайтл '{title}' не знайдено.")
            return

        response = f"📊 *Статус тайтлу '{title}':*\n\n"
        
        # Знаходимо індекси колонок для кожної ролі
        role_map = {
            "Клін": [], "Переклад": [],
            "Тайп": [], "Редакт": []
        }
        
        main_headers = titles_sheet.row_values(titles_sheet.find(title).row)
        sub_headers = titles_sheet.row_values(titles_sheet.find(title).row + 1)
        
        for i, header in enumerate(main_headers):
            if header in role_map:
                status_col_idx = sub_headers.index("Статус", i)
                role_map[header].append(status_col_idx)

        for row in title_data:
            if not row or not row[0].strip():
                continue

            chapter_number = row[0].strip()
            chapter_status = row[-1] if len(row) > 0 else '❌'
            
            status_text = "✅ Опубліковано" if chapter_status == "✅" else "❌ Не опубліковано"
            
            response += f"*{chapter_number}* — {status_text}\n"

        await update.message.reply_text(response, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Помилка при отриманні статусу: {e}")
        await update.message.reply_text("⚠️ Виникла внутрішня помилка при отриманні статусу.")