from .sheets import load_nickname_map, append_log_row, update_title_table
from .core import parse_message
from telegram import Update
from telegram.ext import ContextTypes

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Надішли мені:\n"
        "Назва Розділ Позиція Нік (опціонально)\n"
        "або скористайся командою /add у такому ж форматі."
    )
    
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

    # Якщо позиція збігається з відомою роллю — оновлюємо таблицю
    success = update_title_table(title, chapter, position, nickname)

    if success:
        await update.message.reply_text("✅ Дані додано до таблиці і оновлено тайтл.")
    else:
        await update.message.reply_text("✅ Дані додано до журналу, але тайтл не знайдено або не вдалося оновити.")
