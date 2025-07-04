from telegram import Update
from telegram.ext import ContextTypes
from collections import defaultdict

ROLES = ["Клін", "Переклад", "Тайп", "Редакт"]

# === Команда /status ===
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    message = update.message
    if not message or not message.text:
        return

    args = message.text.strip().split(maxsplit=1)
    if len(args) != 2:
        await update.message.reply_text("⚠️ Використання: /status Назва_Тайтлу")
        return

    title = args[1].strip().lower()
    data = sheet.get_all_records()

    # Відфільтрувати дані за тайтлом
    filtered = [row for row in data if row['Тайтл'].strip().lower() == title]
    if not filtered:
        await update.message.reply_text("⛔ Нічого не знайдено по цьому тайтлу.")
        return

    # Групувати по розділах
    chapters = defaultdict(lambda: defaultdict(str))
    for row in filtered:
        chapter = str(row['Розділ']).strip()
        role = row['Роль'].strip()
        user = row['Користувач'].strip()
        status = row['Статус'].strip()
        if role in ROLES:
            display = f"{user} ✅" if status == '✅' else f"{user} ❌"
            chapters[chapter][role] = display

    # Формування тексту
    header = "     | " + " || ".join([f"{r:<9}" for r in ROLES]) + " || Статус\n"
    lines = [f"{args[1]}\n", header]

    for chapter in sorted(chapters.keys(), key=lambda x: float(x.replace(',', '.'))):
        row = f"{chapter:<5}| "
        role_statuses = []
        all_done = True
        for role in ROLES:
            value = chapters[chapter].get(role, "❌")
            if value == "❌" or '❌' in value:
                all_done = False
            role_statuses.append(f"{value:<9}")
        row += " || ".join(role_statuses)
        row += f" || {'опубліковано' if all_done else ''}"
        lines.append(row)

    await update.message.reply_text("\n".join(lines))
