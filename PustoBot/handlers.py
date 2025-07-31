import logging
from telegram import Update
from telegram.ext import ContextTypes
from .core import parse_message
from .sheets import (
    get_title_sheet,
    update_title_table,
    append_log_row,
    load_nickname_map,
)

logger = logging.getLogger(__name__)

# Словник для відстеження активних гілок
active_threads = {}

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message when the command /start is issued."""
    await update.message.reply_text("👋 Привіт! Я — PustoBot, твій помічник для ведення проєктів. Використовуй `/add` щоб додати прогрес, або інші команди.")

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    """Adds a new entry to the sheet."""
    message = update.message
    if not message:
        logger.warning("Отримано пусте повідомлення для /add.")
        return
    
    text = message.text[len("/add "):].strip() if message.text and len(message.text) > len("/add ") else ""
    
    # Отримання назви гілки
    thread_title = getattr(message, "message_thread_title", None) or getattr(message, "message_thread_topic", None)
    
    await process_input(update, context, sheet, text, thread_title, context.bot.username)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    """Handles regular messages that mention the bot or are a reply."""
    message = update.message
    if not message:
        logger.warning("Отримано пусте повідомлення для handle_message.")
        return
    
    # Видаляємо згадку бота, якщо вона є на початку
    bot_username = f"@{context.bot.username}"
    text = message.text.strip()
    if text.startswith(bot_username):
        text = text[len(bot_username):].strip()
        
    thread_title = getattr(message, "message_thread_title", None) or getattr(message, "message_thread_topic", None)
    
    await process_input(update, context, sheet, text, thread_title, context.bot.username)

async def process_input(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet, text, thread_title=None, bot_username=None):
    """Common logic for processing user input."""
    from_user = update.message.from_user
    
    result = parse_message(text, thread_title, bot_username)
    
    if not result:
        await update.message.reply_text(
            "⚠️ Не вдалося розпізнати формат повідомлення. Використай формат: "
            "`Назва Розділ Роль Нік` або `Розділ Роль Нік` (якщо назва гілки встановлена).",
            parse_mode="Markdown"
        )
        return
    
    # ВИПРАВЛЕНО: розпаковуємо результат parse_message, який тепер повертає role
    title, chapter, role, nickname = result

    if not nickname:
        nickname = from_user.full_name

    telegram_tag = from_user.username if from_user.username else ""

    nickname_map = load_nickname_map()
    # Якщо нікнейм, отриманий з команди, є ключем у мапі, замінюємо його на значення з мапи.
    # В іншому випадку залишаємо як є.
    nickname = nickname_map.get(nickname, nickname)

    if sheet is None:
        logger.error("Sheets object is None in process_input. Cannot update table or log.")
        await update.message.reply_text("⚠️ Виникла внутрішня помилка при роботі з таблицями. Зверніться до адміністратора.")
        return

    success_update = update_title_table(title, chapter, role, nickname, sheet) # ВИПРАВЛЕНО: передаємо sheet
    if not success_update:
        await update.message.reply_text(f"⚠️ Не вдалося оновити таблицю для '{title}' розділ '{chapter}'. Перевірте правильність введених даних.")
        return
    
    append_log_row(from_user.full_name, telegram_tag, title, chapter, role, nickname)
    
    await update.message.reply_text(f"✅ Додано запис: *{nickname}* - *{role}* до тайтлу *{title}* (розділ *{chapter}*).", parse_mode="Markdown")