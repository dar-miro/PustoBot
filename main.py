import os
import asyncio
import logging
from aiohttp import web
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Імпорти з ваших модулів
from PustoBot.handlers import start_command, handle_message, add_command
from thread import get_thread_handler, set_thread_title_command, get_thread_title_command # Додано set/get_thread_title_command, якщо це окремі команди
from register import get_register_handler
from publish import publish_command
from status import status_command
from PustoBot.sheets import get_title_sheet, main_spreadsheet # Імпортуємо main_spreadsheet напряму

# Налаштування логування
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Отримуємо основний аркуш для передачі в обробники
# sheet = get_title_sheet() # Використовуємо main_spreadsheet напряму через sheets.py

# Обгортки для передачі об'єкта `main_spreadsheet` з sheets.py
async def message_handler_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Pass the main_spreadsheet object from sheets directly
    await handle_message(update, context, main_spreadsheet)

async def add_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Pass the main_spreadsheet object from sheets directly
    await add_command(update, context, main_spreadsheet)

async def status_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await status_command(update, context, main_spreadsheet)

async def publish_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await publish_command(update, context, main_spreadsheet)

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
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") # Використовуємо TELEGRAM_BOT_TOKEN як змінну середовища
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
    # Якщо у вас set_thread_title_command та get_thread_title_command є окремими CommandHandler:
    # bot_app.add_handler(CommandHandler("setthread", set_thread_title_command))
    # bot_app.add_handler(CommandHandler("getthread", get_thread_title_command))

    # Реєстрація ConversationHandler для /register
    bot_app.add_handler(get_register_handler(main_spreadsheet)) # Передаємо main_spreadsheet

    # ВИПРАВЛЕНО: Обробник для звичайних повідомлень тепер спрацьовує тільки якщо:
    # 1. Це відповідь на повідомлення бота (filters.REPLY)
    # 2. Або текст повідомлення містить @username бота (filters.Entity("mention"))
    # (filters.TEXT & ~filters.COMMAND) - це базова умова, що це текст і не команда.
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
    # Ensure all necessary sheets are initialized at startup
    # This might need to be called explicitly if not handled by gspread's init
    # For now, rely on sheets.py global initialization
    asyncio.run(main())