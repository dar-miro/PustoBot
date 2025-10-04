import os
import asyncio
import logging
from aiohttp import web
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

# Імпорти з ваших модулів
from PustoBot.handlers import start_command, add_command
from thread import get_thread_handler
from publish import publish_command
from status import status_command
from PustoBot.sheets import connect_to_google_sheets, main_spreadsheet 

# Налаштування логування
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Обгортки для команд
async def add_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await add_command(update, context)

async def status_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await status_command(update, context)

async def publish_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await publish_command(update, context)

async def main() -> None:
    # Отримання токену та URL
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")

    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN не встановлено.")
        return

    bot_app = ApplicationBuilder().token(TOKEN).build()

    # Підключення до Google Sheets
    if not connect_to_google_sheets():
        logger.error("Не вдалося підключитися до Google Sheets. Бот не запускається.")
        return

    # Реєстрація хендлерів
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("add", add_command_wrapper))
    bot_app.add_handler(CommandHandler("status", status_command_wrapper))
    bot_app.add_handler(CommandHandler("publish", publish_command_wrapper))
    
    # Залишаємо тільки /thread
    bot_app.add_handler(get_thread_handler())
    # Видалено get_threadnum_handler() та get_register_handler()
    # Видалено MessageHandler

    # Ініціалізація та запуск бота для вебхуків
    await bot_app.initialize()
    await bot_app.start()
    
    if not hasattr(bot_app, 'update_queue'):
        logger.error("bot_app has no update_queue attribute!")
        return
        
    aio_app = web.Application()
    aio_app['bot_app'] = bot_app
    
    async def webhook_handler(request):
        bot_app = request.app['bot_app']
        update = Update.de_json(await request.json(), bot_app.bot)
        await bot_app.update_queue.put(update)
        return web.Response()

    webhook_path = '/' + TOKEN
    aio_app.add_routes([
        web.get('/health', lambda r: web.Response(text='OK')),
        web.post(webhook_path, webhook_handler),
    ])

    runner = web.AppRunner(aio_app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    logger.info(f"Starting web server on port {port}")
    await site.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Error in main execution: {e}")