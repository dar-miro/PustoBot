from telegram import Update
from telegram.ext import ContextTypes
from collections import defaultdict

ROLES = ["клін", "переклад", "тайп", "редакт"]

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    message = update.message
    if not message or not message.text:
        return

    args = message.text.strip().split(maxsplit=1)
    if len(args) != 2:
        await update.message.reply_text("⚠️ Використання: /status Назва_Тайтлу")
        return

    title = args[1].strip().lower()
    all_rows = sheet.get_all_values()[1:]  # Пропускаємо заголовок

    # Зберігаємо дані у вигляді: {розділ: {роль: нік}}
    chapters = defaultdict(dict)
    for row in all_rows:
        if len(row) < 6:
            continue
        if row[2].strip().lower() != title:
            continue

        chapter = row[3].strip()
        role = row[4].strip().lower()
        user = row[5].strip()
        if role in ROLES:
            chapters[chapter][role] = user

    if not chapters:
        await update.message.reply_text("⛔ Нічого не знайдено по цьому тайтлу.")
        return

    # Формування відповіді
    header = "       | " + " || ".join([f"{r.capitalize():<9}" for r in ROLES]) + " || Статус\n"
    lines = [args[1], header]

    for ch in sorted(chapters.keys(), key=lambda x: float(x.replace(",", "."))):
        row = f"{ch:<7}| "
        role_statuses = []
        all_done = True
        for role in ROLES:
            user = chapters[ch].get(role)
            if user:
                role_statuses.append(f"{user} ✅")
            else:
                role_statuses.append("❌")
                all_done = False
        row += " || ".join([f"{r:<9}" for r in role_statuses])
        row += f" || {'опубліковано' if all_done else ''}"
        lines.append(row)

    await update.message.reply_text("\n".join(lines))
