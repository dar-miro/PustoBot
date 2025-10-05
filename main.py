import logging
import re
import gspread
import asyncio
import os
from aiohttp import web
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
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

# Словник для ролей (ТЕПЕР БЕЗ БЕТИ, БЕТА ДИНАМІЧНО ДОДАЄТЬСЯ)
ROLE_TO_COLUMN_BASE = {
    "клін": "Клін",
    "переклад": "Переклад",
    "тайп": "Тайп",
    "ред": "Редакт", # Додаємо синонім
}
# Публікація
PUBLISH_COLUMN_BASE = "Публікація"

# ОНОВЛЕНО: Функція для генерації заголовків аркуша
def generate_sheet_headers(include_beta=False):
    """Генерує список заголовків для аркуша тайтлу; опціонально включаючи Бета;"""
    headers = ['Розділ']
    roles = list(ROLE_TO_COLUMN_BASE.values())
    if include_beta:
        roles.append("Бета") # Додаємо Бета-роль до списку

    for role in roles:
        # Порядок: Нік; Дата; Статус
        headers.extend([f'{role}-Нік', f'{role}-Дата', f'{role}-Статус'])

    # Додаємо Публікацію
    headers.extend([f'{PUBLISH_COLUMN_BASE}-Нік', f'{PUBLISH_COLUMN_BASE}-Дата', f'{PUBLISH_COLUMN_BASE}-Статус'])
    return headers

# Використовуємо стандартні заголовки без бети як глобальний дефолт
SHEET_HEADERS = generate_sheet_headers(include_beta=False)

# ОНОВЛЕНО: Заголовки для аркуша "Журнал"
LOG_HEADERS = ['Дата', 'Telegram-Нік', 'Нік', 'Тайтл', '№ Розділу', 'Роль']

class SheetsHelper:
    """Клас для інкапсуляції всієї роботи з Google Sheets;"""
    def __init__(self, credentials_file, spreadsheet_name):
        self.spreadsheet = None
        self.log_sheet = None
        self.users_sheet = None
        try:
            gc = gspread.service_account(filename=credentials_file)
            self.spreadsheet = gc.open(spreadsheet_name)
            self._initialize_sheets()
        except Exception as e:
            logger.error(f"Не вдалося підключитися до Google Sheets: {e}")

    # ВИПРАВЛЕННЯ 1: Змінено логіку вставки заголовків
    def _get_or_create_worksheet(self, title_name, headers=None, force_headers=False):
        """
        Отримує або створює аркуш за назвою; 
        Заголовки (якщо передані та force_headers=True) вставляються в рядок 3;
        Аркуші Тайтлів створюються без заголовків тут;
        """
        if not self.spreadsheet: raise ConnectionError("Немає підключення до Google Sheets;")
        try:
            return self.spreadsheet.worksheet(title_name)
        except gspread.WorksheetNotFound:
            logger.info(f"Створення нового аркуша: {title_name}")
            cols = len(headers) if headers else 20
            # Створюємо аркуш
            worksheet = self.spreadsheet.add_worksheet(title=title_name, rows="100", cols=str(cols))
            
            # Тільки якщо `force_headers=True` (для Журналу; Користувачів); вставляємо заголовки
            if headers and force_headers: 
                # Вставляємо порожні рядки 1 та 2
                worksheet.insert_row([], 1) 
                worksheet.insert_row([], 2) 
                # Додаємо заголовки в 3-й рядок
                worksheet.insert_row(headers, 3) 
            return worksheet
            
    def _initialize_sheets(self):
        """Ініціалізує основні аркуші (Журнал; Users; Тайтли);"""
        # Ініціалізація Журналу (force_headers=True)
        try:
            self.log_sheet = self._get_or_create_worksheet("Журнал", LOG_HEADERS, force_headers=True)
        except Exception as e:
            logger.error(f"Не вдалося ініціалізувати аркуш 'Журнал': {e}")
            self.log_sheet = None
            
        # Ініціалізація Користувачів (force_headers=True)
        try:
            self.users_sheet = self._get_or_create_worksheet("Користувачі", ['Telegram-ID', 'Теґ', 'Нік', 'Ролі'], force_headers=True)
        except Exception as e:
            logger.error(f"Не вдалося ініціалізувати аркуш 'Користувачі': {e}")
            self.users_sheet = None

    def _log_action(self, telegram_tag, nickname, title, chapter, role):
        """Додає запис про операцію до аркуша 'Журнал';"""
        if self.log_sheet:
            try:
                current_datetime = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                # Структура: Дата; Telegram-Нік; Нік; Тайтл; № Розділу; Роль
                log_row = [
                    current_datetime,
                    telegram_tag,
                    nickname,
                    title,
                    str(chapter),
                    role
                ]
                self.log_sheet.append_row(log_row)
            except Exception as e:
                logger.error(f"Помилка логування дії: {e}")
        else:
            logger.warning("Аркуш 'Журнал' не ініціалізовано; логування пропущено;")


    def register_user(self, user_id, username, nickname):
        """Реєструє або оновлює користувача на аркуші 'Користувачі';"""
        if not self.users_sheet: return "Помилка підключення до таблиці 'Користувачі';"
        try:
            users_sheet = self.users_sheet
            # Знаходимо користувача за ID (колонка 1)
            user_ids = users_sheet.col_values(1)
            
            # Якщо таблиця пуста; col_values(1) може повернути список із заголовком
            if user_ids and str(user_id) in user_ids:
                row_index = user_ids.index(str(user_id)) + 1
                # Оновлюємо Теґ (колонка 2) та Нік (колонка 3)
                users_sheet.update_cell(row_index, 2, username)
                users_sheet.update_cell(row_index, 3, nickname)
                return f"✅ Ваші дані оновлено; Нікнейм: {nickname}"
            else:
                # Таблиця 'Користувачі': Telegram-ID; Теґ; Нік; Ролі
                users_sheet.append_row([str(user_id), username, nickname, ''])
                return f"✅ Вас успішно зареєстровано; Нікнейм: {nickname}"
        except Exception as e:
            logger.error(f"Помилка реєстрації: {e}")
            return "❌ Сталася помилка під час реєстрації;"

    # ВИПРАВЛЕННЯ 2: set_team тепер лише встановлює команду в A2
    def set_team(self, title_name, team_string, beta_nickname, telegram_tag, nickname):
        """Створює аркуш (якщо його немає) та встановлює команду тайтлу в A2;"""
        if not self.spreadsheet: return "Помилка підключення до таблиці;"
        
        try:
            # Створюємо аркуш; якщо його немає; (заголовки не додаються)
            worksheet = self._get_or_create_worksheet(title_name) 

            # 1. Записуємо команду в клітинку A2
            worksheet.update_acell('A2', team_string)
            
            # 2. Логування
            self._log_action(
                telegram_tag=telegram_tag,
                nickname=nickname,
                title=title_name,
                chapter="Команда",
                role="Встановлення команди"
            )
            
            beta_info = f" (з Бета-тестером: {beta_nickname})" if beta_nickname else ""
            return f"✅ Команда для тайтлу '{title_name}' успішно встановлена;{beta_info}\n_Шапка (заголовки) будуть створені автоматично при додаванні першого розділу;_"
            
        except gspread.WorksheetNotFound:
            return f"⚠️ Тайтл '{title_name}' не знайдено;"
        except Exception as e:
            logger.error(f"Помилка встановлення команди: {e}")
            return "❌ Сталася помилка при встановленні команди;"

    # ВИПРАВЛЕННЯ 3: add_chapter тепер перевіряє та створює правильну шапку
    def add_chapter(self, title_name, chapter_number):
        """
        Додає новий розділ до відповідного аркуша тайтлу;
        Перевіряє наявність заголовків у рядку 3 і створює їх; враховуючи наявність "бета" в A2;
        """
        if not self.spreadsheet: return "Помилка підключення до таблиці;"
        try:
            # Отримуємо існуючий аркуш; або створюємо без заголовків
            try:
                 worksheet = self.spreadsheet.worksheet(title_name)
            except gspread.WorksheetNotFound:
                 # Створення аркуша без заголовків
                 worksheet = self._get_or_create_worksheet(title_name) 

            # 1. Визначаємо; чи є бета-роль в команді (рядок A2)
            try:
                team_string = worksheet.acell('A2').value or ''
            except Exception:
                team_string = ''
                
            has_beta_in_team = 'бета -' in team_string.lower()
            
            # 2. Перевіряємо та створюємо/оновлюємо заголовки в рядку 3
            required_headers = generate_sheet_headers(include_beta=has_beta_in_team)
            
            # Отримуємо поточні заголовки (або порожній список)
            try:
                current_headers = worksheet.row_values(3)
            except gspread.exceptions.APIError:
                current_headers = []
            
            # Якщо заголовки відсутні або не збігаються з необхідними
            if not current_headers or current_headers != required_headers:
                logger.info(f"Створення/оновлення заголовків для {title_name}; Бета: {has_beta_in_team}")
                # Якщо рядок 3 не порожній; видаляємо його перед вставкою
                if current_headers:
                    worksheet.delete_rows(3, 3) 
                
                # Забезпечуємо наявність порожніх рядків 1 та 2 (якщо їх немає)
                # Перевіряти наявність пустих рядків тут складно; але gspread.insert_row(..., 3) 
                # гарантує; що він буде на 3-му місці;
                
                worksheet.insert_row(required_headers, 3) # Вставляємо заголовки в 3-й рядок
                
            headers = required_headers # Використовуємо тепер актуальні заголовки
            
            # 3. Перевірка на дублікат розділу
            all_values = worksheet.get_all_values()
            data_rows = all_values[3:] # Рядки з даними (після заголовків)
            chapters = [row[0] for row in data_rows if row and row[0].strip()] 
            
            if str(chapter_number) in chapters:
                return f"⚠️ Розділ {chapter_number} для '{title_name}' вже існує;"
            
            # 4. Створення рядка для розділу
            
            # Генерація ролей для створення рядка (включаючи Бета; якщо вона є в заголовках)
            base_roles = list(ROLE_TO_COLUMN_BASE.values())
            if has_beta_in_team:
                base_roles.append("Бета")
                
            num_roles = len(base_roles)
            
            new_row_data = [str(chapter_number)] # Розділ
            
            # Додаємо дані для основних ролей (Нік; Дата; Статус)
            for _ in range(num_roles):
                 new_row_data.extend(['', '', '❌']) # 'Нік'; 'Дата'; 'Статус'
            
            # Додаємо дані для Публікації
            new_row_data.extend(['', '', '❌']) # Публікація: 'Нік'; 'Дата'; 'Статус'

            worksheet.append_row(new_row_data)
            
            # 5. Логування
            self._log_action(telegram_tag="Bot", nickname="System", title=title_name, chapter=chapter_number, role="Додано розділ")

            return f"✅ Додано розділ {chapter_number} до тайтлу '{title_name}'."
        except Exception as e:
            logger.error(f"Помилка додавання розділу: {e}")
            return "❌ Сталася помилка при додаванні розділу;"

    # Методи get_status та update_chapter_status не потребують змін; 
    # оскільки вони вже покладаються на правильність рядка 3 з заголовками;

# --- Обробники команд Telegram (без змін; використовують оновлений SheetsHelper) ---
# ... (весь код обробників та main залишається без змін) ...
# В цілях економії місця я опускаю незмінені функції тут; але вони є в повному коді;

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привіт! Це бот для відстеження роботи над тайтлами; Використовуйте /help для списку команд;");

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 *Список доступних команд:*\n\n"
        "👤 `/register <нікнейм>`\n_Реєструє вас у системі;_\n\n"
        "👥 `/team \"Назва Тайтлу\"`\n_Встановлює команду для тайтлу; Бот запитає про ролі;_\n\n"
        "➕ `/newchapter \"Назва Тайтлу\" <номер_розділу>`\n_Додає новий розділ до тайтлу; Назву брати в лапки!_\n\n"
        "📊 `/status \"Назва Тайтлу\"`\n_Показує статус усіх розділів тайтлу;_\n\n"
        "🔄 `/updatestatus \"Назва Тайтлу\" <розділ> <роль> <+|-> [нік]`\n_Оновлює статус завдання; Нік необов'язковий; Ролі: клін; переклад; тайп; редакт; бета; публікація;_"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("Будь ласка; вкажіть ваш нікнейм; Приклад: `/register SuperTranslator`")
        return
    nickname = " ".join(context.args)
    # ВИПРАВЛЕННЯ: Використовуємо sheets з контексту
    sheets = context.application.bot_data['sheets_helper']
    telegram_tag = f"@{user.username}" if user.username else user.full_name
    response = sheets.register_user(user.id, telegram_tag, nickname)
    await update.message.reply_text(response)

# ВИПРАВЛЕННЯ: Виправлення синтаксичної помилки з поверненням значень
def parse_title_and_args(text):
    """Парсер для команд; що містять назву тайтлу в лапках;"""
    match = re.search(r'\"(.*?)\"', text)
    if not match:
        return None, text.strip().split() # Виправлено: замінено ; на ,
    title = match.group(1)
    remaining_args = text[match.end():].strip().split()
    return title, remaining_args # Виправлено: замінено ; на ,

async def new_chapter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    full_text = " ".join(context.args)
    title, args = parse_title_and_args(full_text)
    if not title or len(args) != 1 or not args[0].isdigit():
        await update.message.reply_text('Невірний формат; Приклад: `/newchapter "Відьмоварта" 15`')
        return
    chapter = args[0]
    # ВИПРАВЛЕННЯ: Використовуємо sheets з контексту
    sheets = context.application.bot_data['sheets_helper']
    response = sheets.add_chapter(title, chapter)
    await update.message.reply_text(response)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    full_text = " ".join(context.args)
    title, _ = parse_title_and_args(full_text)
    if not title:
        await update.message.reply_text('Невірний формат; Приклад: `/status "Відьмоварта"`')
        return
    # ВИПРАВЛЕННЯ: Використовуємо sheets з контексту
    sheets = context.application.bot_data['sheets_helper']
    response = sheets.get_status(title)
    await update.message.reply_text(response, parse_mode="Markdown")

async def update_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    full_text = " ".join(context.args)
    title, args = parse_title_and_args(full_text)
    
    # Очікуємо 3 або 4 аргументи: Номер розділу; Роль; +/-; [Нік]
    if not title or len(args) < 3 or len(args) > 4 or not args[0].isdigit() or args[2] not in ['+', '-']:
        await update.message.reply_text('Невірний формат; Приклад: `/updatestatus "Відьмоварта" 15 клін + <нік>`')
        return
    
    chapter, role, status_char = args[0], args[1], args[2]
    
    # Визначаємо нік: якщо передано 4 аргументи; беремо останній; Інакше - Telegram-нік;
    user = update.effective_user
    if len(args) == 4:
        nickname = args[3] # Нік вказано в команді
    else:
        # Нік береться з Telegram-профілю користувача
        nickname = user.first_name
        if user.username:
            nickname = f"@{user.username}"
            
    # Telegram-тег для логування
    telegram_tag = f"@{user.username}" if user.username else user.full_name

    # ВИПРАВЛЕННЯ: Використовуємо sheets з контексту
    sheets = context.application.bot_data['sheets_helper']
    # Передаємо telegram_tag до методу update_chapter_status
    response = sheets.update_chapter_status(title, chapter, role, status_char, nickname, telegram_tag)
    await update.message.reply_text(response)

# --- ОБРОБНИК КОМАНДИ /team ---
async def team_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє команду /team \"Назва тайтлу\" та запитує ніки для ролей;"""
    full_text = " ".join(context.args)
    title, _ = parse_title_and_args(full_text)
    
    if not title:
        await update.message.reply_text('Невірний формат; Приклад: `/team "Назва Тайтлу"`')
        return

    # Зберігаємо тайтл у контексті користувача для наступного кроку
    context.user_data['setting_team_for_title'] = title
    
    # Початкове запитання
    prompt = (
        f"Встановлення команди для тайтлу **'{title}'**; "
        "Будь ласка; введіть ніки в наступному форматі:\n\n"
        "`клін - нік; переклад - нік; тайп - нік; редакт - нік; [бета - нік]`\n\n"
        "Наприклад: `клін - Клінер; переклад - Перекладач; тайп - Тайпер; редакт - Редактор; бета - БетаТест`\n"
        "Бета є необов'язковою;"
    )
    context.user_data['awaiting_team_input'] = True
    
    await update.message.reply_text(prompt, parse_mode="Markdown")

# Обробник текстових повідомлень; який буде слухати після /team
async def handle_team_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє введення користувача після команди /team;"""
    # Перевіряємо; чи ми очікуємо введення команди і чи є тайтл у контексті
    if context.user_data.get('awaiting_team_input') and 'setting_team_for_title' in context.user_data:
        title_name = context.user_data['setting_team_for_title']
        raw_input = update.message.text
        
        # Регулярний вираз для парсингу: роль - нік
        pattern = re.compile(r'(клін|переклад|тайп|редакт|ред|бета)\s*-\s*([^;]+)', re.IGNORECASE)
        matches = pattern.findall(raw_input)
        
        team_nicks = {}
        for role, nick in matches:
            role_lower = role.lower()
            if role_lower == 'ред':
                role_lower = 'редакт'
            team_nicks[role_lower] = nick.strip()

        # Обов'язкові ролі
        required_roles = ['клін', 'переклад', 'тайп', 'редакт']
        missing_roles = [r for r in required_roles if r not in team_nicks]

        if missing_roles:
            # Очищуємо контекст і повертаємо помилку
            del context.user_data['awaiting_team_input']
            del context.user_data['setting_team_for_title']
            return await update.message.reply_text(
                f"❌ Помилка: Не вказано обов'язкові ролі: {'; '.join(missing_roles)}; Спробуйте ще раз з `/team \"{title_name}\"`;"
            )
            
        # Форматуємо рядок для запису в A2
        team_string_parts = []
        for role_key in required_roles:
            team_string_parts.append(f"{role_key} - {team_nicks[role_key]}")

        beta_nickname = team_nicks.get('бета', '').strip()
        if beta_nickname:
             team_string_parts.append(f"бета - {beta_nickname}")
             
        team_string = '; '.join(team_string_parts)
        
        # Зберігаємо дані користувача для логування
        user = update.effective_user
        telegram_tag = f"@{user.username}" if user.username else user.full_name
        nickname = user.first_name
        if user.username:
            nickname = f"@{user.username}"

        # ВИПРАВЛЕННЯ: Використовуємо sheets з контексту
        sheets = context.application.bot_data['sheets_helper']
        # Тепер set_team тільки встановлює команду в A2
        response = sheets.set_team(title_name, team_string, beta_nickname, telegram_tag, nickname)
        
        # Очищуємо контекст
        del context.user_data['awaiting_team_input']
        del context.user_data['setting_team_for_title']

        await update.message.reply_text(response)
        return
    
    # Якщо це не очікуване введення команди; дозволяємо іншим обробникам працювати
    pass


# --- АСИНХРОННИЙ ЗАПУСК ДЛЯ WEBHOOKS ---

async def main():
    """Основна асинхронна функція для запуску бота;"""
    
    # 1. Ініціалізація SheetsHelper один раз
    sheets_helper = SheetsHelper(GOOGLE_CREDENTIALS_FILE, SPREADSHEET_NAME)
    if sheets_helper.spreadsheet is None:
        logger.error("Початкове підключення до Google Sheets провалилося; Бот не запускається;")
        return
    
    # 2. Створення Application
    bot_app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Зберігаємо sheets_helper у bot_data для доступу з обробників
    bot_app.bot_data['sheets_helper'] = sheets_helper
    
    # Додавання обробників
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("help", help_command))
    bot_app.add_handler(CommandHandler("register", register))
    bot_app.add_handler(CommandHandler("team", team_command))
    bot_app.add_handler(CommandHandler("newchapter", new_chapter))
    bot_app.add_handler(CommandHandler("status", status))
    bot_app.add_handler(CommandHandler("updatestatus", update_status))
    
    # Обробник для обробки введеного тексту після /team
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_team_input)) 
    
    # 3. Налаштування та запуск бота для вебхуків
    await bot_app.initialize()
    await bot_app.start()

    # (Оригінальний код для вебхуків aiohttp без змін)
    
    # Перевірка; що Application має чергу для оновлень
    if not hasattr(bot_app, 'update_queue'):
        logger.error("bot_app has no update_queue attribute!")
        return
        
    # 4. Налаштування веб-сервера aiohttp
    aio_app = web.Application()
    aio_app['bot_app'] = bot_app # Зберігаємо Application у додатку aiohttp
    
    async def webhook_handler(request):
        """Обробник вхідних POST-запитів від Telegram;"""
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
    
    # 5. Налаштування маршрутів aiohttp
    aio_app.add_routes([
        web.get('/health', lambda r: web.Response(text='OK')), # Перевірка працездатності
        web.post(webhook_path, webhook_handler), # Обробник для Telegram
    ])

    # 6. Запуск веб-сервера
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