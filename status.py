from telegram import Update
from telegram.ext import ContextTypes
from collections import defaultdict
import re

ROLES = ["Клін", "Переклад", "Тайп", "Редакт"]

# === Команда /status ===
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    message = update.message
    if not message or not message.text:
        return

    args = message.text.strip().split(maxsplit=1)
    if len(args) < 2:
        await update.message.reply_text("⚠️ Використання: /status Назва_Тайтлу або /status Назва_Тайтлу 30-34")
        return

    parts = args[1].strip().split()
    title = parts[0].strip().lower()
    range_filter = None

    if len(parts) > 1:
        range_match = re.match(r"(\d+[.,]?\d*)-(\d+[.,]?\d*)", parts[1])
        if range_match:
            start = float(range_match.group(1).replace(",", "."))
            end = float(range_match.group(2).replace(",", "."))
            range_filter = (start, end)

    data = sheet.get_all_values()[1:]  # Пропускаємо заголовок

    # Відфільтрувати дані за тайтлом
    filtered = [row for row in data if len(row) >= 6 and row[2].strip().lower() == title]
    if not filtered:
        await update.message.reply_text("⛔ Нічого не знайдено по цьому тайтлу.")
        return

    # Групувати по розділах
    chapters = defaultdict(lambda: defaultdict(str))
    for row in filtered:
        chapter = row[3].strip()
        role = row[4].strip().capitalize()
        user = row[5].strip()
        if role.lower() in [r.lower() for r in ROLES]:
            chapters[chapter][role] = user

    # Формування відповіді
    lines = [f"<b>{parts[0]}</b>"]
    for chapter in sorted(chapters.keys(), key=lambda x: float(x.replace(',', '.'))):
        chapter_val = float(chapter.replace(',', '.'))
        if range_filter:
            if not (range_filter[0] <= chapter_val <= range_filter[1]):
                continue
        roles_data = chapters[chapter]
        all_done = all(role in roles_data for role in ROLES)
        lines.append(f"\n<b>{chapter} - {'опубліковано' if all_done else 'в роботі'}</b>")
        for role in ROLES:
            user = roles_data.get(role)
            if user:
                lines.append(f"{role.lower()} {user} ✅")
            else:
                lines.append(f"{role.lower()} ❌")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
