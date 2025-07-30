from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
import gspread
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
import logging
# sheets імпортуємо, але не ініціалізуємо тут глобально
from PustoBot.sheets import load_nickname_map, append_log_row # Додано import

logger = logging.getLogger(__name__)

ASK_NICKNAME, ASK_ROLES = range(2)
ROLES_LIST = ["Клінер", "Перекладач", "Тайпер", "Редактор"]

# Отримати аркуш користувачів
# Ця функція тепер приймає `main_spreadsheet_instance` як аргумент
def get_user_sheet(main_spreadsheet_instance):
    if main_spreadsheet_instance is None:
        logger.error("main_spreadsheet_instance is None in get_user_sheet.")
        return None
    try:
        return main_spreadsheet_instance.worksheet("Користувачі")
    except gspread.exceptions.WorksheetNotFound:
        logger.warning("Worksheet 'Користувачі' not found, creating a new one.")
        return main_spreadsheet_instance.add_worksheet("Користувачі", rows=100, cols=3)
    except Exception as e:
        logger.error(f"Error getting or creating 'Користувачі' sheet: {e}")
        return None

# Старт реєстрації
async def start_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        await update.message.reply_text("⚠️ Реєстрація доступна лише в особистих повідомленнях.")
        return ConversationHandler.END

    await update.message.reply_text("👤 Введи бажаний нік (наприклад: darmiro):")
    return ASK_NICKNAME

# Запитати ролі
async def ask_roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nickname"] = update.message.text.strip()
    await update.message.reply_text(
        "🛠 Введи ролі вручну через кому (наприклад: Клінер, Тайпер).\\n"
        "Можливі ролі: Клінер, Перекладач, Тайпер, Редактор"
    )
    return ASK_ROLES

# Завершення
async def finish_register(update: Update, context: ContextTypes.DEFAULT_TYPE): # sheet не потрібен тут
    roles = update.message.text.strip()
    nickname = context.user_data.get("nickname", "")
    telegram_name = update.message.from_user.full_name

    # sheet тепер береться з контексту або через глобальний import,
    # але важливіше, що get_user_sheet вимагає main_spreadsheet_instance.
    # main_spreadsheet_instance буде передаватися через get_register_handler
    # і зберігатися у Context (якщо потрібно), або використовувати глобально з sheets.py
    # Оскільки `get_user_sheet` вимагає `main_spreadsheet_instance`, а не `sheet` (titles_sheet),
    # ми повинні передавати саме `main_spreadsheet` з `sheets.py` через handler.
    # Context.bot.main_spreadsheet або інший спосіб.
    
    # Виправлення: отримати main_spreadsheet_instance з context, якщо він був встановлений
    # Якщо він не встановлений, можна спробувати отримати його з sheets.py напряму, але це менш чисто.
    # Простіше, щоб get_register_handler передавав його.
    main_spreadsheet_instance = context.bot_data.get('main_spreadsheet_instance')
    
    if main_spreadsheet_instance is None:
        await update.message.reply_text("⚠️ Виникла помилка: не вдалося підключитися до таблиць. Зверніться до адміністратора.")
        logger.error("main_spreadsheet_instance is None in finish_register.")
        return ConversationHandler.END

    user_sheet = get_user_sheet(main_spreadsheet_instance)
    if user_sheet is None:
        await update.message.reply_text("⚠️ Виникла помилка: не вдалося отримати аркуш користувачів. Зверніться до адміністратора.")
        return ConversationHandler.END

    try:
        headers = user_sheet.row_values(1)
        if not headers or len(headers) < 3: # Перевірка, чи є достатньо заголовків
            user_sheet.insert_row(["Telegram-нік", "Нік", "Ролі"], index=1)
            headers = user_sheet.row_values(1) # Оновити заголовки після вставки

        user_sheet.append_row([telegram_name, nickname, roles])

        await update.message.reply_text("✅ Реєстрацію завершено!", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Помилка при завершенні реєстрації: {e}")
        await update.message.reply_text("⚠️ Виникла помилка під час збереження даних. Спробуйте ще раз.")
        return ConversationHandler.END

# Скасування
async def cancel_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Реєстрацію скасовано.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# Обгортка, щоб sheet передати (main_spreadsheet_instance)
def get_register_handler(main_spreadsheet_instance):
    # Зберігаємо main_spreadsheet_instance у bot_data, щоб він був доступний у станах
    async def _start_register_with_context(update, context):
        context.bot_data['main_spreadsheet_instance'] = main_spreadsheet_instance
        return await start_register(update, context)

    async def _finish_register_with_context(update, context):
        context.bot_data['main_spreadsheet_instance'] = main_spreadsheet_instance
        return await finish_register(update, context)

    return ConversationHandler(
        entry_points=[CommandHandler("register", _start_register_with_context)],
        states={
            ASK_NICKNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_roles)],
            ASK_ROLES: [MessageHandler(filters.TEXT & ~filters.COMMAND, _finish_register_with_context)],
        },
        fallbacks=[CommandHandler("cancel", cancel_register)],
    )