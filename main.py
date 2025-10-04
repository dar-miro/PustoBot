import logging
import re
import gspread
import asyncio
import os
from aiohttp import web
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from datetime import datetime

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

# Словник для ролей
ROLE_TO_COLUMN_BASE = {
    "клін": "Клін",
    "переклад": "Переклад",
    "тайп": "Тайп",
    "редакт": "Редакт",
    "ред": "Редакт", # Додаємо синонім
}
# Публікація
PUBLISH_COLUMN_BASE = "Публікація"

# ОНОВЛЕНО: Нова структура заголовків
# Структура: [Розділ, Клін-Нік, Клін-Дата, Клін-Статус, Переклад-Нік, Переклад-Дата, Переклад-Статус, ...]
SHEET_HEADERS = ['Розділ']

# Додаємо Нік/Дата/Статус для кожної ролі
for role in ROLE_TO_COLUMN_BASE.values():
    # Порядок: Нік, Дата, Статус
    SHEET_HEADERS.extend([f'{role}-Нік', f'{role}-Дата', f'{role}-Статус'])

# Додаємо Публікацію
SHEET_HEADERS.extend([f'{PUBLISH_COLUMN_BASE}-Нік', f'{PUBLISH_COLUMN_BASE}-Дата', f'{PUBLISH_COLUMN_BASE}-Статус'])

# Фінальна структура (приклад): ['Розділ', 'Клін-Нік', 'Клін-Дата', 'Клін-Статус', 'Переклад-Нік', 'Переклад-Дата', 'Переклад-Статус', ...]


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
            # Встановлюємо кількість колонок відповідно до нової структури
            worksheet = self.spreadsheet.add_worksheet(title=title_name, rows="100", cols=str(len(SHEET_HEADERS) + 2)) 
            worksheet.append_row(SHEET_HEADERS)
            return worksheet

    def register_user(self, user_id, username, nickname):
        """Реєструє або оновлює користувача на аркуші 'Users'."""
        if not self.spreadsheet: return "Помилка підключення до таблиці."
        try:
            users_sheet = self.spreadsheet.worksheet("Users")
            # Знаходимо користувача за ID (колонка 1)
            user_ids = users_sheet.col_values(1)
            
            # Якщо таблиця пуста, col_values(1) може повернути список із заголовком
            if user_ids and str(user_id) in user_ids:
                row_index = user_ids.index(str(user_id)) + 1
                # Оновлюємо Теґ (колонка 2) та Нік (колонка 3)
                users_sheet.update_cell(row_index, 2, username)
                users_sheet.update_cell(row_index, 3, nickname)
                return f"✅ Ваші дані оновлено. Нікнейм: {nickname}"
            else:
                # Таблиця 'Користувачі': Telegram-нік (ID), Теґ, Нік, Ролі
                users_sheet.append_row([str(user_id), username, nickname, '']) 
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
            
            # Створюємо рядок: Розділ, потім для кожної ролі [Нік, Дата, Статус='❌']
            new_row_data = [str(chapter_number)] # Розділ
            
            for _ in ROLE_TO_COLUMN_BASE:
                 new_row_data.extend(['', '', '❌']) # 'Нік', 'Дата', 'Статус'
            
            new_row_data.extend(['', '', '❌']) # Публікація: 'Нік', 'Дата', 'Статус'

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
            all_values = worksheet.get_all_values()
            if len(all_values) <= 1:
                 return f"📊 Для тайтлу '{title_name}' ще немає жодного розділу."
            
            headers = all_values[0]
            records = all_values[1:]

            response = [f"📊 *Статус тайтлу '{title_name}':*\n"]
            
            # Індекс колонки розділу
            chapter_index = headers.index('Розділ')

            # Список для обробки основних ролей та публікації
            role_definitions = list(ROLE_TO_COLUMN_BASE.items()) + [("публікація", PUBLISH_COLUMN_BASE)]

            for row in records:
                chapter = row[chapter_index]
                statuses = []
                
                for role_key, role_base_name in role_definitions:
                    # Пошук колонок для Нік/Дата/Статус
                    nick_col_name = f'{role_base_name}-Нік'
                    date_col_name = f'{role_base_name}-Дата'
                    status_col_name = f'{role_base_name}-Статус'
                    
                    try:
                        nick_index = headers.index(nick_col_name)
                        date_index = headers.index(date_col_name)
                        status_index = headers.index(status_col_name)
                        
                        nick_value = row[nick_index].strip()
                        date_value = row[date_index].strip()
                        status_value = row[status_index].strip()
                        
                        status_char = "✅" if status_value == '✅' else "❌"
                        info = []
                        if nick_value:
                            info.append(nick_value)
                        if date_value:
                            info.append(date_value)
                        
                        info_str = f" ({' | '.join(info)})" if info else ""
                        
                        statuses.append(f"*{role_key}*: {status_char}{info_str}")
                    except ValueError:
                        statuses.append(f"*{role_key}*: ⚠️ (Помилка заголовка)") 

                response.append(f"*{chapter}* — _{' | '.join(statuses)}_")
            return "\n".join(response)
        except gspread.WorksheetNotFound:
            return f"⚠️ Тайтл '{title_name}' не знайдено."
        except Exception as e:
            logger.error(f"Помилка отримання статусу: {e}")
            return "❌ Сталася помилка при отриманні статусу."

    def update_chapter_status(self, title_name, chapter_number, role, status_char, nickname):
        """Оновлює статус, дату та нік для конкретної ролі."""
        if not self.spreadsheet: return "Помилка підключення до таблиці."
        
        role_lower = role.lower()
        role_base_name = None
        
        if role_lower == 'публікація':
            role_base_name = PUBLISH_COLUMN_BASE
        elif role_lower in ROLE_TO_COLUMN_BASE:
            role_base_name = ROLE_TO_COLUMN_BASE[role_lower]
        else:
            return f"⚠️ Невідома роль '{role}'. Доступні: {', '.join(ROLE_TO_COLUMN_BASE.keys())}, публікація"
            
        try:
            worksheet = self.spreadsheet.worksheet(title_name)
            
            # Пошук рядка за номером розділу
            cell = worksheet.find(str(chapter_number), in_column=1) 
            if not cell:
                return f"⚠️ Розділ {chapter_number} не знайдено в тайтлі '{title_name}'."
            
            headers = worksheet.row_values(1)
            row_index = cell.row
            
            new_status_char = '✅' if status_char == '+' else '❌'
            current_date = datetime.now().strftime("%d.%m")
            
            # Пошук індексів колонок для цієї ролі
            nick_col_name = f'{role_base_name}-Нік'
            date_col_name = f'{role_base_name}-Дата'
            status_col_name = f'{role_base_name}-Статус'

            # Перевірка наявності всіх трьох колонок
            if not all(col in headers for col in [nick_col_name, date_col_name, status_col_name]):
                return f"❌ Помилка: Не знайдено всі колонки для ролі '{role_base_name}'. Перевірте заголовки таблиці."
            
            nick_index = headers.index(nick_col_name) + 1
            date_index = headers.index(date_col_name) + 1
            status_index = headers.index(status_col_name) + 1
            
            # 1. Оновлюємо статус
            worksheet.update_cell(row_index, status_index, new_status_char)
            
            # 2. Оновлюємо Нік та Дату
            if status_char == '+':
                worksheet.update_cell(row_index, date_index, current_date)
                worksheet.update_cell(row_index, nick_index, nickname)
            else:
                # Якщо статус скидається ('-'), очищуємо Нік та Дату
                worksheet.update_cell(row_index, date_index, '')
                worksheet.update_cell(row_index, nick_index, '')

            return f"✅ Статус оновлено: '{title_name}', розділ {chapter_number}, роль {role_lower} → {status_char} (Виконавець: {nickname})"
        
        except gspread.WorksheetNotFound:
            return f"⚠️ Тайтл '{title_name}' не знайдено."
        except ValueError as ve: 
            logger.error(f"Помилка індексування колонки: {ve}")
            return f"❌ Помилка: Не знайдена колонка. Перевірте заголовки таблиці: {ve}"
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
        "🔄 `/updatestatus \"Назва Тайтлу\" <розділ> <роль> <+|-> [нік]`\n_Оновлює статус завдання. Нік необов'язковий. Ролі: клін, переклад, тайп, редакт, публікація._"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Будь ласка, вкажіть ваш нікнейм. Приклад: `/register SuperTranslator`")
        return
    nickname = " ".join(context.args)
    sheets = SheetsHelper(GOOGLE_CREDENTIALS_FILE, SPREADSHEET_NAME)
    # Telegram-тег беремо з username, якщо є, або з імені
    telegram_tag = f"@{user.username}" if user.username else user.full_name
    response = sheets.register_user(user.id, telegram_tag, nickname)
    await update.message.reply_text(response)

def parse_title_and_args(text):
    """Парсер для команд, що містять назву тайтлу в лапках."""
    match = re.search(r'\"(.*?)\"', text)
    if not match:
        return None, text.strip().split() # Якщо лапок немає, назви тайтлу теж немає
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
    
    # Очікуємо 3 або 4 аргументи: Номер розділу, Роль, +/-, [Нік]
    if not title or len(args) < 3 or len(args) > 4 or not args[0].isdigit() or args[2] not in ['+', '-']:
        await update.message.reply_text('Невірний формат. Приклад: `/updatestatus "Відьмоварта" 15 клін + <нік>`')
        return
    
    chapter, role, status_char = args[0], args[1], args[2]
    
    # Визначаємо нік: якщо передано 4 аргументи, беремо останній. Інакше - Telegram-нік.
    if len(args) == 4:
        nickname = args[3] # Нік вказано в команді
    else:
        # Нік береться з Telegram-профілю користувача
        nickname = update.effective_user.first_name 
        if update.effective_user.username:
            nickname = f"@{update.effective_user.username}"

    sheets = SheetsHelper(GOOGLE_CREDENTIALS_FILE, SPREADSHEET_NAME)
    response = sheets.update_chapter_status(title, chapter, role, status_char, nickname)
    await update.message.reply_text(response)


# --- АСИНХРОННИЙ ЗАПУСК ДЛЯ WEBHOOKS ---

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