import os
import gspread
from datetime import datetime
from aiohttp import web
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from oauth2client.service_account import ServiceAccountCredentials

# === Google Sheets ===
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open("DataBase").sheet1

# === Завантаження нікнеймів з аркуша "Користувачі" ===
def load_nickname_map(sheet):
    try:
        user_sheet = sheet.spreadsheet.worksheet("Користувачі")
        data = user_sheet.get_all_records()
        return {row["Telegram-нік"]: row["Нік"] for row in data if row.get("Telegram-нік") and row.get("Нік")}
    except:
        return {}

# === Парсинг повідомлення ===
def parse_message(text, thread_title=None, bot_username=None):
    parts = text.strip().split()
    if bot_username and parts and parts[0].lower() == f"@{bot_username.lower()}":
        parts = parts[1:]
    if len(parts) == 2 and thread_title:
        chapter, position = parts
        nickname = None
        title = thread_title
    elif len(parts) == 3 and thread_title:
        chapter, position, nickname = parts
        title = thread_title
    elif len(parts) == 3:
        title, chapter, position = parts
        nickname = None
    elif len(parts) >= 4:
        title, chapter, position = parts[:3]
        nickname = parts[3]
    else:
        return None
    return title, chapter, position, nickname

# === Обробка одного повідомлення ===
async def process_input(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet, text: str, thread_title=None, bot_username=None):
    result = parse_message(text, thread_title=thread_title, bot_username=bot_username)
    if not result:
        await update.message.reply_text("⚠️ Невірний формат. Спробуй ще раз.")
        return

    title, chapter, position, nickname = result
    if not nickname:
        nickname = update.message.from_user.full_name

    # Динамічно оновлюємо нікнейм мапу
    nickname_map = load_nickname_map(sheet)
    nickname = nickname_map.get(nickname, nickname)

    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        update.message.from_user.full_name,
        title,
        chapter,
        position,
        nickname
    ]
    sheet.append_row(row)
    await update.message.reply_text("✅ Дані додано до таблиці.")

# === Команди ===
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Надішли мені:\n"
        "Назва Розділ Позиція Нік (опціонально)\n"
        "або скористайся командою /add у такому ж форматі."
    )

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    message = update.message
    if not message or not message.text:
        return
    text = message.text[len("/add "):].strip()
    thread_title = getattr(message, "message_thread_title", None) or getattr(message, "message_thread_topic", None)
    await process_input(update, context, sheet, text, thread_title=thread_title, bot_username=context.bot.username)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    message = update.message
    if not message or not message.text:
        return
    bot_username = context.bot.username.lower()
    if bot_username in message.text.lower():
        thread_title = getattr(message, "message_thread_title", None) or getattr(message, "message_thread_topic", None)
        await process_input(update, context, sheet, message.text, thread_title=thread_title, bot_username=context.bot.username)

# === Обгортки ===
async def message_handler_wrapper(update, context):
    await handle_message(update, context, sheet)

async def add_command_wrapper(update, context):
    await add_command(update, context, sheet)

# === Webhook ===
async def handle_ping(request):
    return web.Response(text="I'm alive!")

async def handle_webhook(request):
    app = request.app['bot_app']
    update = await request.json()
    telegram_update = Update.de_json(update, app.bot)
    await app.update_queue.put(telegram_update)
    return web.Response(text='OK')
