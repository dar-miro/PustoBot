from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    filters,
)
import logging
import gspread 
from PustoBot.sheets import (
    load_nickname_map, 
    append_log_row, 
    get_user_sheet,
    find_user_row_by_nick_or_tag, # Імпортуємо нові функції
    update_user_row,             # Імпортуємо нові функції
    append_user_row              # Імпортуємо нові функції
)

logger = logging.getLogger(__name__)

# Нові стани для розмови
ASK_NICKNAME, CONFIRM_OVERWRITE, ASK_ROLES = range(3)
ROLES_LIST = ["Клінер", "Перекладач", "Тайпер", "Редактор"]

# Старт реєстрації
async def start_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        await update.message.reply_text("⚠️ Реєстрація доступна лише в особистих повідомленнях.")
        return ConversationHandler.END

    await update.message.reply_text("👤 Введи бажаний нік (наприклад: darmiro):", reply_markup=ReplyKeyboardRemove())
    return ASK_NICKNAME

# Обробка введеного ніку та перевірка наявності
async def handle_nickname_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desired_nick = update.message.text.strip()
    telegram_full_name = update.message.from_user.full_name
    telegram_username = update.message.from_user.username # Отримуємо тег телеграму

    # Зберігаємо дані для подальшого використання
    context.user_data["desired_nick"] = desired_nick
    context.user_data["telegram_full_name"] = telegram_full_name
    context.user_data["telegram_username"] = telegram_username if telegram_username else "" # Забезпечуємо, що це не None

    main_spreadsheet_instance = context.bot_data.get('main_spreadsheet_instance')
    if main_spreadsheet_instance is None:
        await update.message.reply_text("⚠️ Виникла помилка: не вдалося підключитися до таблиць. Зверніться до адміністратора.")
        logger.error("main_spreadsheet_instance is None in handle_nickname_input.")
        return ConversationHandler.END

    # Шукаємо існуючого користувача
    existing_row_index, existing_row_data = find_user_row_by_nick_or_tag(
        telegram_full_name, telegram_username, desired_nick
    )

    if existing_row_index:
        context.user_data["existing_row_index"] = existing_row_index
        context.user_data["existing_row_data"] = existing_row_data
        
        reply_keyboard = [
            [KeyboardButton("Так"), KeyboardButton("Ні")]
        ]
        await update.message.reply_text(
            f"ℹ️ Здається, ви вже зареєстровані, або цей нік/Telegram-нік вже використовується.\\n"
            f"Знайдено: Telegram-нік: '{existing_row_data[0]}', Тег: '{existing_row_data[1]}', Нік: '{existing_row_data[2]}', Ролі: '{existing_row_data[3]}'\\n"
            f"Бажаєте перезаписати свої дані на актуальні (новий нік '{desired_nick}' та тег '{telegram_username if telegram_username else 'відсутній'}')?",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return CONFIRM_OVERWRITE
    else:
        # Користувача не знайдено, переходимо до запиту ролей
        await update.message.reply_text(
            "🛠 Введи ролі вручну через кому (наприклад: Клінер, Тайпер).\\n"
            "Можливі ролі: Клінер, Перекладач, Тайпер, Редактор",
            reply_markup=ReplyKeyboardRemove()
        )
        return ASK_ROLES

# Обробка підтвердження перезапису
async def confirm_overwrite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_choice = update.message.text.strip().lower()

    if user_choice == "так":
        # Перезаписуємо дані
        existing_row_index = context.user_data["existing_row_index"]
        desired_nick = context.user_data["desired_nick"]
        telegram_full_name = context.user_data["telegram_full_name"]
        telegram_username = context.user_data["telegram_username"]
        
        # На цьому етапі ролі ще не відомі, тому оновимо їх пізніше
        # Або можна зберегти старі ролі, якщо вони потрібні
        # Для простоти зараз, ми їх запитаємо знову або залишимо порожніми на цьому кроці

        # Просимо ролі після підтвердження перезапису
        await update.message.reply_text(
            "🛠 Добре, дані буде оновлено. Тепер введи свої ролі вручну через кому (наприклад: Клінер, Тайпер).\\n"
            "Можливі ролі: Клінер, Перекладач, Тайпер, Редактор",
            reply_markup=ReplyKeyboardRemove()
        )
        return ASK_ROLES
    elif user_choice == "ні":
        await update.message.reply_text("❌ Реєстрацію скасовано.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END
    else:
        reply_keyboard = [
            [KeyboardButton("Так"), KeyboardButton("Ні")]
        ]
        await update.message.reply_text(
            "Будь ласка, оберіть 'Так' або 'Ні'.",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
        )
        return CONFIRM_OVERWRITE # Залишаємося на цьому ж кроці

# Запитати ролі (після введення нового ніку або підтвердження перезапису)
async def ask_roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    roles = update.message.text.strip()
    context.user_data["roles"] = roles # Зберігаємо ролі

    # Тепер викликаємо фіналізацію реєстрації
    return await finish_register(update, context)


# Завершення реєстрації (тепер використовує оновлення або додавання)
async def finish_register(update: Update, context: ContextTypes.DEFAULT_TYPE): 
    desired_nick = context.user_data.get("desired_nick", "")
    telegram_full_name = context.user_data.get("telegram_full_name", "")
    telegram_username = context.user_data.get("telegram_username", "")
    roles = context.user_data.get("roles", "")
    existing_row_index = context.user_data.get("existing_row_index", None)

    main_spreadsheet_instance = context.bot_data.get('main_spreadsheet_instance')
    if main_spreadsheet_instance is None:
        await update.message.reply_text("⚠️ Виникла помилка: не вдалося підключитися до таблиць. Зверніться до адміністратора.")
        logger.error("main_spreadsheet_instance is None in finish_register.")
        return ConversationHandler.END

    if existing_row_index:
        # Оновлюємо існуючий рядок
        success = update_user_row(
            existing_row_index, telegram_full_name, telegram_username, desired_nick, roles
        )
        if success:
            await update.message.reply_text("✅ Ваші дані успішно оновлено!", reply_markup=ReplyKeyboardRemove())
        else:
            await update.message.reply_text("⚠️ Виникла помилка під час оновлення даних. Спробуйте ще раз.", reply_markup=ReplyKeyboardRemove())
    else:
        # Додаємо новий рядок
        success = append_user_row(
            telegram_full_name, telegram_username, desired_nick, roles
        )
        if success:
            await update.message.reply_text("✅ Реєстрацію завершено! Ваші дані збережено.", reply_markup=ReplyKeyboardRemove())
        else:
            await update.message.reply_text("⚠️ Виникла помилка під час збереження даних. Спробуйте ще раз.", reply_markup=ReplyKeyboardRemove())
    
    # Очищаємо user_data після завершення розмови
    context.user_data.clear()
    return ConversationHandler.END

# Скасування
async def cancel_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Реєстрацію скасовано.", reply_markup=ReplyKeyboardRemove())
    context.user_data.clear() # Очищаємо дані при скасуванні
    return ConversationHandler.END

# Обгортка для отримання обробника розмови
def get_register_handler(main_spreadsheet_instance):
    async def _start_register_with_context(update, context):
        context.bot_data['main_spreadsheet_instance'] = main_spreadsheet_instance
        return await start_register(update, context)

    # Оновлення обробників станів для передачі контексту
    async def _handle_nickname_input_with_context(update, context):
        context.bot_data['main_spreadsheet_instance'] = main_spreadsheet_instance
        return await handle_nickname_input(update, context)
    
    async def _confirm_overwrite_with_context(update, context):
        context.bot_data['main_spreadsheet_instance'] = main_spreadsheet_instance
        return await confirm_overwrite(update, context)
    
    async def _ask_roles_with_context(update, context):
        context.bot_data['main_spreadsheet_instance'] = main_spreadsheet_instance
        return await ask_roles(update, context)
    
    async def _finish_register_with_context(update, context):
        context.bot_data['main_spreadsheet_instance'] = main_spreadsheet_instance
        return await finish_register(update, context)


    return ConversationHandler(
        entry_points=[CommandHandler("register", _start_register_with_context)],
        states={
            ASK_NICKNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_nickname_input_with_context)],
            CONFIRM_OVERWRITE: [MessageHandler(filters.TEXT & ~filters.COMMAND, _confirm_overwrite_with_context)],
            ASK_ROLES: [MessageHandler(filters.TEXT & ~filters.COMMAND, _ask_roles_with_context)],
        },
        fallbacks=[CommandHandler("cancel", cancel_register)],
    )