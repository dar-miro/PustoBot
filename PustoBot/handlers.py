from telegram import Update
from telegram.ext import ContextTypes
from .sheets import load_nickname_map, append_log_row
from .core import parse_message

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Надішли мені:\n"
        "Назва Розділ Позиція Нік (опціонально)\n"
        "або скористайся командою /add у такому ж форматі."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return
    bot_username = context.bot.username.lower()
    if bot_username in message.text.lower():
        thread_title = getattr(message, "message_thread_title", None) or getattr(message, "message_thread_topic", None)
        await process_input(update, context, message.text, thread_title, bot_username)

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return
    text = message.text[len("/add "):].strip()
    thread_title = getattr(message, "message_thread_title", None) or getattr(message, "message_thread_topic", None)
    await process_input(update, context, text, thread_title, context.bot.username)

async def process_input(update, context, text, thread_title, bot_username):
    result = parse_message(text, thread_title, bot_username)
    if not result:
        await update.message.reply_text("⚠️ Невірний формат. Спробуй ще раз.")
        return

    title, chapter, position, nickname = result
    if not nickname:
        nickname = update.message.from_user.full_name

    nickname_map = load_nickname_map()
    nickname = nickname_map.get(nickname, nickname)

    append_log_row(update.message.from_user.full_name, title, chapter, position, nickname)
    await update.message.reply_text("✅ Дані додано до таблиці.")
