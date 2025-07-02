from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from PustoBot import start_command, handle_message, start_command, handle_message, add_command

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open("DataBase").sheet1  # замініть на назву вашої таблиці

async def message_handler_wrapper(update, context):
    # Обгортка, щоб передати sheet у handle_message
    await handle_message(update, context, sheet)
async def message_handler_wrapper(update, context):
    await handle_message(update, context, sheet)

async def add_command_wrapper(update, context):
    await add_command(update, context, sheet)
if __name__ == "__main__":
    TOKEN = "7392593867:AAHSNWTbZxS4BfEKJa3KG7SuhK2G9R5kKQA"  # Вкажи свій токен бота

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("add", add_command_wrapper))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler_wrapper))

    print("Бот запущений...")
    app.run_polling()
#fix




