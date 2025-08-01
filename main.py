import logging

from telegram.ext import Updater, CommandHandler

from PustoBot.sheets import initialize_header_map, main_spreadsheet
from PustoBot.core import setup_bot_with_commands, create_updater
from PustoBot.handlers import (
    status_handler,
    register_handler,
    publish_handler,
    thread_handler,
)

# Налаштування логування
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Start the bot."""
    # Create the Updater and pass it your bot's token.
    updater = create_updater()

    # Get the dispatcher to register handlers
    dispatcher = updater.dispatcher

    # Initialize the header map for the spreadsheets
    try:
        initialize_header_map()
        logger.info("Карту колонок успішно ініціалізовано.")
    except Exception as e:
        logger.error(f"Помилка при ініціалізації карти колонок: {e}")
        return  # Stop execution if headers can't be initialized

    # on different commands - answer in Telegram
    dispatcher.add_handler(CommandHandler("status", status_handler))
    dispatcher.add_handler(CommandHandler("register", register_handler))
    dispatcher.add_handler(CommandHandler("publish", publish_handler))
    dispatcher.add_handler(CommandHandler("thread", thread_handler))

    # Start the Bot
    updater.start_polling()

    # Run the bot until you press Ctrl-C or the process receives SIGINT,
    # SIGTERM or SIGABRT. This should be used most of the time, since
    # start_polling() is non-blocking and will stop the bot gracefully.
    updater.idle()


if __name__ == "__main__":
    main()