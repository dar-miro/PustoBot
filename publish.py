from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime
from PustoBot.sheets import load_nickname_map  # Імпортуємо з PustoBot
import gspread

ROLES = ["Клін", "Переклад", "Тайп", "Редакт"]

async def publish_command(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    message = update.message
    if not message or not message.text:
        return

    args = message.text.strip().split()
    if len(args) < 3:
        await update.message.reply_text("⚠️ Використання: /publish Назва_Тайтлу Розділ")
        return

    chapter = args[-1].strip()
    title = ' '.join(args[1:-1]).strip().lower()

    # Отримуємо нік із таблиці "Користувачі"
    user_fullname = update.message.from_user.full_name
    nickname_map = load_nickname_map(sheet)
    user_nickname = nickname_map.get(user_fullname, user_fullname)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    rows = sheet.get_all_values()
    headers = rows[0]
    data = rows[1:]

    try:
        title_idx = headers.index("Тайтл")
        chapter_idx = headers.index("№ розділу")
        role_idx = headers.index("Позиція")
        nick_idx = headers.index("Користувач")
        status_idx = headers.index("Статус") if "Статус" in headers else -1
        date_idx = headers.index("Дата") if "Дата" in headers else -1
        tg_idx = headers.index("Нік") if "Нік" in headers else -1
    except ValueError as e:
        await update.message.reply_text(f"⚠️ Помилка: не знайдено колонку — {e}")
        return

    updated_rows = 0

    # Оновлюємо статус для наявних рядків
    for i, row in enumerate(data):
        if len(row) < max(title_idx, chapter_idx, role_idx, nick_idx) + 1:
            continue
        if row[title_idx].strip().lower() == title and row[chapter_idx].strip() == chapter:
            if status_idx >= 0:
                sheet.update_cell(i + 2, status_idx + 1, "✅")
                updated_rows += 1

    # Додаємо відсутні ролі
    existing_roles = [row[role_idx].strip().capitalize() for row in data
                      if row[title_idx].strip().lower() == title and row[chapter_idx].strip() == chapter]

    for role in ROLES:
        if role not in existing_roles:
            new_row = ["" for _ in headers]
            if date_idx >= 0:
                new_row[date_idx] = now
            if tg_idx >= 0:
                new_row[tg_idx] = user_nickname
            if nick_idx >= 0:
                new_row[nick_idx] = user_nickname
            new_row[title_idx] = title
            new_row[chapter_idx] = chapter
            new_row[role_idx] = role
            if status_idx >= 0:
                new_row[status_idx] = "✅"
            sheet.append_row(new_row)
            updated_rows += 1

    await update.message.reply_text(
        f"✅ Розділ {chapter} для '{title}' позначено як опублікований ({updated_rows} оновлень)."
    )
