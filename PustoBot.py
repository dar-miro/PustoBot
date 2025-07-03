from telegram import Update
from telegram.ext import ContextTypes
import re
from datetime import datetime

def parse_message(text):
    pattern = r"(\S+)\s+(\S+)\s+(\S+)\s+\((клін|тайп|переклад|редакт)\)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        return match.groups()
    return None

async def process_input(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet, text: str):
    result = parse_message(text)
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
