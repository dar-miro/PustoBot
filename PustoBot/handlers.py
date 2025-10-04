# PustoBot/handlers.py
import logging
from telegram import Update
from telegram.ext import ContextTypes
from .core import parse_message 
from .sheets import (
    update_title_table,
    append_log_row,
    resolve_user_nickname,
    get_title_number_and_name
)
from thread import get_thread_number 

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a message when the command /start is issued."""
    await update.message.reply_text("👋 Привіт! Я — PustoBot, твій помічник для ведення проєктів. Використовуй команди: /thread, /add, /status, /publish.")

async def process_input(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, thread_title_or_number: str | None = None):
    """Спільна логіка для обробки прогресу /add."""
    from_user = update.message.from_user
    bot_username = context.bot.username
    
    # Парсимо повідомлення
    result = parse_message(text, thread_title_or_number, bot_username, from_user.username)
    
    if not result:
        await update.message.reply_text(
            "⚠️ Не вдалося розпізнати формат. Використайте: `/add Назва Розділ Роль [Нік]` або `/add Розділ Роль [Нік]` у гілці тайтлу.",
            parse_mode="Markdown"
        )
        return
    
    title_identifier = result['title_identifier']
    chapter = result['chapter']
    role = result['role']
    nickname_from_command = result.get('nickname') 

    # Визначаємо нікнейм для запису в таблицю
    telegram_tag_for_resolution = from_user.username if from_user.username else from_user.full_name
    resolved_nickname = resolve_user_nickname(telegram_tag_for_resolution, nickname_from_command)
    
    # Оновлення таблиці (завдання 1)
    success_update = update_title_table(title_identifier, chapter, role, resolved_nickname)
    
    if success_update:
        # Отримуємо повну назву для логування та відповіді
        full_title_name = title_identifier
        if title_identifier.isdigit():
             _, name = get_title_number_and_name(title_identifier)
             if name:
                 full_title_name = name

        telegram_tag = f"@{from_user.username}" if from_user.username else ""
        append_log_row(from_user.full_name, telegram_tag, full_title_name, chapter, role, resolved_nickname)
        await update.message.reply_text(f"✅ Успішно оновлено: *{full_title_name}* (розділ *{chapter}*).", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ Не вдалося оновити статус. Можливо, тайтл, його номер або розділ не знайдено.")

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Оновлює статус ролі через /add (завдання 1)."""
    message = update.message
    text = message.text[len("/add "):].strip() if message.text and len(message.text) > len("/add ") else ""
    # Отримуємо Номер Тайтлу з гілки
    thread_number = get_thread_number(message.message_thread_id) 
    await process_input(update, context, text, thread_number) 

# Видалено async def handle_message(...)