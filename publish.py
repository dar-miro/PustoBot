import logging
from telegram import Update
from telegram.ext import ContextTypes
from PustoBot.sheets import get_title_sheet, normalize_title, titles_sheet
from thread import get_thread_title

logger = logging.getLogger(__name__)

async def publish_command(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    """Оновлює статус розділу на 'Опубліковано'."""
    message = update.message
    if not message or not message.text:
        return
    
    text = message.text[len("/publish "):].strip()

    # Отримання назви гілки
    thread_title = get_thread_title(message.message_thread_id)
    
    parts = text.split()
    
    title = None
    chapter = None

    # Логіка парсингу: спочатку перевіряємо формат для гілки
    if thread_title and len(parts) >= 1:
        chapter = parts[0]
        title = thread_title
    # Якщо це не формат для гілки, спробуємо повний формат
    elif len(parts) >= 2:
        title = " ".join(parts[:-1])
        chapter = parts[-1]

    if not title or not chapter:
        await update.message.reply_text(
            "⚠️ Невірний формат. Використайте `/publish Назва Тайтлу Номер` або `/publish Номер` у гілці тайтлу."
        )
        return
    
    if titles_sheet is None:
        logger.error("titles_sheet не ініціалізовано. Неможливо оновити таблицю.")
        await update.message.reply_text("⚠️ Внутрішня помилка: аркуш 'Тайтли' не ініціалізовано.")
        return

    try:
        data = titles_sheet.get_all_values()
        
        # Знаходимо блок для тайтлу
        title_row_idx, header_row_idx = -1, -1
        for i, row in enumerate(data):
            if row and normalize_title(row[0]) == normalize_title(title):
                title_row_idx = i
                header_row_idx = i + 1
                break
        
        if title_row_idx == -1 or header_row_idx >= len(data):
            await update.message.reply_text(f"⚠️ Тайтл '{title}' не знайдено.")
            return

        headers = data[header_row_idx]
        
        # Перевіряємо наявність необхідних колонок
        try:
            chapter_col_idx = headers.index("Розділ")
            published_col_idx = headers.index("Статус")
        except ValueError:
            await update.message.reply_text(
                "⚠️ Помилка: не знайдено необхідну колонку 'Розділ' або 'Статус' в таблиці 'Тайтли'."
            )
            return

        updated = False
        
        # Шукаємо рядок з розділом
        for i, row in enumerate(data[header_row_idx + 1:]):
            if len(row) > chapter_col_idx and str(row[chapter_col_idx]).strip() == str(chapter).strip():
                row_index_to_update = header_row_idx + 2 + i
                titles_sheet.update_cell(row_index_to_update, published_col_idx + 1, "✅")
                await update.message.reply_text(f"✅ Успішно оновлено: *{data[title_row_idx][0]}* (розділ *{chapter}*) тепер позначено як 'Опубліковано'.", parse_mode="Markdown")
                updated = True
                break
        
        if not updated:
             await update.message.reply_text(f"⚠️ Не знайдено розділ '{chapter}' для тайтлу '{title}'.")

    except Exception as e:
        logger.error(f"Помилка при оновленні статусу публікації: {e}")
        await update.message.reply_text("⚠️ Виникла внутрішня помилка при оновленні статусу публікації.")