import os
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from PustoBot import start_command, handle_message, add_command
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from status import status_command

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

# Обробка запитів від Telegram
async def handle_ping(request):
    return web.Response(text="I'm alive!")

async def handle_webhook(request):
    app = request.app['bot_app']
    update = await request.json()
    print("📨 Отримано update від Telegram:", update)
    telegram_update = Update.de_json(update, app.bot)
    await app.update_queue.put(telegram_update)
    return web.Response(text='OK')

# Основна асинхронна функція
async def main():
    TOKEN = os.getenv("TOKEN")

    # Створення Telegram application
    bot_app = ApplicationBuilder().token(TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("add", add_command_wrapper))
    bot_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler_wrapper))
    bot_app.add_handler(CommandHandler("status", lambda u, c: status_command(u, c, sheet)))

    await bot_app.initialize()
    await bot_app.start()

    # Вебсервер aiohttp
    aio_app = web.Application()
    aio_app['bot_app'] = bot_app
    aio_app.add_routes([
        web.get('/', handle_ping),
        web.post('/webhook', handle_webhook),
    ])

    PORT = int(os.environ.get("PORT", "8443"))
    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()

    print(f"✅ Server started on port {PORT}")
    while True:
        await asyncio.sleep(3600)  # тримай сервер живим


# Запуск
if __name__ == "__main__":
    asyncio.run(main())
