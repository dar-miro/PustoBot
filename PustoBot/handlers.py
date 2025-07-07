from .sheets import load_nickname_map, append_log_row, update_title_table, set_main_roles
from .core import parse_message
from telegram import Update
from telegram.ext import ContextTypes
from thread import set_thread_title, get_thread_title

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
    await process_input(update, context, text, thread_title, context.bot.username)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    message = update.message
    if not message or not message.text:
        return
    bot_username = context.bot.username.lower()
    if bot_username in message.text.lower():
        thread_title = getattr(message, "message_thread_title", None) or getattr(message, "message_thread_topic", None)
        await process_input(update, context, message.text, thread_title, bot_username)

async def thread_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    thread_id = msg.message_thread_id or msg.chat_id

    await msg.reply_text("📝 Введи назву тайтлу для цієї гілки:")
    
    def check_response(u): return u.message and u.message.reply_to_message == msg

    # Очікуємо назву тайтлу
    response = await context.application.wait_for_message(filters=None, timeout=60)
    title = response.text.strip()

    set_thread_title(thread_id, title)

    await response.reply_text("✅ Тайтл збережено. Тепер введи основних учасників проєкту у форматі:\n"
                              "`клін - darmiro, переклад - elena`, тощо.", parse_mode="Markdown")

    members_msg = await context.application.wait_for_message(filters=None, timeout=120)
    members_text = members_msg.text.lower()

    roles_map = {}
    for part in members_text.split(","):
        if "-" in part:
            role, nick = [p.strip() for p in part.split("-", 1)]
            roles_map[role] = nick

    set_main_roles(title, roles_map)

    await members_msg.reply_text("✅ Команду збережено.")
   
async def process_input(update, context, sheet, text, thread_title=None, bot_username=None):
    from_user = update.message.from_user
    thread_id = update.message.message_thread_id or update.message.chat_id

    result = parse_message(text, thread_title, bot_username)
    if not result:
        title_from_thread = get_thread_title(thread_id)
        if not title_from_thread:
            await update.message.reply_text("⚠️ У цій гілці не вказано тайтл. Використай /thread.")
            return
        parts = text.strip().split()
        if len(parts) < 2:
            await update.message.reply_text("⚠️ Введи розділ і позицію.")
            return
        chapter, position = parts[:2]
        nickname = parts[2] if len(parts) >= 3 else None
        title = title_from_thread
    else:
        title, chapter, position, nickname = result

    if not nickname:
        nickname = from_user.full_name

    nickname_map = load_nickname_map()
    nickname = nickname_map.get(nickname, nickname)

    append_log_row(from_user.full_name, title, chapter, position, nickname)
    success = update_title_table(title, chapter, position, nickname)

    if success:
        await update.message.reply_text("✅ Дані додано до таблиці і оновлено тайтл.")
    else:
        await update.message.reply_text("✅ Дані додано до журналу, але тайтл не знайдено або не вдалося оновити.")