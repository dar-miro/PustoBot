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
    await update.message.reply_text("👤 Введи бажаний нік (наприклад: darmiro):")
    return ASK_NICKNAME

async def ask_roles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nickname"] = update.message.text.strip()
    keyboard = [[role] for role in ROLES_LIST]
    await update.message.reply_text(
        "🛠 Обери ролі (через кому, наприклад: Клінер, Тайпер):",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return ASK_ROLES

async def finish_register(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    roles = update.message.text.strip()
    nickname = context.user_data.get("nickname", "")
    telegram_name = update.message.from_user.full_name
    username = update.message.from_user.username or telegram_name

    user_sheet = get_user_sheet(sheet)
    headers = user_sheet.row_values(1)
    if not headers:
        user_sheet.insert_row(["Telegram-нік", "Нік", "Ролі"], index=1)

    user_sheet.append_row([telegram_name, nickname, roles])

    await update.message.reply_text("✅ Реєстрацію завершено!", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

async def cancel_register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Реєстрацію скасовано.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END
