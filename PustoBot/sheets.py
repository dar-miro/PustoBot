import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
import re
import logging

# Налаштування логування
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Авторизація
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

client = None
main_spreadsheet = None
log_sheet = None
titles_sheet = None

try:
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)
    main_spreadsheet = client.open("DataBase")
    log_sheet = main_spreadsheet.worksheet("Журнал")
    titles_sheet = main_spreadsheet.worksheet("Тайтли")
    logger.info("Успішно підключено до Google Sheets.")
except Exception as e:
    logger.error(f"Помилка підключення до Google Sheets: {e}")
    # Важливо: якщо тут виникла помилка, об'єкти sheet будуть None.
    # Обробники в main.py повинні це враховувати або перевіряти.

# Відповідність ролей і колонок
columns_by_role = {
    "клін": {"nick": "B", "date": "C", "check": "D"},
    "переклад": {"nick": "E", "date": "F", "check": "G"},
    "тайп": {"nick": "H", "date": "I", "check": "J"},
    "ред": {"nick": "K", "date": "L", "check": "M"},
    "редакт": {"nick": "K", "date": "L", "check": "M"},
}

def get_title_sheet():
    if titles_sheet is None:
        logger.error("titles_sheet не ініціалізовано. Можливо, проблема з credentials.json або доступом.")
        # Можна повернути заглушку або викликати виняток, якщо sheet обов'язковий.
        # Для цього бота, краще, щоб виклики функцій з sheets.py перевіряли None.
    return titles_sheet

def normalize_title(t):
    return re.sub(r'\\s+', ' ', t.strip().lower().replace("’", "'"))

def get_user_sheet(main_sheet_instance): # Приймаємо екземпляр основного аркуша
    if main_sheet_instance is None:
        logger.error("main_sheet_instance не передано для get_user_sheet.")
        return None
    try:
        return main_sheet_instance.spreadsheet.worksheet("Користувачі")
    except gspread.exceptions.WorksheetNotFound: # Точніший виняток
        logger.warning("Аркуш 'Користувачі' не знайдено, створюю новий.")
        return main_sheet_instance.spreadsheet.add_worksheet("Користувачі", rows=100, cols=3)
    except Exception as e:
        logger.error(f"Помилка при отриманні або створенні аркуша 'Користувачі': {e}")
        return None

def load_nickname_map():
    user_sheet = get_user_sheet(main_spreadsheet) # Передаємо main_spreadsheet
    if user_sheet is None:
        return {} # Повернути порожній словник, якщо аркуш недоступний

    try:
        data = user_sheet.get_all_records()
        nickname_map = {row["Telegram-нік"]: row["Нік"] for row in data if "Telegram-нік" in row and "Нік" in row}
        return nickname_map
    except Exception as e:
        logger.error(f"Помилка при завантаженні мапи нікнеймів: {e}")
        return {}

def append_log_row(telegram_name, title, chapter, position, nickname):
    if log_sheet is None:
        logger.error("log_sheet не ініціалізовано, неможливо додати запис у лог.")
        return False
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_sheet.append_row([now, telegram_name, title, chapter, position, nickname])
        return True
    except Exception as e:
        logger.error(f"Помилка при додаванні запису в лог: {e}")
        return False

# ✍️ Оновлення таблиці по знайденому блоку
def update_title_table(title, chapter, role, nickname):
    if titles_sheet is None:
        logger.error("titles_sheet не ініціалізовано, неможливо оновити таблицю.")
        return False

    role_columns = columns_by_role.get(role.lower()) # Використовуємо .lower()
    if not role_columns:
        logger.warning(f"Невідома роль для оновлення: {role}")
        return False

    blocks = get_title_blocks()
    for block_title, start_row, end_row in blocks:
        if normalize_title(block_title) == normalize_title(title):
            rows = titles_sheet.get_all_values()[start_row:end_row]
            for i, row in enumerate(rows):
                # Перевіряємо, чи є в рядку достатньо елементів для доступу до chapter
                if row and len(row) > 0 and chapter.strip() == row[0].strip(): # Порівнюємо розділ
                    actual_row = start_row + i + 1 # +1 для індексації Google Sheets, +1 бо headers
                    now = datetime.now().strftime("%Y-%m-%d")
                    try:
                        titles_sheet.update_acell(f"{role_columns['nick']}{actual_row}", nickname)
                        titles_sheet.update_acell(f"{role_columns['date']}{actual_row}", now)
                        titles_sheet.update_acell(f"{role_columns['check']}{actual_row}", "✅")
                        return True
                    except Exception as e:
                        logger.error(f"Помилка при оновленні комірки в Google Sheets: {e}")
                        return False
    logger.warning(f"Не знайдено розділ '{chapter}' для тайтлу '{title}' для оновлення.")
    return False

def get_title_blocks():
    if titles_sheet is None:
        logger.error("titles_sheet не ініціалізовано, неможливо отримати блоки тайтлів.")
        return []
    try:
        data = titles_sheet.get_all_values()
        blocks = []
        current_title = None
        start_row = None
        for i, row in enumerate(data):
            # Перша колонка не порожня і це не заголовок "Розділ"
            if row and row[0].strip() and not row[0].strip().lower().startswith("розділ"):
                if current_title is None:
                    current_title = row[0].strip()
                    start_row = i
            elif not any(row) and current_title is not None: # Порожній рядок розділяє блоки
                blocks.append((current_title, start_row, i))
                current_title = None
        # Додати останній блок, якщо він є
        if current_title:
            blocks.append((current_title, start_row, len(data)))
        return blocks
    except Exception as e:
        logger.error(f"Помилка при отриманні блоків тайтлів: {e}")
        return []

def get_full_title_data():
    if titles_sheet is None:
        logger.error("titles_sheet не ініціалізовано, неможливо отримати повні дані тайтлів.")
        return []
    try:
        return titles_sheet.get_all_values()
    except Exception as e:
        logger.error(f"Помилка при отриманні всіх значень з аркуша Тайтли: {e}")
        return []


def set_main_roles(title, roles_map):
    if titles_sheet is None:
        logger.error("titles_sheet не ініціалізовано, неможливо встановити основні ролі.")
        return False
    try:
        data = titles_sheet.get_all_values()
        headers = data[0] if data else []
        
        # Знайти колонки для 'Осн. Клін', 'Осн. Переклад' тощо
        main_role_cols = {
            "клін": headers.index("Осн. Клін") if "Осн. Клін" in headers else -1,
            "переклад": headers.index("Осн. Переклад") if "Осн. Переклад" in headers else -1,
            "тайп": headers.index("Осн. Тайп") if "Осн. Тайп" in headers else -1,
            "редакт": headers.index("Осн. Редакт") if "Осн. Редакт" in headers else -1,
        }

        for i, row in enumerate(data):
            if normalize_title(row[0]) == normalize_title(title):
                # Рядок заголовка тайтлу
                row_num = i + 1 # індекс рядка в Google Sheets
                for role, nickname in roles_map.items():
                    col_idx = main_role_cols.get(role)
                    if col_idx != -1 and col_idx is not None:
                        titles_sheet.update_cell(row_num, col_idx + 1, nickname) # +1 для індексу колонки
                return True
        logger.warning(f"Тайтл '{title}' не знайдено для встановлення основних ролей.")
        return False
    except Exception as e:
        logger.error(f"Помилка при встановленні основних ролей: {e}")
        return False