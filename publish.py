from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime
import gspread

ROLES = ["Клін", "Переклад", "Тайп", "Редакт"]

async def publish_command(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    message = update.message
    if not message or not message.text:
        return

    args = message.text.strip().split(maxsplit=2)
    if len(args) != 3:
        await update.message.reply_text("⚠️ Використання: /publish Назва_Тайтлу Розділ")
        return

    title = args[1].strip().lower()
    chapter = args[2].strip()
    user_fullname = update.message.from_user.full_name
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    rows = sheet.get_all_values()
    headers = rows[0]
    data = rows[1:]

    title_idx = headers.index("Тайтл")
    chapter_idx = headers.index("Розділ")
    role_idx = headers.index("Роль")
    nick_idx = headers.index("Користувач")
    status_idx = headers.index("Статус") if "Статус" in headers else -1
    date_idx = headers.index("Дата") if "Дата" in headers else -1
    tg_idx = headers.index("Telegram-нік") if "Telegram-нік" in headers else -1

    updated_rows = 0

    for i, row in enumerate(data):
        if len(row) < 6:
            continue
        if row[title_idx].strip().lower() == title and row[chapter_idx].strip() == chapter:
            if status_idx >= 0:
                sheet.update_cell(i + 2, status_idx + 1, "✅")
                updated_rows += 1

    # Додаємо записи для відсутніх ролей
    existing_roles = [row[role_idx].strip().capitalize() for row in data
                      if row[title_idx].strip().lower() == title and row[chapter_idx].strip() == chapter]

    for role in ROLES:
        if role not in existing_roles:
            new_row = ["" for _ in headers]
            if date_idx >= 0:
                new_row[date_idx] = now
            if tg_idx >= 0:
                new_row[tg_idx] = user_fullname
            new_row[title_idx] = title
            new_row[chapter_idx] = chapter
            new_row[role_idx] = role
            new_row[nick_idx] = user_fullname
            if status_idx >= 0:
                new_row[status_idx] = "✅"
            sheet.append_row(new_row)
            updated_rows += 1

    await update.message.reply_text(f"✅ Розділ {chapter} для '{title}' позначено як опублікований ({updated_rows} оновлень).")
