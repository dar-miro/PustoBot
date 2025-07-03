import os
from aiohttp import web
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from PustoBot import start_command, handle_message, add_command
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open("DataBase").sheet1

# Обгортки для передачі sheet
async def message_handler_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_message(update, context, sheet)

async def add_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await add_command(update, context, sheet)

async def handle_ping(request):
    return web.Response(text="I'm alive!")

async def handle_webhook(request):
    # Отримуємо json і передаємо у telegram бот
    app = request.app['bot_app']
    update = await request.json()
    telegram_update = Update.de_json(update, app.bot)
    await app.update_queue.put(telegram_update)
    return web.Response(text='OK')

if __name__ == "__main__":
    TOKEN = os.getenv("TOKEN")

    # Створюємо Application telegram бота без запуску polling/webhook
    bot_app = ApplicationBuilder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("add", add_command_wrapper))
    bot_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler_wrapper))

    # Створюємо aiohttp вебсервер
    aio_app = web.Application()
    aio_app['bot_app'] = bot_app
    aio_app.add_routes([
        web.get('/', handle_ping),
        web.post('/webhook', handle_webhook),
    ])

    PORT = int(os.environ.get("PORT", "8443"))
    print(f"Starting server on port {PORT}")

    # Запускаємо telegram bot без власного webhook (ми зробили свій через aiohttp)
    bot_app.start()

    # Запускаємо aiohttp сервер
    web.run_app(aio_app, host='0.0.0.0', port=PORT)
