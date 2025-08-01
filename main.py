import os
import asyncio
import logging
from aiohttp import web
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# Імпорти з ваших модулів, враховуючи структуру
from PustoBot.core import parse_message # Якщо використовується parse_message в main
from PustoBot.handlers import start_command, handle_message, add_command
from PustoBot.sheets import main_spreadsheet, initialize_header_map
from publish import publish_command
from status import status_command
from thread import get_thread_handler
from register import get_register_handler

# Налаштування логування
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Обгортки для команд (тепер вони простіші)
async def message_handler_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_message(update, context)

async def add_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await add_command(update, context)

async def status_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await status_command(update, context)

async def publish_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await publish_command(update, context)

# Функції для вебхуків
async def handle_ping(request):
    return web.Response(text='pong')

async def handle_webhook(request):
    bot_app = request.app['bot_app']
    update_data = await request.json()
    update = Update.de_json(update_data, bot_app.bot)
    await bot_app.process_update(update)
    return web.Response(status=200)

async def main():
    """Start the bot."""
    bot_token = os.environ.get("BOT_TOKEN")
    if not bot_token:
        logger.error("BOT_TOKEN not found in environment variables.")
        return
    
    bot_app = (
        ApplicationBuilder()
        .token(bot_token)
        .updater(None)  # No Updater when using webhook
        .build()
    )

    # Ініціалізація карти колонок
    try:
        # Ця функція знаходиться у файлі PustoBot/sheets.py
        initialize_header_map()
        logger.info("Карту колонок успішно ініціалізовано.")
    except Exception as e:
        logger.error(f"Помилка при ініціалізації карти колонок: {e}")
        return

    # Реєстрація хендлерів
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("add", add_command_wrapper))
    bot_app.add_handler(CommandHandler("status", status_command_wrapper))
    bot_app.add_handler(CommandHandler("publish", publish_command_wrapper))
    
    bot_app.add_handler(get_thread_handler())
    # Передача main_spreadsheet як аргументу, якщо це потрібно для get_register_handler
    bot_app.add_handler(get_register_handler(main_spreadsheet)) 

    # Обробник для звичайних повідомлень
    bot_app.add_handler(
        MessageHandler(
            (filters.TEXT & ~filters.COMMAND & filters.REPLY) |
            (filters.TEXT & ~filters.COMMAND & filters.Entity("mention")),
            message_handler_wrapper
        )
    )

    # Ініціалізація та запуск бота для вебхуків
    await bot_app.initialize()
    await bot_app.start()
    
    # Потрібно переконатися, що у `bot_app` є черга оновлень
    if not hasattr(bot_app, 'update_queue'):
        logger.error("bot_app has no update_queue attribute!")
        return
        
    aio_app = web.Application()
    aio_app['bot_app'] = bot_app
    aio_app.add_routes([
        web.get('/', handle_ping),
        web.post('/webhook', handle_webhook),
    ])

    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()

if __name__ == '__main__':
    asyncio.run(main())