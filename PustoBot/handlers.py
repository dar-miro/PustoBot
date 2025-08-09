import logging
from telegram import Update
from telegram.ext import ContextTypes
from .core import parse_message
from .sheets import (
    update_title_table,
    append_log_row,
    load_nickname_map,
    initialize_header_map
)
from thread import get_thread_title

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message when the command /start is issued."""
    await update.message.reply_text("👋 Привіт! Я — PustoBot, твій помічник для ведення проєктів.")

async def process_input(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, thread_title: str | None = None):
    """Common logic for processing user input for adding progress."""
    from_user = update.message.from_user
    bot_username = context.bot.username
    
    # Викликаємо оновлену функцію парсингу
    result = parse_message(text, thread_title, bot_username)
    
    if not result:
        await update.message.reply_text(
            "⚠️ Не вдалося розпізнати формат. Використайте: `Назва Розділ Роль [Нік]` або `Розділ Роль [Нік]` у гілці тайтлу.",
            parse_mode="Markdown"
        )
        return
    
    title, chapter, role, nickname = result

    # Оновлення: Завантажуємо актуальну мапу нікнеймів перед використанням
    nickname_map = load_nickname_map()
    resolved_nickname = nickname_map.get(from_user.full_name, nickname)

    # Перевірка наявності нікнейму, якщо він не був вказаний
    if not resolved_nickname:
        await update.message.reply_text("⚠️ Не вдалося знайти ваш нікнейм. Будь ласка, зареєструйтесь за допомогою `/register` або вкажіть нікнейм в повідомленні.")
        return

    # Оновлення статусу в таблиці
    success_update = update_title_table(title, chapter, role, resolved_nickname)
    
    if success_update:
        # Логуємо дію
        telegram_tag = from_user.username if from_user.username else ""
        append_log_row(from_user.full_name, telegram_tag, title, chapter, role, resolved_nickname)
        await update.message.reply_text(f"✅ Успішно оновлено: *{title}* (розділ *{chapter}*).", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ Не вдалося оновити статус. Можливо, тайтл або розділ не знайдено.")

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Adds a new entry to the sheet via /add command."""
    message = update.message
    text = message.text[len("/add "):].strip() if message.text and len(message.text) > len("/add ") else ""
    thread_title = get_thread_title(message.message_thread_id)
    await process_input(update, context, text, thread_title)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles regular messages that mention the bot or are a reply."""
    message = update.message
    bot_username = f"@{context.bot.username}"
    text = message.text.strip()
    
    # Видаляємо тег бота, якщо він є на початку
    if text.lower().startswith(bot_username.lower()):
        text = text[len(bot_username):].strip()
    
    thread_title = get_thread_title(message.message_thread_id)
    await process_input(update, context, text, thread_title)