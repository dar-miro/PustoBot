import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from PustoBot import start_command, handle_message, add_command
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Налаштування Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open("DataBase").sheet1  # замініть на назву таблиці

# Обгортки, щоб передати sheet в обробники
async def message_handler_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await handle_message(update, context, sheet)

async def add_command_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await add_command(update, context, sheet)

if __name__ == "__main__":
    TOKEN = os.getenv("TOKEN")  # токен беремо зі змінних оточення

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("add", add_command_wrapper))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler_wrapper))

    # --- Налаштування webhook ---

    # Шлях webhook (можеш змінити на свій)
    WEBHOOK_PATH = "/webhook"
    WEBHOOK_URL = os.getenv("WEBHOOK_URL") or "https://pustobot.onrender.com" + WEBHOOK_PATH
    PORT = int(os.environ.get("PORT", "8443"))  # Render дає порт у змінній оточення PORT

    print(f"Starting webhook on port {PORT} with URL {WEBHOOK_URL}")

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=WEBHOOK_PATH,
        webhook_url=WEBHOOK_URL
    )
