import logging
import re
import gspread
import asyncio
import os
from aiohttp import web
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from datetime import datetime # Додано для отримання поточної дати

# --- НАЛАШТУВАННЯ: ВКАЖІТЬ ВАШІ ДАНІ ТУТ ---

# Вставте токен вашого Telegram-бота
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "7392593867:AAHSNWTbZxS4BfEKJa3KG7SuhK2G9R5kKQA") # Зчитування з ENVs
# URL для встановлення вебхука.
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://pustobot.onrender.com/") # Зчитування з ENVs

# Назва файлу з ключами доступу до Google API
GOOGLE_CREDENTIALS_FILE = 'credentials.json'

# Назва вашої ГОЛОВНОЇ Google-таблиці
SPREADSHEET_NAME = "PustoBot"

# --- КІНЕЦЬ НАЛАШТУВАНЬ ---

# Налаштування логування
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Словник для ролей та їх відповідних колонок (ОНОВЛЕНО)
# Тепер кожна роль має колонку для СТАТУСУ та колонку для ДАТИ
ROLE_TO_COLUMN_BASE = {
    "клін": "Клін",
    "переклад": "Переклад",
    "тайп": "Тайп",
    "редакт": "Редакт",
}
# Публікація поки залишається єдиною, як у вашому прикладі
PUBLISH_COLUMN = "Публікація"

# ОНОВЛЕНО: Тепер заголовки включають пари 'Статус' та 'Дата'
SHEET_HEADERS = ['Розділ']
for role in ROLE_TO_COLUMN_BASE.values():
    SHEET_HEADERS.extend([f'{role}-Статус', f'{role}-Дата'])
SHEET_HEADERS.append(PUBLISH_COLUMN)
# SHEET_HEADERS тепер виглядає так: ['Розділ', 'Клін-Статус', 'Клін-Дата', 'Переклад-Статус', 'Переклад-Дата', 'Тайп-Статус', 'Тайп-Дата', 'Редакт-Статус', 'Редакт-Дата', 'Публікація']

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
        if not self.spreadsheet: raise ConnectionError("Немає підключення до Google Sheets.")
        try:
            return self.spreadsheet.worksheet(title_name)
        except gspread.WorksheetNotFound:
            logger.info(f"Створення нового аркуша для тайтлу: {title_name}")
            # Збільшуємо кількість колонок для вмісту всіх нових заголовків
            worksheet = self.spreadsheet.add_worksheet(title=title_name, rows="100", cols=str(len(SHEET_HEADERS) + 2)) 
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
                # Врахуйте, що ваша таблиця "Користувачі" має 4 колонки: Telegram-нік, Теґ, Нік, Ролі
                # Тут ми записуємо тільки перші три. Ролі, ймовірно, додаються пізніше.
                users_sheet.append_row([str(user_id), username, nickname, '']) # додаємо порожню колонку для Ролей
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
            
            # ОНОВЛЕНО: створюємо рядок, де статус = 'FALSE' (❌), а дата = ''
            new_row_data = [str(chapter_number)]
            for _ in ROLE_TO_COLUMN_BASE:
                 new_row_data.extend(['FALSE', '']) # 'Статус', 'Дата'
            new_row_data.append('FALSE') # 'Публікація'

            worksheet.append_row(new_row_data)
            return f"✅ Додано розділ {chapter_number} до тайтлу '{title_name}'."
        except Exception as e:
            logger.error(f"Помилка додавання розділу: {e}")
            return "❌ Сталася помилка при додаванні розділу."

    def get_status(self, title_name):
        """Отримує статус усіх розділів для тайтлу."""
        if not self.spreadsheet: return "Помилка підключення до таблиці."
        try:
            worksheet = self.spreadsheet.worksheet(title_name)
            # Отримуємо всі значення, а не records, щоб коректно обробляти дати
            all_values = worksheet.get_all_values()
            if len(all_values) <= 1:
                 return f"📊 Для тайтлу '{title_name}' ще немає жодного розділу."
            
            headers = all_values[0]
            records = all_values[1:]

            response = [f"📊 *Статус тайтлу '{title_name}':*\n"]
            
            for row in records:
                chapter = row[0]
                statuses = []
                
                for role_key, role_base_name in ROLE_TO_COLUMN_BASE.items():
                    status_col_name = f'{role_base_name}-Статус'
                    date_col_name = f'{role_base_name}-Дата'
                    
                    try:
                        status_index = headers.index(status_col_name)
                        date_index = headers.index(date_col_name)
                        
                        status_value = row[status_index].strip().upper()
                        date_value = row[date_index].strip()
                        
                        status_char = "✅" if status_value == 'TRUE' else "❌"
                        date_info = f" ({date_value})" if date_value else ""
                        
                        statuses.append(f"*{role_key}*: {status_char}{date_info}")
                    except ValueError:
                        # Якщо колонка не знайдена, виводимо лише статус
                        statuses.append(f"*{role_key}*: ⚠️") 

                response.append(f"*{chapter}* — _{' | '.join(statuses)}_")
            return "\n".join(response)
        except gspread.WorksheetNotFound:
            return f"⚠️ Тайтл '{title_name}' не знайдено."
        except Exception as e:
            logger.error(f"Помилка отримання статусу: {e}")
            return "❌ Сталася помилка при отриманні статусу."

    def update_chapter_status(self, title_name, chapter_number, role, status_char):
        """Оновлює статус конкретної ролі для розділу та записує дату."""
        if not self.spreadsheet: return "Помилка підключення до таблиці."
        
        role_lower = role.lower()
        if role_lower not in ROLE_TO_COLUMN_BASE and role_lower != 'публікація':
            return f"⚠️ Невідома роль '{role}'. Доступні: {', '.join(ROLE_TO_COLUMN_BASE.keys())}, публікація"
        
        try:
            worksheet = self.spreadsheet.worksheet(title_name)
            cell = worksheet.find(str(chapter_number))
            if not cell:
                return f"⚠️ Розділ {chapter_number} не знайдено в тайтлі '{title_name}'."
            
            headers = worksheet.row_values(1)
            row_index = cell.row
            
            new_status = 'TRUE' if status_char == '+' else 'FALSE'
            current_date = datetime.now().strftime("%d.%m")

            if role_lower == 'публікація':
                status_col_name = PUBLISH_COLUMN
                date_col_name = None # У вашій структурі дата публікації окремо не потрібна, лише статус
                
                # Публікація - це завжди '✅' / '❌', а не TRUE/FALSE, якщо вона в кінці рядка
                new_status_char = '✅' if status_char == '+' else '❌'
                
                status_index = headers.index(status_col_name) + 1
                worksheet.update_cell(row_index, status_index, new_status_char)

                return f"✅ Статус оновлено: '{title_name}', розділ {chapter_number}, роль Публікація → {status_char}"

            else:
                # Оновлення статусу для ролей (Клін, Переклад, Тайп, Редакт)
                role_base_name = ROLE_TO_COLUMN_BASE[role_lower]
                status_col_name = f'{role_base_name}-Статус'
                date_col_name = f'{role_base_name}-Дата'
                
                status_index = headers.index(status_col_name) + 1
                date_index = headers.index(date_col_name) + 1
                
                # 1. Оновлюємо статус
                worksheet.update_cell(row_index, status_index, new_status)
                
                # 2. Оновлюємо дату (тільки якщо статус встановлюється на '+')
                if status_char == '+':
                    worksheet.update_cell(row_index, date_index, current_date)
                else:
                    # Якщо статус скидається ('-'), очищуємо дату
                    worksheet.update_cell(row_index, date_index, '')

                return f"✅ Статус оновлено: '{title_name}', розділ {chapter_number}, роль {role} → {status_char}"
        
        except gspread.WorksheetNotFound:
            return f"⚠️ Тайтл '{title_name}' не знайдено."
        except ValueError as ve: # .index() fails, коли колонка не знайдена
            logger.error(f"Помилка індексування колонки: {ve}")
            return f"❌ Помилка: Не знайдена колонка для статусу/дати '{role_base_name}'."
        except Exception as e:
            logger.error(f"Помилка оновлення статусу: {e}")
            return "❌ Сталася помилка при оновленні статусу."

# --- Обробники команд Telegram (без змін) ---
# ... (start_command, help_command, register, parse_title_and_args, new_chapter, status, update_status залишаються незмінними, оскільки логіка взаємодії з таблицею змінилася всередині SheetsHelper)
# ...

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


# --- АСИНХРОННИЙ ЗАПУСК ДЛЯ WEBHOOKS (без змін) ---
# ... (main та його логіка вебхука залишаються незмінними)
# ...

async def main():
    """Основна асинхронна функція для запуску бота."""
    
    # 1. Створення Application
    bot_app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Додавання обробників
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("help", help_command))
    bot_app.add_handler(CommandHandler("register", register))
    bot_app.add_handler(CommandHandler("newchapter", new_chapter))
    bot_app.add_handler(CommandHandler("status", status))
    bot_app.add_handler(CommandHandler("updatestatus", update_status))
    
    # 2. Ініціалізація та запуск бота для вебхуків
    await bot_app.initialize()
    await bot_app.start() # Запускає внутрішні цикли Application
    
    # Перевірка, що Application має чергу для оновлень
    if not hasattr(bot_app, 'update_queue'):
        logger.error("bot_app has no update_queue attribute!")
        return
        
    # 3. Налаштування веб-сервера aiohttp
    aio_app = web.Application()
    aio_app['bot_app'] = bot_app # Зберігаємо Application у додатку aiohttp
    
    async def webhook_handler(request):
        """Обробник вхідних POST-запитів від Telegram."""
        bot_app = request.app['bot_app']
        # Отримання та десеріалізація оновлення з тіла запиту
        try:
            update = Update.de_json(await request.json(), bot_app.bot)
        except Exception as e:
            logger.error(f"Помилка десеріалізації оновлення: {e}")
            return web.Response(status=400)
            
        # Поміщення оновлення в чергу Application
        await bot_app.update_queue.put(update)
        return web.Response() # Telegram очікує 200 OK
    
    # Встановлення вебхука на сервері Telegram
    webhook_path = '/' + TELEGRAM_BOT_TOKEN
    full_webhook_url = WEBHOOK_URL.rstrip('/') + webhook_path
    
    await bot_app.bot.set_webhook(url=full_webhook_url)
    logger.info(f"Встановлено Webhook на: {full_webhook_url}")
    
    # 4. Налаштування маршрутів aiohttp
    aio_app.add_routes([
        web.get('/health', lambda r: web.Response(text='OK')), # Перевірка працездатності
        web.post(webhook_path, webhook_handler), # Обробник для Telegram
    ])

    # 5. Запуск веб-сервера
    runner = web.AppRunner(aio_app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    # '0.0.0.0' дозволяє слухати на всіх доступних інтерфейсах (важливо для Render)
    site = web.TCPSite(runner, '0.0.0.0', port) 
    logger.info(f"Starting web server on port {port}")
    await site.start()

    # Запобігання виходу головного циклу
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Error in main execution: {e}")