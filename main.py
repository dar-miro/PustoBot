import logging
import re
import gspread
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- НАЛАШТУВАННЯ: ВКАЖІТЬ ВАШІ ДАНІ ТУТ ---

# Вставте токен вашого Telegram-бота
TELEGRAM_BOT_TOKEN = "7392593867:AAHSNWTbZxS4BfEKJa3KG7SuhK2G9R5kKQA"

# Назва файлу з ключами доступу до Google API
GOOGLE_CREDENTIALS_FILE = 'credentials.json'

# Назва вашої ГОЛОВНОЇ Google-таблиці
SPREADSHEET_NAME = "PustoBot"

# --- КІНЕЦЬ НАЛАШТУВАНЬ ---

# Налаштування логування
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Словник для ролей та їх відповідних колонок
ROLE_TO_COLUMN = {
    "клін": "Клін",
    "переклад": "Переклад",
    "тайп": "Тайп",
    "редакт": "Редакт",
    "публікація": "Публікація"
}
SHEET_HEADERS = ['Розділ', 'Клін', 'Переклад', 'Тайп', 'Редакт', 'Публікація']

class SheetsHelper:
    """Клас для інкапсуляції всієї роботи з Google Sheets."""
    def __init__(self, credentials_file, spreadsheet_name):
        try:
            gc = gspread.service_account(filename=credentials_file)
            self.spreadsheet = gc.open(spreadsheet_name)
        except Exception as e:
            logger.error(f"Не вдалося підключитися до Google Sheets: {e}")
            self.spreadsheet = None

    def _get_or_create_worksheet(self, title_name):
        """Отримує або створює аркуш для тайтлу."""
        try:
            return self.spreadsheet.worksheet(title_name)
        except gspread.WorksheetNotFound:
            logger.info(f"Створення нового аркуша для тайтлу: {title_name}")
            worksheet = self.spreadsheet.add_worksheet(title=title_name, rows="100", cols="10")
            worksheet.append_row(SHEET_HEADERS)
            return worksheet

    def register_user(self, user_id, username, nickname):
        """Реєструє або оновлює користувача на аркуші 'Users'."""
        if not self.spreadsheet: return "Помилка підключення до таблиці."
        try:
            users_sheet = self.spreadsheet.worksheet("Users")
            user_ids = users_sheet.col_values(1)
            if str(user_id) in user_ids:
                row_index = user_ids.index(str(user_id)) + 1
                users_sheet.update_cell(row_index, 2, username)
                users_sheet.update_cell(row_index, 3, nickname)
                return f"✅ Ваші дані оновлено. Нікнейм: {nickname}"
            else:
                users_sheet.append_row([str(user_id), username, nickname])
                return f"✅ Вас успішно зареєстровано. Нікнейм: {nickname}"
        except Exception as e:
            logger.error(f"Помилка реєстрації: {e}")
            return "❌ Сталася помилка під час реєстрації."

    def add_chapter(self, title_name, chapter_number):
        """Додає новий розділ до відповідного аркуша тайтлу."""
        if not self.spreadsheet: return "Помилка підключення до таблиці."
        try:
            worksheet = self._get_or_create_worksheet(title_name)
            chapters = worksheet.col_values(1)
            if str(chapter_number) in chapters:
                return f"⚠️ Розділ {chapter_number} для '{title_name}' вже існує."
            
            new_row = [str(chapter_number)] + ['FALSE'] * (len(SHEET_HEADERS) - 1)
            worksheet.append_row(new_row)
            return f"✅ Додано розділ {chapter_number} до тайтлу '{title_name}'."
        except Exception as e:
            logger.error(f"Помилка додавання розділу: {e}")
            return "❌ Сталася помилка при додаванні розділу."

    def get_status(self, title_name):
        """Отримує статус усіх розділів для тайтлу."""
        if not self.spreadsheet: return "Помилка підключення до таблиці."
        try:
            worksheet = self.spreadsheet.worksheet(title_name)
            records = worksheet.get_all_records()
            if not records:
                return f"📊 Для тайтлу '{title_name}' ще немає жодного розділу."
            
            response = [f"📊 *Статус тайтлу '{title_name}':*\n"]
            for record in records:
                chapter = record['Розділ']
                statuses = []
                for role_key, col_name in ROLE_TO_COLUMN.items():
                    status_char = "✅" if record[col_name] == 'TRUE' else "❌"
                    statuses.append(f"{role_key}: {status_char}")
                response.append(f"*{chapter}* — _{' | '.join(statuses)}_")
            return "\n".join(response)
        except gspread.WorksheetNotFound:
            return f"⚠️ Тайтл '{title_name}' не знайдено."
        except Exception as e:
            logger.error(f"Помилка отримання статусу: {e}")
            return "❌ Сталася помилка при отриманні статусу."

    def update_chapter_status(self, title_name, chapter_number, role, status_char):
        """Оновлює статус конкретної ролі для розділу."""
        if not self.spreadsheet: return "Помилка підключення до таблиці."
        if role.lower() not in ROLE_TO_COLUMN:
            return f"⚠️ Невідома роль '{role}'. Доступні: {', '.join(ROLE_TO_COLUMN.keys())}"
        
        try:
            worksheet = self.spreadsheet.worksheet(title_name)
            cell = worksheet.find(str(chapter_number))
            if not cell:
                return f"⚠️ Розділ {chapter_number} не знайдено в тайтлі '{title_name}'."
            
            col_name = ROLE_TO_COLUMN[role.lower()]
            headers = worksheet.row_values(1)
            col_index = headers.index(col_name) + 1
            
            new_status = 'TRUE' if status_char == '+' else 'FALSE'
            worksheet.update_cell(cell.row, col_index, new_status)
            
            return f"✅ Статус оновлено: '{title_name}', розділ {chapter_number}, роль {role} → {status_char}"
        except gspread.WorksheetNotFound:
            return f"⚠️ Тайтл '{title_name}' не знайдено."
        except ValueError: # .index() fails
            return f"❌ Помилка: колонка '{col_name}' не знайдена в таблиці."
        except Exception as e:
            logger.error(f"Помилка оновлення статусу: {e}")
            return "❌ Сталася помилка при оновленні статусу."

# --- Обробники команд Telegram ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привіт! Це бот для відстеження роботи над тайтлами. Використовуйте /help для списку команд.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 *Список доступних команд:*\n\n"
        "👤 `/register <нікнейм>`\n_Реєструє вас у системі._\n\n"
        "➕ `/newchapter \"Назва Тайтлу\" <номер_розділу>`\n_Додає новий розділ до тайтлу. Назву брати в лапки!_\n\n"
        "📊 `/status \"Назва Тайтлу\"`\n_Показує статус усіх розділів тайтлу._\n\n"
        "🔄 `/updatestatus \"Назва Тайтлу\" <номер_розділу> <роль> <+|->`\n_Оновлює статус завдання. Ролі: клін, переклад, тайп, редакт, публікація._"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Будь ласка, вкажіть ваш нікнейм. Приклад: `/register SuperTranslator`")
        return
    nickname = " ".join(context.args)
    sheets = SheetsHelper(GOOGLE_CREDENTIALS_FILE, SPREADSHEET_NAME)
    response = sheets.register_user(user.id, user.username or "N/A", nickname)
    await update.message.reply_text(response)

def parse_title_and_args(text):
    """Парсер для команд, що містять назву тайтлу в лапках."""
    match = re.search(r'\"(.*?)\"', text)
    if not match:
        return None, None
    title = match.group(1)
    remaining_args = text[match.end():].strip().split()
    return title, remaining_args

async def new_chapter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    full_text = " ".join(context.args)
    title, args = parse_title_and_args(full_text)
    if not title or len(args) != 1 or not args[0].isdigit():
        await update.message.reply_text('Невірний формат. Приклад: `/newchapter "Відьмоварта" 15`')
        return
    chapter = args[0]
    sheets = SheetsHelper(GOOGLE_CREDENTIALS_FILE, SPREADSHEET_NAME)
    response = sheets.add_chapter(title, chapter)
    await update.message.reply_text(response)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    full_text = " ".join(context.args)
    title, _ = parse_title_and_args(full_text)
    if not title:
        await update.message.reply_text('Невірний формат. Приклад: `/status "Відьмоварта"`')
        return
    sheets = SheetsHelper(GOOGLE_CREDENTIALS_FILE, SPREADSHEET_NAME)
    response = sheets.get_status(title)
    await update.message.reply_text(response, parse_mode="Markdown")

async def update_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    full_text = " ".join(context.args)
    title, args = parse_title_and_args(full_text)
    if not title or len(args) != 3 or not args[0].isdigit() or args[2] not in ['+', '-']:
        await update.message.reply_text('Невірний формат. Приклад: `/updatestatus "Відьмоварта" 15 клін +`')
        return
    chapter, role, status_char = args
    sheets = SheetsHelper(GOOGLE_CREDENTIALS_FILE, SPREADSHEET_NAME)
    response = sheets.update_chapter_status(title, chapter, role, status_char)
    await update.message.reply_text(response)

def main():
    """Основна функція для запуску бота."""
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("register", register))
    application.add_handler(CommandHandler("newchapter", new_chapter))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("updatestatus", update_status))

    logger.info("Бот запускається...")
    application.run_polling()

if __name__ == '__main__':
    main()