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
from yarl import URL

# Конфігурація
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
GOOGLE_CREDENTIALS_FILE = os.environ.get("GOOGLE_CREDENTIALS_FILE", "credentials.json")
SPREADSHEET_KEY = os.environ.get("SPREADSHEET_KEY")

WEB_APP_ENTRYPOINT = "/miniapp"

# Налаштування логування
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Словник для ролей
ROLE_TO_COLUMN_BASE = {
    "клін": "Клін",
    "переклад": "Переклад",
    "тайп": "Тайп",
    "ред": "Редакт",
}
PUBLISH_COLUMN_BASE = "Публікація"

# Шаблон для парсингу команди (legacy)
UPDATE_STATUS_PATTERN = re.compile(r'/updatestatus \"(.+?)\"\s+([\d\.]+)\s+(клін|переклад|тайп|ред)\s+([\d]{4}-[\d]{2}-[\d]{2})\s+\+')


# ============================================================================== #
# HTTP ОБРОБНИКИ (AIOHTTP)
# ============================================================================== #

async def miniapp(request: web.Request):
    """Віддає головну сторінку Mini App."""
    # Припускаємо, що файл index.html знаходиться у теці webapp
    index_path = os.path.join("webapp", "index.html")
    if not os.path.exists(index_path):
        return web.Response(status=404, text="Mini App not found.")
    return web.FileResponse(index_path)


async def webhook_handler(request: web.Request):
    """Обробляє вхідні запити webhook від Telegram."""
    try:
        data = await request.json()
        application = request.app["bot_app"]
        update = Update.de_json(data, application.bot)
        # Кладемо update в чергу обробки застосунку
        await application.update_queue.put(update)
        return web.Response(status=200)
    except Exception as e:
        logger.exception(f"Помилка в обробнику вебхука: {e}")
        return web.Response(status=500)


# ============================================================================== #
# GOOGLE SHEETS HELPER
# ============================================================================== #

class SheetsHelper:
    def __init__(self, spreadsheet_key: str):
        self.spreadsheet_key = spreadsheet_key
        self.gc = None
        self.spreadsheet = None
        self.users_cache: dict[int, str] = {}
        # Запускаємо авторизацію у фоновому таску (будьте впевнені, що event loop вже є)
        try:
            asyncio.create_task(self._authorize_and_connect())
        except RuntimeError:
            # Якщо немає глобального loop (наприклад, при імпорті), просто пропустимо:
            logger.warning("Event loop not running when SheetsHelper created — відкладене підключення може не стартувати.")

    async def _authorize_and_connect(self):
        """Авторизація та підключення до таблиці."""
        try:
            if os.path.exists(GOOGLE_CREDENTIALS_FILE):
                self.gc = gspread.service_account(filename=GOOGLE_CREDENTIALS_FILE)
            else:
                logger.error("Файл Google Credentials не знайдено.")
                return

            self.spreadsheet = self.gc.open_by_key(self.spreadsheet_key)
            logger.info("Підключення до Google Sheets успішне.")
            self._load_users_cache()

        except Exception as e:
            logger.exception(f"Помилка підключення до Google Sheets: {e}")
            self.spreadsheet = None

    def _load_users_cache(self):
        """Завантажує ID користувачів та їхні нікнейми з аркуша 'Користувачі'."""
        if not self.spreadsheet:
            return
        try:
            users_ws = self.spreadsheet.worksheet("Користувачі")
            records = users_ws.get_all_records()
            self.users_cache = {
                int(record["Telegram ID"]): record["Нік"]
                for record in records
                if "Telegram ID" in record and "Нік" in record and str(record["Telegram ID"]).isdigit()
            }
            logger.info(f"Завантажено {len(self.users_cache)} користувачів у кеш.")
        except gspread.WorksheetNotFound:
            logger.error("Аркуш 'Користувачі' не знайдено. Реєстрація користувачів неможлива.")
        except Exception as e:
            logger.exception(f"Помилка завантаження кешу користувачів: {e}")

    def get_nickname_by_id(self, user_id: int) -> str | None:
        """Повертає нікнейм за ID користувача."""
        return self.users_cache.get(user_id)

    def _log_action(self, telegram_tag, nickname, title, chapter, role):
        """Логує дію користувача в аркуші LOG (за бажанням)."""
        if not self.spreadsheet:
            return
        try:
            log_ws = self.spreadsheet.worksheet("LOG")
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_ws.append_row([now, telegram_tag, nickname, title, chapter, role, "UPDATE"])
        except Exception as e:
            logger.exception(f"Помилка при логуванні дії: {e}")

    def update_chapter_status(
        self, title_name: str, chapter_number: str, role_key: str, date: str, status_symbol: str, nickname: str, telegram_tag: str
    ) -> str:
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
            # припускаємо, що в колонці 1 знаходяться номери розділів десь починаючи з індексу 3
            if str(chapter_number) not in chapters:
                return f"❌ Помилка: Розділ {chapter_number} не знайдено. Створіть його спочатку."

            row_index = chapters.index(str(chapter_number)) + 1
        except Exception as e:
            logger.exception(f"Помилка при пошуку розділу {chapter_number}: {e}")
            return f"❌ Помилка при пошуку розділу {chapter_number}."

        # 3. Визначаємо колонки для оновлення
        role_base = ROLE_TO_COLUMN_BASE.get(role_key)
        if not role_base:
            return f"❌ Помилка: Невідома роль: {role_key}."

        headers = worksheet.row_values(3)

        col_name_nick = f"{role_base}-Нік"
        col_name_date = f"{role_base}-Дата"
        col_name_status = f"{role_base}-Статус"

        try:
            col_index_nick = headers.index(col_name_nick) + 1
            col_index_date = headers.index(col_name_date) + 1
            col_index_status = headers.index(col_name_status) + 1
        except ValueError:
            return f"❌ Помилка: Аркуш '{title_name}' не містить потрібних заголовків для ролі '{role_base}'."

        # 4. Оновлення даних (пакетне оновлення)
        updates = []
        updates.append({"range": gspread.utils.rowcol_to_a1(row_index, col_index_nick), "values": [[nickname]]})
        updates.append({"range": gspread.utils.rowcol_to_a1(row_index, col_index_date), "values": [[date]]})
        updates.append({"range": gspread.utils.rowcol_to_a1(row_index, col_index_status), "values": [[status_symbol]]})

        worksheet.batch_update(updates)

        # 5. Логування дії
        self._log_action(
            telegram_tag=telegram_tag,
            nickname=nickname,
            title=title_name,
            chapter=chapter_number,
            role=role_base,
        )

        return f"✅ Статус оновлено: {title_name} - Розділ {chapter_number} ({role_base}) встановлено на {status_symbol} ({nickname})."


# ============================================================================== #
# TELEGRAM БОТ: ОБРОБНИКИ КОМАНД ТА ДАНИХ
# ============================================================================== #


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обробляє команду /start."""
    user = update.effective_user

    sheets_helper: SheetsHelper | None = context.application.bot_data.get("sheets_helper")
    nickname = sheets_helper.get_nickname_by_id(user.id) if sheets_helper else None

    if not nickname:
        message = (
            f"Привіт, {user.first_name}! 👋\n"
            "Щоб користуватися ботом, вам потрібно зареєструватись.\n"
            "Використайте команду /register <Ваш Нік> для реєстрації."
        )
        if update.effective_message:
            await update.effective_message.reply_text(message)
        return

    # Кнопка Mini App — формуємо абсолютну URL до miniapp
    if WEBHOOK_URL:
        parsed = URL(WEBHOOK_URL)
        base = f"{parsed.scheme}://{parsed.host}"
        if parsed.port:
            base += f":{parsed.port}"
        miniapp_url = base.rstrip("/") + WEB_APP_ENTRYPOINT
    else:
        miniapp_url = WEB_APP_ENTRYPOINT

    keyboard = [
        [
            InlineKeyboardButton("📝 Оновити Статус", web_app=WebAppInfo(url=miniapp_url)),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.effective_message.reply_text(
        f"Вітаю, {nickname}!\nВаш статус: Зареєстрований.\nОберіть дію:", reply_markup=reply_markup
    )


async def web_app_data_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    ОБРОБКА JSON-ДАНИХ, надісланих з Mini App.
    Цей хендлер буде викликаний для повідомлень — тут ми перевіряємо наявність web_app_data.
    """
    msg = update.effective_message
    if not msg:
        return

    web_app = getattr(msg, "web_app_data", None)
    if not web_app:
        # Не web app — ігноруємо
        return

    user = update.effective_user
    # Захищений доступ до поля data (воно може бути bytes або str залежно від версії)
    data_raw = getattr(web_app, "data", None)
    if data_raw is None:
        await msg.reply_text("❌ Помилка: Отримано пусті дані з Mini App.")
        return

    # Якщо байти — перетворимо в рядок
    if isinstance(data_raw, (bytes, bytearray)):
        try:
            data_str = data_raw.decode("utf-8")
        except Exception:
            data_str = data_raw.decode(errors="ignore")
    else:
        data_str = str(data_raw)

    logger.info(f"Отримано дані Mini App від {user.username} ({user.id}): {data_str}")

    try:
        data_json = json.loads(data_str)

        # 1. ПЕРЕВІРКА ДІЇ
        action = data_json.get("action")
        if action == "update_status":

            # 2. ПЕРЕВІРКА НЕОБХІДНИХ ПОЛІВ
            required_keys = ["title", "chapter", "role", "date", "status"]
            if not all(k in data_json for k in required_keys):
                error_message = f"❌ Помилка: JSON-запит на оновлення статусу неповний. Необхідні поля: {required_keys}"
                await msg.reply_text(error_message)
                return

            # 3. ВИКЛИК ОСНОВНОЇ ЛОГІКИ
            args = (
                data_json["title"],
                data_json["chapter"],
                data_json["role"],
                data_json["date"],
                data_json["status"],
            )
            await update_status_command(update, context, args)

        else:
            # Обробка невідомої дії або інших JSON-запитів
            await msg.reply_text(f"❓ Невідома дія в JSON-запиті: {action}. Отримано: `{data_str}`")

    except json.JSONDecodeError:
        # 4. FALLBACK: СПРОБА ПАРСИНГУ ЯК СТАРОЇ КОМАНДИ (якщо це не JSON)
        match = UPDATE_STATUS_PATTERN.match(data_str)
        if match:
            await update_status_command(update, context, match.groups())
            return  # Успішно оброблено як команду

        # Якщо не вдалося ні JSON, ні команда
        error_message = f"❌ Помилка: Отримано невалідний формат даних з Mini App. Очікувався JSON. Отримано: `{data_str}`"
        await msg.reply_text(error_message)
        logger.warning(f"Помилка парсингу Mini App: {data_str}")


async def update_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE, args: Tuple[str, str, str, str, str]) -> None:
    """Виконує логіку оновлення статусу в Google Sheets."""
    title, chapter, role_key, date, status = args

    user = update.effective_user
    sheets_helper: SheetsHelper | None = context.application.bot_data.get("sheets_helper")

    if not sheets_helper:
        if update.effective_message:
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
            telegram_tag=f"@{user.username}" if user.username else str(user.id),
        )
        await update.effective_message.reply_text(result_message)
    except Exception as e:
        logger.exception(f"Помилка при оновленні статусу: {e}")
        await update.effective_message.reply_text(f"❌ Помилка при оновленні статусу в таблиці: {e}")


# ============================================================================== #
# ЗАПУСК БОТА
# ============================================================================== #


async def run_bot():
    """Основна функція для запуску бота та веб-сервера aiohttp."""
    if not TELEGRAM_BOT_TOKEN or not WEBHOOK_URL or not SPREADSHEET_KEY:
        logger.error("Відсутні необхідні змінні середовища (TOKEN, WEBHOOK_URL, SPREADSHEET_KEY).")
        return

    # 1. Створення об'єкта SheetsHelper
    sheets_helper = SheetsHelper(SPREADSHEET_KEY)

    # 2. Створення застосунку Telegram
    bot_app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # 3. ЗБЕРЕЖЕННЯ ДАНИХ
    bot_app.bot_data["sheets_helper"] = sheets_helper
    logger.info("SheetsHelper збережено в Application.bot_data.")

    # 4. Налаштування webhook
    parsed_url = URL(WEBHOOK_URL)
    webhook_path = parsed_url.path or "/"
    # Формуємо повний URL (безпечно)
    full_webhook_url = str(parsed_url.with_path(webhook_path))

    # Встановлюємо webhook у Telegram
    await bot_app.bot.set_webhook(url=full_webhook_url)
    logger.info(f"Встановлено Webhook на: {full_webhook_url}")

    # 5. Налаштування обробників
    bot_app.add_handler(CommandHandler("start", start_command))

    # Реєструємо загальний MessageHandler — всередині він перевіряє наявність web_app_data
    bot_app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, web_app_data_handler))

    # 6. Налаштування маршрутів aiohttp
    aio_app = web.Application()
    aio_app["bot_app"] = bot_app
    aio_app.add_routes(
        [
            web.get("/health", lambda r: web.Response(text="OK")),
            web.post(webhook_path, webhook_handler),
            # --- МАРШРУТИЗАЦІЯ ДЛЯ МІНІ-ЗАСТОСУНКУ ---
            web.get(WEB_APP_ENTRYPOINT, miniapp),
            web.static(WEB_APP_ENTRYPOINT, path="webapp", name="static"),
        ]
    )

    # 7. Запуск веб-сервера
    runner = web.AppRunner(aio_app)
    await runner.setup()

    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    logger.info(f"Starting web server on port {port}")
    await site.start()

    # Запобігання виходу головного циклу asyncio
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped manually.")
    except Exception as e:
        logger.exception(f"Fatal error in main loop: {e}")
