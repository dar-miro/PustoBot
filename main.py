import logging
import re
import gspread
import asyncio
import os
import sys
import json
from aiohttp import web
from datetime import datetime
import gspread.utils
from telegram import Update, WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from typing import List, Tuple

# Конфігурація
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
GOOGLE_CREDENTIALS_FILE = os.environ.get("GOOGLE_CREDENTIALS_FILE", 'credentials.json')
SPREADSHEET_KEY = os.environ.get("SPREADSHEET_KEY")

WEB_APP_ENTRYPOINT = "/miniapp" 

# Налаштування логування
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Словник для ролей
ROLE_TO_COLUMN_BASE = {
    "клін": "Клін",
    "переклад": "Переклад",
    "тайп": "Тайп",
    "ред": "Редакт",
}
PUBLISH_COLUMN_BASE = "Публікація"

# Шаблон для парсингу команди /updatestatus "Тайтл" <№ Розділу> <Роль> <Дата YYYY-MM-DD> <+>
UPDATE_STATUS_PATTERN = re.compile(r'/updatestatus \"(.+?)\"\s+([\d\.]+)\s+(клін|переклад|тайп|ред)\s+([\d]{4}-[\d]{2}-[\d]{2})\s+\+')

# ==============================================================================
# HTTP ОБРОБНИКИ (AIOHTTP)
# ==============================================================================

async def miniapp(request: web.Request):
    """Віддає головну сторінку Mini App."""
    return web.FileResponse("webapp/index.html")

async def webhook_handler(request: web.Request):
    """Обробляє вхідні запити webhook від Telegram."""
    update = Update.de_json(await request.json(), request.app['bot_app'].bot)
    asyncio.create_task(request.app['bot_app'].process_update(update))
    return web.Response()

# ==============================================================================
# GOOGLE SHEETS HELPER
# ==============================================================================

class SheetsHelper:
    def __init__(self, spreadsheet_key):
        self.spreadsheet_key = spreadsheet_key
        self.gc = None
        self.spreadsheet = None
        self.users_cache = {}
        asyncio.create_task(self._authorize_and_connect())

    async def _authorize_and_connect(self):
        """Авторизація та підключення до таблиці."""
        try:
            if os.path.exists(GOOGLE_CREDENTIALS_FILE):
                self.gc = gspread.service_account(filename=GOOGLE_CREDENTIALS_FILE)
            else:
                logger.error("Файл Google Credentials не знайдено.")
                sys.exit(1)
                
            self.spreadsheet = self.gc.open_by_key(self.spreadsheet_key)
            logger.info("Підключення до Google Sheets успішне.")
            self._load_users_cache()
            
        except Exception as e:
            logger.error(f"Помилка підключення до Google Sheets: {e}")
            self.spreadsheet = None

    def _load_users_cache(self):
        """Завантажує ID користувачів та їхні нікнейми з аркуша Користувачі."""
        if not self.spreadsheet: return
        try:
            # ✅ Виправлення: Використання аркуша "Користувачі"
            users_ws = self.spreadsheet.worksheet("Користувачі")
            records = users_ws.get_all_records()
            self.users_cache = {
                int(record['Telegram ID']): record['Нік']
                for record in records if 'Telegram ID' in record and 'Нік' in record and str(record['Telegram ID']).isdigit()
            }
            logger.info(f"Завантажено {len(self.users_cache)} користувачів у кеш.")
        except gspread.WorksheetNotFound:
            logger.error("Аркуш 'Користувачі' не знайдено. Реєстрація користувачів неможлива.")
        except Exception as e:
            logger.error(f"Помилка завантаження кешу користувачів: {e}")

    def get_nickname_by_id(self, user_id: int) -> str | None:
        """Повертає нікнейм за ID користувача."""
        return self.users_cache.get(user_id)
    
    def _log_action(self, telegram_tag, nickname, title, chapter, role):
        """Логує дію користувача в аркуші LOG (за бажанням)."""
        if not self.spreadsheet: return
        try:
            log_ws = self.spreadsheet.worksheet("LOG")
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_ws.append_row([
                now, telegram_tag, nickname, title, chapter, role, "UPDATE"
            ])
        except Exception as e:
            logger.error(f"Помилка при логуванні дії: {e}")

    def update_chapter_status(self, title_name: str, chapter_number: str, role_key: str, date: str, status_symbol: str, nickname: str, telegram_tag: str) -> str:
        """Оновлює статус глави для певної ролі."""
        if not self.spreadsheet: 
            raise ConnectionError("Немає підключення до Google Sheets.")

        # 1. Знаходимо робочий аркуш
        try:
            worksheet = self.spreadsheet.worksheet(title_name)
        except gspread.WorksheetNotFound:
            return f"❌ Помилка: Тайтл '{title_name}' не знайдено в таблиці."
        
        # 2. Знаходимо рядок розділу
        try:
            chapters = worksheet.col_values(1) 
            if str(chapter_number) not in chapters[3:]: 
                return f"❌ Помилка: Розділ {chapter_number} не знайдено. Створіть його спочатку."

            row_index = chapters.index(str(chapter_number)) + 1
        except Exception as e:
            logger.error(f"Помилка при пошуку розділу {chapter_number}: {e}")
            return f"❌ Помилка при пошуку розділу {chapter_number}."
        
        # 3. Визначаємо колонки для оновлення
        role_base = ROLE_TO_COLUMN_BASE.get(role_key) 
        if not role_base:
            return f"❌ Помилка: Невідома роль: {role_key}."

        headers = worksheet.row_values(3) 
        
        col_name_nick = f'{role_base}-Нік'
        col_name_date = f'{role_base}-Дата'
        col_name_status = f'{role_base}-Статус'

        try:
            col_index_nick = headers.index(col_name_nick) + 1
            col_index_date = headers.index(col_name_date) + 1
            col_index_status = headers.index(col_name_status) + 1

        except ValueError:
            return f"❌ Помилка: Аркуш '{title_name}' не містить потрібних заголовків для ролі '{role_base}'."

        # 4. Оновлення даних (пакетне оновлення)
        updates = []
        updates.append({'range': gspread.utils.rowcol_to_a1(row_index, col_index_nick), 'values': [[nickname]]})
        updates.append({'range': gspread.utils.rowcol_to_a1(row_index, col_index_date), 'values': [[date]]})
        updates.append({'range': gspread.utils.rowcol_to_a1(row_index, col_index_status), 'values': [[status_symbol]]})
        
        worksheet.batch_update(updates)
        
        # 5. Логування дії
        self._log_action(
            telegram_tag=telegram_tag,
            nickname=nickname,
            title=title_name,
            chapter=chapter_number,
            role=role_base
        )
        
        return f"✅ Статус оновлено: {title_name} - Розділ {chapter_number} ({role_base}) встановлено на {status_symbol} ({nickname})."

# ==============================================================================
# TELEGRAM БОТ: ОБРОБНИКИ КОМАНД ТА ДАНИХ
# ==============================================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обробляє команду /start."""
    user = update.effective_user
    
    # Доступ до sheets_helper
    sheets_helper = context.application.data.get('sheets_helper')
    nickname = sheets_helper.get_nickname_by_id(user.id) if sheets_helper else None
    
    if not nickname:
        message = (
            f"Привіт, {user.first_name}! 👋\n"
            "Щоб користуватися ботом, вам потрібно зареєструватись.\n"
            "Використайте команду /register <Ваш Нік> для реєстрації."
        )
        await update.message.reply_text(message)
        return

    # Кнопка Mini App
    keyboard = [[
        InlineKeyboardButton(
            "📝 Оновити Статус", 
            web_app=WebAppInfo(url=WEBHOOK_URL.replace("/webhook", WEB_APP_ENTRYPOINT))
        )
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"Вітаю, {nickname}!\nВаш статус: Зареєстрований.\nОберіть дію:", 
        reply_markup=reply_markup
    )

async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обробляє дані, надіслані з Mini App через sendData()."""
    user = update.effective_user
    data = update.effective_message.web_app_data.data 
    
    logger.info(f"Отримано дані Mini App від {user.username} ({user.id}): {data}")

    match = UPDATE_STATUS_PATTERN.match(data)
    
    if match:
        await update_status_command(update, context, match.groups())
    else:
        error_message = f"❌ Помилка парсингу команди Mini App. Перевірте формат. Отримано: `{data}`"
        await update.effective_message.reply_text(error_message)
        logger.warning(f"Помилка парсингу Mini App: {data}")
        
async def update_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE, args: Tuple[str, str, str, str, str]) -> None:
    """Виконує логіку оновлення статусу в Google Sheets."""
    
    title, chapter, role_key, date, status = args

    user = update.effective_user
    # Доступ до sheets_helper
    sheets_helper = context.application.data.get('sheets_helper')

    if not sheets_helper:
        await update.effective_message.reply_text("❌ Помилка: Сервіс Google Sheets недоступний.")
        return

    nickname = sheets_helper.get_nickname_by_id(user.id)
    if not nickname:
        await update.effective_message.reply_text(f"❌ Помилка: Ваш Telegram ID ({user.id}) не зареєстровано. Використовуйте /register.")
        return
        
    try:
        result_message = sheets_helper.update_chapter_status(
            title_name=title,
            chapter_number=chapter,
            role_key=role_key,
            date=date,
            status_symbol=status, 
            nickname=nickname,
            telegram_tag=f"@{user.username}" if user.username else str(user.id)
        )
        await update.effective_message.reply_text(result_message)
    except Exception as e:
        logger.error(f"Помилка при оновленні статусу: {e}")
        await update.effective_message.reply_text(f"❌ Помилка при оновленні статусу в таблиці: {e}")

# ==============================================================================
# ЗАПУСК БОТА
# ==============================================================================

async def run_bot():
    """Основна функція для запуску бота та веб-сервера aiohttp."""
    if not TELEGRAM_BOT_TOKEN or not WEBHOOK_URL or not SPREADSHEET_KEY:
        logger.error("Відсутні необхідні змінні середовища (TOKEN, WEBHOOK_URL, SPREADSHEET_KEY).")
        return

    # 1. Створення об'єкта SheetsHelper
    sheets_helper = SheetsHelper(SPREADSHEET_KEY)

    # 2. Створення застосунку Telegram
    # ✅ ВИПРАВЛЕННЯ: Використовуємо .build().application.data для сумісності з різними версіями PTB
    bot_app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    # Присвоюємо дані після .build() (найбільш універсальний спосіб)
    bot_app.application.data['sheets_helper'] = sheets_helper 
    
    # 3. Налаштування webhook
    parsed_url = web.URL(WEBHOOK_URL)
    webhook_path = parsed_url.path
    full_webhook_url = str(parsed_url.with_path(webhook_path))
    
    await bot_app.bot.set_webhook(url=full_webhook_url)
    logger.info(f"Встановлено Webhook на: {full_webhook_url}")
    
    # 4. Налаштування обробників
    bot_app.add_handler(CommandHandler("start", start_command))
    
    bot_app.add_handler(
        MessageHandler(
            filters.TEXT 
            & ~filters.COMMAND 
            & filters.UpdateType.WEB_APP_DATA, 
            web_app_data_handler
        )
    )

    # 5. Налаштування маршрутів aiohttp
    aio_app = web.Application()
    aio_app['bot_app'] = bot_app 
    aio_app.add_routes([
        web.get('/health', lambda r: web.Response(text='OK')), 
        web.post(webhook_path, webhook_handler), 
        
        # --- МАРШРУТИЗАЦІЯ ДЛЯ МІНІ-ЗАСТОСУНКУ ---
        web.get(WEB_APP_ENTRYPOINT, miniapp), 
        web.static(WEB_APP_ENTRYPOINT, path='webapp', name='static') 
    ])    

    # 6. Запуск веб-сервера
    runner = web.AppRunner(aio_app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    logger.info(f"Starting web server on port {port}")
    await site.start()

    # Запобігання виходу головного циклу asyncio
    await asyncio.Event().wait()

if __name__ == '__main__':
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually.")
    except Exception as e:
        logger.error(f"Fatal error in main loop: {e}")