from .sheets import load_nickname_map, append_log_row, update_title_table, set_main_roles, get_title_sheet
from .core import parse_message
from telegram import Update
from telegram.ext import ContextTypes
from thread import set_thread_title, get_thread_title
import logging

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Надішли мені:\\n"
        "Назва Розділ Позиція Нік (опціонально)\\n"
        "або скористайся командою /add у такому ж форматі."
    )

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    message = update.message
    if not message:
        logger.warning("Отримано пусте повідомлення для /add.")
        return
    
    # ВИПРАВЛЕНО: Залишаємо text як є, parse_message тепер сам вирішує
    text = message.text[len("/add "):].strip() if message.text and len(message.text) > len("/add ") else ""
    
    thread_title = getattr(message, "message_thread_title", None) or getattr(message, "message_thread_topic", None)
    
    await process_input(update, context, sheet, text, thread_title, context.bot.username)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    message = update.message
    if not message or not message.text:
        logger.warning("Отримано пусте повідомлення.")
        return
    bot_username = context.bot.username.lower()
    
    text_to_parse = message.text
    if bot_username in text_to_parse.lower():
        text_to_parse = text_to_parse.lower().replace(f"@{bot_username}", "").strip()

    thread_title = getattr(message, "message_thread_title", None) or getattr(message, "message_thread_topic", None)
    
    await process_input(update, context, sheet, text_to_parse, thread_title, context.bot.username)

async def process_input(update, context, sheet, text, thread_title=None, bot_username=None):
    from_user = update.message.from_user
    thread_id = update.message.message_thread_id or update.message.chat_id

    logger.info(f"Processing input: text='{text}', thread_title='{thread_title}', bot_username='{bot_username}'")

    result = parse_message(text, thread_title, bot_username)
    
    if not result:
        # Якщо parse_message не зміг розпарсити жоден з форматів, повідомляємо про помилку
        await update.message.reply_text("⚠️ Не вдалося розпізнати формат повідомлення. "
                                        "Використай формат: `Назва Розділ Позиція Нік` "
                                        "або `Розділ Позиція Нік` (якщо назва гілки встановлена).", parse_mode="Markdown")
        return
    else:
        title, chapter, position, nickname = result

    if not nickname:
        nickname = from_user.full_name

    telegram_tag = from_user.username if from_user.username else ""

    nickname_map = load_nickname_map()
    nickname = nickname_map.get(nickname, nickname)

    if sheet is None:
        logger.error("Sheets object is None in process_input. Cannot update table or log.")
        await update.message.reply_text("⚠️ Виникла внутрішня помилка при роботі з таблицями. Зверніться до адміністратора.")
        return

    success_update = update_title_table(title, chapter, "клін", nickname) # Залишив "клін" як приклад.
    if not success_update:
        await update.message.reply_text(f"⚠️ Не вдалося оновити таблицю для '{title}' розділ '{chapter}'. Перевірте правильність введених даних.")
        return

    append_log_row(from_user.full_name, telegram_tag, title, chapter, position, nickname)

    await update.message.reply_text(f"✅ Для тайтлу *{title}* розділ *{chapter}* оновлено статус для {nickname}.", parse_mode="Markdown")