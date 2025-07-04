import os
import json
from datetime import datetime
from aiohttp import web
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Завантаження словника ніків
with open("nicknames.json", "r", encoding="utf-8") as f:
    nickname_map = json.load(f)

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open("DataBase").sheet1

# === Парсинг повідомлення ===
def parse_message(text, thread_title=None):
    parts = text.strip().split()

    if len(parts) < 2:
        return None

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

# === Обробка повідомлення ===
async def process_input(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet, text: str, thread_title=None):
    result = parse_message(text, thread_title)
    if not result:
        await update.message.reply_text("⚠️ Невірний формат. Спробуй знову.")
        return

    title, chapter, position, nickname = result
    if not nickname:
        nickname = update.message.from_user.full_name
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

# === Команда /start ===
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Надішли мені:\n"
        "Назва Розділ Позиція Нік (опціонально)\n"
        "або скористайся командою /add у такому ж форматі."
    )

# === Обробка тексту з тегом бота ===
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    message = update.message
    if not message or not message.text:
        return

    bot_username = context.bot.username.lower()
    if bot_username in message.text.lower():
        # Отримуємо назву теми (гілки) якщо є
        thread_title = message.message_thread_title if hasattr(message, 'message_thread_title') else None
        await process_input(update, context, sheet, message.text, thread_title=thread_title)


# === Команда /add ===
async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    message = update.message
    if not message or not message.text:
        return
    text = message.text[len("/add "):].strip()
    thread_title = message.message_thread_topic if message.is_topic_message else None
    await process_input(update, context, sheet, text, thread_title)

# === Обгортки для передачі sheet ===
async def message_handler_wrapper(update, context):
    await handle_message(update, context, sheet)

async def add_command_wrapper(update, context):
    await add_command(update, context, sheet)

async def handle_ping(request):
    return web.Response(text="I'm alive!")

async def handle_webhook(request):
    app = request.app['bot_app']
    update = await request.json()
    telegram_update = Update.de_json(update, app.bot)
    await app.update_queue.put(telegram_update)
    return web.Response(text='OK')

# === Запуск бота та aiohttp-сервера ===
if __name__ == "__main__":
    TOKEN = os.getenv("TOKEN")

    bot_app = ApplicationBuilder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("add", add_command_wrapper))
    bot_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler_wrapper))

    aio_app = web.Application()
    aio_app['bot_app'] = bot_app
    aio_app.add_routes([
        web.get("/", handle_ping),
        web.post("/webhook", handle_webhook)
    ])

    PORT = int(os.environ.get("PORT", "8443"))
    print(f"🌐 Server running on port {PORT}...")

    # Запуск
    bot_app.initialize()
    bot_app.start()
    web.run_app(aio_app, host="0.0.0.0", port=PORT)
