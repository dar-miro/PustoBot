from telegram import Update
from telegram.ext import ContextTypes
import re
from datetime import datetime
import json

with open("nicknames.json", "r", encoding="utf-8") as f:
    nickname_map = json.load(f)
def parse_message(text, thread_title=None):
    parts = text.strip().split()

    if len(parts) < 2:
        return None  # мінімум розділ і позиція

    if len(parts) == 2:
        chapter, position = parts
        nickname = None
        title = thread_title or "БезНазви"
    elif len(parts) == 3:
        chapter, position, nickname = parts
        title = thread_title or "БезНазви"
    else:
        title, chapter, position = parts[:3]
        nickname = parts[3] if len(parts) > 3 else None

    return title, chapter, position, nickname

async def process_input(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet, text: str):
    result = parse_message(text)
    nickname = nickname or update.message.from_user.full_name
    nickname = nickname_map.get(nickname, nickname)
    if result:
        title, chapter, position, work_type = result
        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            update.message.from_user.full_name,
            title,
            chapter,
            position,
            work_type
        ]
        sheet.append_row(row)
        await update.message.reply_text("✅ Дані додано до таблиці.")
    else:
        await update.message.reply_text("⚠️ Невірний формат. Використай: Назва Розділ Позиція (тип)")

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Надішли мені:\n"
        "Назва Розділ Позиція (клін/тайп/переклад/редакт)\n"
        "або скористайся командою /add у такому ж форматі."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    message = update.message
    if not message or not message.text:
        return

    bot_username = context.bot.username.lower()
    if bot_username in message.text.lower():
        await process_input(update, context, sheet, message.text)

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    message = update.message
    if not message or not message.text:
        return
    text = message.text[len("/add "):].strip()
    await process_input(update, context, sheet, text)
