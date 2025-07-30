import os
import asyncio
from aiohttp import web
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import logging

# Імпорти з ваших файлів
from PustoBot.handlers import start_command, handle_message, add_command
from thread import get_thread_handler
from register import get_register_handler
from publish import publish_command
from status import status_command
from PustoBot.sheets import get_title_sheet, main_spreadsheet # Імпортуємо main_spreadsheet

# Налаштування логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Спроба отримати sheet на початку. Якщо не вдасться, sheet буде None.
sheet = get_title_sheet()
if sheet is None:
    logger.error("Failed to initialize Google Sheets connection. Bot may not function correctly.")
    # Тут можна додати логіку для виходу або повідомити користувача, що бот не працює.

async def message_handler_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Перевіряємо, чи sheet є None, і якщо так, відповідаємо про помилку
    if sheet is None:
        await update.message.reply_text("⚠️ На жаль, бот зараз не може підключитися до таблиць. Будь ласка, спробуйте пізніше або зверніться до адміністратора.")
        return
    await handle_message(update, context, sheet)

async def add_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if sheet is None:
        await update.message.reply_text("⚠️ На жаль, бот зараз не може підключитися до таблиць. Будь ласка, спробуйте пізніше або зверніться до адміністратора.")
        return
    await add_command(update, context, sheet)

async def handle_ping(request):
    return web.Response(text="I'm alive!")

async def handle_webhook(request):
    app = request.app['bot_app']
    try:
        update = await request.json()
        telegram_update = Update.de_json(update, app.bot)
        await app.update_queue.put(telegram_update)
    except Exception as e:
        logger.error(f"Error processing webhook update: {e}")
        return web.Response(text='Error', status=500)
    return web.Response(text='OK')

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log the error and send a message to the user."""
    logger.error(f"Update {update} caused error {context.error}")
    # Відправлення повідомлення користувачу про помилку (можна налаштувати більш детально)
    if update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ Виникла неочікувана помилка. Будь ласка, спробуйте ще раз або зверніться до адміністратора."
        )

async def main():
    TOKEN = os.getenv("TOKEN")
    if not TOKEN:
        logger.critical("TOKEN environment variable not set. Exiting.")
        return

    bot_app = ApplicationBuilder().token(TOKEN).build()

    # Додаємо глобальний обробник помилок
    bot_app.add_error_handler(error_handler)

    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("add", add_command_wrapper))
    bot_app.add_handler(CommandHandler("status", lambda u, c: status_command(u, c, sheet)))
    bot_app.add_handler(CommandHandler("publish", lambda u, c: publish_command(u, c, sheet)))
    bot_app.add_handler(get_thread_handler())
    
    # Передаємо main_spreadsheet в get_register_handler
    # Це потрібно, бо get_user_sheet у register.py очікує main_spreadsheet.
    bot_app.add_handler(get_register_handler(main_spreadsheet)) 
    
    bot_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler_wrapper))

    await bot_app.initialize()
    await bot_app.start()

    # Налаштування Aiohttp веб-сервера
    aio_app = web.Application()
    aio_app['bot_app'] = bot_app # Зберігаємо екземпляр бота в aiohttp app
    aio_app.add_routes([
        web.get('/', handle_ping),
        web.post(f'/{TOKEN}', handle_webhook), # Змінено на f'/{TOKEN}' для вебхука
    ])

    PORT = int(os.getenv("PORT", 8080))
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")

    if not WEBHOOK_URL:
        logger.critical("WEBHOOK_URL environment variable not set. Webhook will not be set.")
        # Можливо, варто викликати app.run_polling() тут для локального тестування
        raise ValueError("WEBHOOK_URL environment variable is required for webhook mode.")

    # Встановлення вебхука
    webhook_path = f'/{TOKEN}'
    full_webhook_url = f"{WEBHOOK_URL}{webhook_path}"
    
    try:
        await bot_app.bot.set_webhook(url=full_webhook_url)
        logger.info(f"Webhook set to: {full_webhook_url}")
    except Exception as e:
        logger.critical(f"Failed to set webhook: {e}")
        # Якщо вебхук не встановлено, бот не отримуватиме оновлення
        raise

    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    logger.info(f"Starting web server on port {PORT}")
    await site.start()

    # Keep the aiohttp server running indefinitely
    await asyncio.Event().wait()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.critical(f"Unhandled exception in main: {e}", exc_info=True)