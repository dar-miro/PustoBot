import os
import gspread
from datetime import datetime
from aiohttp import web
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)
from oauth2client.service_account import ServiceAccountCredentials

# === Google Sheets ===
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)
sheet = client.open("DataBase").sheet1

# === Завантаження нікнеймів з аркуша "Користувачі" ===
def load_nickname_map(sheet):
    try:
        user_sheet = sheet.spreadsheet.worksheet("Користувачі")
        data = user_sheet.get_all_records()
        return {row["Telegram-нік"]: row["Нік"] for row in data if row.get("Telegram-нік") and row.get("Нік")}
    except:
        return {}

nickname_map = load_nickname_map(sheet)

# === Парсинг повідомлення ===
def parse_message(text, thread_title=None, bot_username=None):
    parts = text.strip().split()

    if bot_username and parts and parts[0].lower() == f"@{bot_username.lower()}":
        parts = parts[1:]

    if len(parts) == 2 and thread_title:
        chapter, position = parts
        nickname = None
        title = thread_title
    elif len(parts) == 3 and thread_title:
        chapter, position, nickname = parts
        title = thread_title
    elif len(parts) == 3:
        title, chapter, position = parts
        nickname = None
    elif len(parts) >= 4:
        title, chapter, position = parts[:3]
        nickname = parts[3]
    else:
        return None

    return title, chapter, position, nickname

# === Обробка одного повідомлення ===
async def process_input(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet, text: str, thread_title=None, bot_username=None):
    result = parse_message(text, thread_title=thread_title, bot_username=bot_username)
    if not result:
        await update.message.reply_text("⚠️ Невірний формат. Спробуй ще раз.")
        return

    title, chapter, position, nickname = result
    if not nickname:
        nickname = update.message.from_user.full_name
    nickname = nickname_map.get(nickname, nickname)

    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        update.message.from_user.full_name,
        title,
        chapter,
        position,
        nickname
    ]
    sheet.append_row(row)
    await update.message.reply_text("✅ Дані додано до таблиці.")

# === Команди ===
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Надішли мені:\n"
        "Назва Розділ Позиція Нік (опціонально)\n"
        "або скористайся командою /add у такому ж форматі."
    )

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    message = update.message
    if not message or not message.text:
        return
    text = message.text[len("/add "):].strip()
    thread_title = getattr(message, "message_thread_title", None) or getattr(message, "message_thread_topic", None)
    await process_input(update, context, sheet, text, thread_title=thread_title, bot_username=context.bot.username)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    message = update.message
    if not message or not message.text:
        return
    bot_username = context.bot.username.lower()
    if bot_username in message.text.lower():
        thread_title = getattr(message, "message_thread_title", None) or getattr(message, "message_thread_topic", None)
        await process_input(update, context, sheet, message.text, thread_title=thread_title, bot_username=context.bot.username)

# === Обгортки ===
async def message_handler_wrapper(update, context):
    await handle_message(update, context, sheet)

async def add_command_wrapper(update, context):
    await add_command(update, context, sheet)

# === Webhook ===
async def handle_ping(request):
    return web.Response(text="I'm alive!")

async def handle_webhook(request):
    app = request.app['bot_app']
    update = await request.json()
    telegram_update = Update.de_json(update, app.bot)
    await app.update_queue.put(telegram_update)
    return web.Response(text='OK')

# === Реєстрація користувача ===
ASK_NICKNAME, ASK_ROLES = range(2)
ROLES_LIST = ["Клінер", "Перекладач", "Тайпер", "Редактор"]

def get_user_sheet(sheet):
    try:
        return sheet.spreadsheet.worksheet("Користувачі")
    except:
        return sheet.spreadsheet.add_worksheet("Користувачі", rows=100, cols=3)

async def start_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👤 Введи бажаний нік (наприклад: darmiro):")
    return ASK_NICKNAME

async def ask_roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nickname"] = update.message.text.strip()
    keyboard = [[role] for role in ROLES_LIST]
    await update.message.reply_text(
        "🛠 Обери ролі (через кому, наприклад: Клінер, Тайпер):",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return ASK_ROLES

async def finish_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    roles = update.message.text.strip()
    nickname = context.user_data.get("nickname", "")
    telegram_name = update.message.from_user.full_name

    user_sheet = get_user_sheet(sheet)
    headers = user_sheet.row_values(1)
    if not headers:
        user_sheet.insert_row(["Telegram-нік", "Нік", "Ролі"], index=1)

    user_sheet.append_row([telegram_name, nickname, roles])

    await update.message.reply_text("✅ Реєстрацію завершено!", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def cancel_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Реєстрацію скасовано.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

register_conv = ConversationHandler(
    entry_points=[CommandHandler("register", start_register)],
    states={
        ASK_NICKNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_roles)],
        ASK_ROLES: [MessageHandler(filters.TEXT & ~filters.COMMAND, finish_register)]
    },
    fallbacks=[CommandHandler("cancel", cancel_register)],
    allow_reentry=True
)

# === Запуск бота ===
if __name__ == "__main__":
    TOKEN = os.getenv("TOKEN")
    bot_app = ApplicationBuilder().token(TOKEN).build()

    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("add", add_command_wrapper))
    bot_app.add_handler(register_conv)
    bot_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler_wrapper))

    aio_app = web.Application()
    aio_app['bot_app'] = bot_app
    aio_app.add_routes([
        web.get("/", handle_ping),
        web.post("/webhook", handle_webhook)
    ])

    PORT = int(os.environ.get("PORT", "8443"))
    print(f"🌐 Server running on port {PORT}...")

    bot_app.initialize()
    bot_app.start()
    web.run_app(aio_app, host="0.0.0.0", port=PORT)
