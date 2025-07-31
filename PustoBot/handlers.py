import logging
from telegram import Update
from telegram.ext import ContextTypes
from .core import parse_message
from .sheets import (
    update_title_table,
    append_log_row,
    load_nickname_map,
    titles_sheet,
    log_sheet,
    get_title_sheet, # Додано
)
from thread import get_thread_title

logger = logging.getLogger(__name__)

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
    thread_title = get_thread_title(message.message_thread_id)
    
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
        
    thread_title = get_thread_title(message.message_thread_id)
    
    await process_input(update, context, sheet, text, thread_title, context.bot.username)

async def process_input(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet, text, thread_title=None, bot_username=None):
    """Common logic for processing user input."""
    from_user = update.message.from_user
    
    result = parse_message(text, thread_title, bot_username)
    
    if not result:
        await update.message.reply_text(
            "⚠️ Не вдалося розпізнати формат повідомлення. "
            "Використай формат: `Назва Розділ Роль Нік` або `Розділ Роль Нік` (якщо назва гілки встановлена).",
            parse_mode="Markdown"
        )
        return
    
    title, chapter, role, nickname = result

    if not nickname:
        nickname = from_user.full_name

    telegram_tag = from_user.username if from_user.username else ""

    nickname_map = load_nickname_map()
    # Замінюємо нікнейм, якщо знайдено відповідність
    resolved_nickname = nickname_map.get(nickname, nickname)

    if sheet is None:
        logger.error("Sheets object is None in process_input. Cannot update table or log.")
        await update.message.reply_text("⚠️ Виникла внутрішня помилка при роботі з таблицями. Зверніться до адміністратора.")
        return

    # Перевірка на існування titles_sheet
    if titles_sheet is None:
        logger.error("titles_sheet is None. Cannot update title table.")
        await update.message.reply_text("⚠️ Внутрішня помилка: аркуш 'Тайтли' не ініціалізовано.")
        return

    # Оновлюємо таблицю тайтлів, передаючи `titles_sheet`
    success_update = update_title_table(title, chapter, role, resolved_nickname, titles_sheet)
    if not success_update:
        await update.message.reply_text(f"⚠️ Не вдалося оновити таблицю для '{title}' розділ '{chapter}'. Перевірте правильність введених даних.")
        return
    
    # Записуємо лог, використовуючи коректний нікнейм
    append_log_row(from_user.full_name, telegram_tag, title, chapter, role, resolved_nickname)
    
    await update.message.reply_text(f"✅ Додано запис: *{resolved_nickname}* - *{role}* до тайтлу *{title}* (розділ *{chapter}*).", parse_mode="Markdown")