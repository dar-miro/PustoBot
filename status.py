from telegram import Update
from telegram.ext import ContextTypes
from PustoBot.sheets import get_titles_sheet
import re

def extract_title_blocks(sheet):
    data = sheet.get_all_values()
    blocks = []
    current_title = None
    start_row = None
    for i, row in enumerate(data):
        if any(row):
            if current_title is None and row[0]:
                current_title = row[0]
                start_row = i
        else:
            if current_title is not None:
                blocks.append((current_title, start_row, i))
                current_title = None
    if current_title:
        blocks.append((current_title, start_row, len(data)))
    return blocks

def extract_status_text(sheet, title_block):
    title, start_row, end_row = title_block
    rows = sheet.get_all_values()[start_row+2:end_row]  # Розділи починаються з 3 рядка
    if not rows:
        return f"ℹ️ Немає розділів для {title}"
    
    text = f"📚 *{title}*\n"
    for i, row in enumerate(rows):
        chapter = row[0]
        if not chapter:
            continue
        line = f"— *{chapter}*: "
        roles = ["Клін", "Переклад", "Тайп", "Редакт"]
        col_offset = {"Клін": 1, "Переклад": 4, "Тайп": 7, "Редакт": 10}
        for role in roles:
            name = row[col_offset[role]]
            done = row[col_offset[role] + 2]
            mark = "✅" if done == "✅" else "❌"
            if name:
                line += f"{role}: `{name}` {mark}, "
        text += line.rstrip(", ") + "\n"
    return text

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    text = update.message.text
    match = re.match(r"/status\s+(.+)", text)
    if not match:
        await update.message.reply_text("⚠️ Напиши команду у форматі:\n/status НазваТайтлу")
        return

    title = match.group(1).strip()
    titles_sheet = get_titles_sheet()

    blocks = extract_title_blocks(titles_sheet)
    for block in blocks:
        if block[0].strip().lower() == title.lower():
            msg = extract_status_text(titles_sheet, block)
            await update.message.reply_text(msg, parse_mode="Markdown")
            return

    await update.message.reply_text("⚠️ Тайтл не знайдено.")
