from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters

ASK_NICKNAME, ASK_ROLES = range(2)
ROLES_LIST = ["Клінер", "Перекладач", "Тайпер", "Редактор"]

def get_user_sheet(sheet):
    try:
        return sheet.spreadsheet.worksheet("Користувачі")
    except:
        return sheet.spreadsheet.add_worksheet("Користувачі", rows=100, cols=3)

async def start_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        await update.message.reply_text("⚠️ Реєстрація доступна лише в особистих повідомленнях.")
        return ConversationHandler.END
    await update.message.reply_text("👤 Введи бажаний нік (наприклад: darmiro):")
    return ASK_NICKNAME  # <- Повертаємо наступний стан

async def ask_roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("DEBUG: отримано нік, питаю ролі")
    context.user_data["nickname"] = update.message.text.strip()
    keyboard = [[role] for role in ROLES_LIST]
    await update.message.reply_text(
        "🛠 Обери ролі (через кому, наприклад: Клінер, Тайпер):",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return ASK_ROLES  # <- теж повертаємо

async def finish_register(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    roles = update.message.text.strip()
    nickname = context.user_data.get("nickname", "")
    telegram_name = update.message.from_user.full_name

    user_sheet = get_user_sheet(sheet)
    headers = user_sheet.row_values(1)
    if not headers:
        user_sheet.insert_row(["Telegram-нік", "Нік", "Ролі"], index=1)

    user_sheet.append_row([telegram_name, nickname, roles])

    await update.message.reply_text("✅ Реєстрацію завершено!", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END  # <- повертаємо кінець розмови

async def cancel_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Реєстрацію скасовано.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def get_register_handler(sheet):
    return ConversationHandler(
        entry_points=[CommandHandler("register", start_register)],
        states={
            ASK_NICKNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_roles)],
            ASK_ROLES: [MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: finish_register(u, c, sheet))]
        },
        fallbacks=[CommandHandler("cancel", cancel_register)],
        allow_reentry=True
    )
