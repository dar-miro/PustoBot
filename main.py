import os
import asyncio
import logging
from aiohttp import web
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Імпорти з ваших модулів
from PustoBot.handlers import start_command, handle_message, add_command
from thread import get_thread_handler
from register import get_register_handler
from publish import publish_command
from status import status_command
from PustoBot.sheets import main_spreadsheet, log_sheet, titles_sheet # ВИПРАВЛЕНО: імпортуємо specific sheets

# Налаштування логування
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Обгортки для передачі об'єкта `main_spreadsheet` з sheets.py
async def message_handler_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # handle_message працює з log_sheet
    await handle_message(update, context, log_sheet, titles_sheet)

async def add_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ВИПРАВЛЕНО: передаємо titles_sheet для оновлення таблиці
    await add_command(update, context, titles_sheet)

async def status_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ВИПРАВЛЕНО: передаємо titles_sheet для отримання статусу
    await status_command(update, context, titles_sheet)

async def publish_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ВИПРАВЛЕНО: передаємо titles_sheet для публікації
    await publish_command(update, context, titles_sheet)

# Функції для вебхуків (як у вашому прикладі)
async def handle_ping(request):
    return web.Response(text="I'm alive!")

async def handle_webhook(request):
    app = request.app['bot_app']
    update = await request.json()
    telegram_update = Update.de_json(update, app.bot)
    await app.update_queue.put(telegram_update)
    return web.Response(text='OK')

async def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set.")
        return

    # Ініціалізація ApplicationBuilder
    bot_app = ApplicationBuilder().token(TOKEN).build()

    # Додаємо обробники команд
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("add", add_command_wrapper))
    bot_app.add_handler(CommandHandler("status", status_command_wrapper))
    bot_app.add_handler(CommandHandler("publish", publish_command_wrapper))
    
    # Реєстрація ConversationHandler для /thread
    bot_app.add_handler(get_thread_handler())

    # Реєстрація ConversationHandler для /register
    bot_app.add_handler(get_register_handler(main_spreadsheet))

    # Обробник для звичайних повідомлень
    bot_app.add_handler(
        MessageHandler(
            (filters.TEXT & ~filters.COMMAND & filters.REPLY) |
            (filters.TEXT & ~filters.COMMAND & filters.Entity("mention")),
            message_handler_wrapper
        )
    )

    # Ініціалізація та запуск бота (для використання з вебхуками)
    await bot_app.initialize()
    await bot_app.start()

    aio_app = web.Application()
    aio_app['bot_app'] = bot_app
    aio_app.add_routes([
        web.get('/', handle_ping),
        web.post('/webhook', handle_webhook),
    ])

    # Запуск aiohttp сервера
    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()

    # Keep the bot running indefinitely
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())