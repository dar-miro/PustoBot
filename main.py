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
from PustoBot.sheets import main_spreadsheet, initialize_header_map # Додано initialize_header_map

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
    return web.Response(text="I'm alive!")

async def handle_webhook(request):
    app = request.app['bot_app']
    try:
        update_json = await request.json()
        telegram_update = Update.de_json(update_json, app.bot)
        await app.update_queue.put(telegram_update)
        return web.Response(text='OK')
    except Exception as e:
        logger.error(f"Error handling webhook: {e}")
        return web.Response(text='Error', status=500)

async def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN environment variable not set.")
        return

    # >>> ВАЖЛИВО: Ініціалізуємо карту колонок при старті <<<
    initialize_header_map()

    # Ініціалізація ApplicationBuilder
    bot_app = ApplicationBuilder().token(TOKEN).build()

    # Додаємо обробники команд
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("add", add_command_wrapper))
    bot_app.add_handler(CommandHandler("status", status_command_wrapper))
    bot_app.add_handler(CommandHandler("publish", publish_command_wrapper))
    
    bot_app.add_handler(get_thread_handler())
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
    logger.info(f"Bot started and listening on port {os.environ.get('PORT', 8080)}")

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())