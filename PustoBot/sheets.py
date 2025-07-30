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
    return titles_sheet

def normalize_title(t):
    return re.sub(r'\\s+', ' ', t.strip().lower().replace("’", "'"))

def get_user_sheet(main_sheet_instance): # Приймаємо екземпляр основного аркуша
    if main_sheet_instance is None:
        logger.error("main_sheet_instance не передано для get_user_sheet.")
        return None
    try:
        # ВИПРАВЛЕНО: Тепер використовуємо main_sheet_instance.worksheet напряму
        return main_sheet_instance.worksheet("Користувачі")
    except gspread.exceptions.WorksheetNotFound:
        logger.warning("Аркуш 'Користувачі' не знайдено, створюю новий.")
        # Створення нового аркуша з заголовками: "Telegram-нік", "Теґ", "Нік", "Ролі"
        # ВИПРАВЛЕНО: Тепер використовуємо main_sheet_instance.add_worksheet напряму
        new_sheet = main_sheet_instance.add_worksheet("Користувачі", rows=100, cols=4)
        new_sheet.append_row(["Telegram-нік", "Теґ", "Нік", "Ролі"])
        return new_sheet
    except Exception as e:
        logger.error(f"Помилка при отриманні або створенні аркуша 'Користувачі': {e}")
        return None

def load_nickname_map():
    user_sheet = get_user_sheet(main_spreadsheet)
    if user_sheet is None:
        return {}

    try:
        data = user_sheet.get_all_records()
        nickname_map = {row["Telegram-нік"]: row["Нік"] for row in data if "Telegram-нік" in row and "Нік" in row}
        return nickname_map
    except Exception as e:
        logger.error(f"Помилка при завантаженні мапи нікнеймів: {e}")
        return {}

def find_user_row_by_nick_or_tag(telegram_full_name, telegram_tag, desired_nick):
    user_sheet = get_user_sheet(main_spreadsheet)
    if user_sheet is None:
        logger.error("user_sheet не ініціалізовано, неможливо здійснити пошук.")
        return None, None
    
    try:
        all_values = user_sheet.get_all_values()
        if not all_values or len(all_values) < 2: # Перевіряємо, чи є хоча б заголовки і один рядок даних
            return None, None
        
        headers = all_values[0]
        try:
            telegram_nick_col_idx = headers.index("Telegram-нік")
            tag_col_idx = headers.index("Теґ")
            nick_col_idx = headers.index("Нік")
        except ValueError as e:
            logger.error(f"Відсутня необхідна колонка в аркуші 'Користувачі': {e}. Заголовки: {headers}")
            return None, None

        for i, row in enumerate(all_values[1:]): # Починаємо з 1, щоб пропустити заголовки
            row_index = i + 2 # Індекс рядка в Google Sheets (з урахуванням заголовків та 1-індексації)
            
            if len(row) <= max(telegram_nick_col_idx, tag_col_idx, nick_col_idx):
                continue

            current_telegram_nick = row[telegram_nick_col_idx].strip().lower() if len(row) > telegram_nick_col_idx else ""
            current_tag = row[tag_col_idx].strip().lower() if len(row) > tag_col_idx else ""
            current_nick = row[nick_col_idx].strip().lower() if len(row) > nick_col_idx else ""

            if current_telegram_nick == telegram_full_name.strip().lower() or \
               current_nick == desired_nick.strip().lower() or \
               (telegram_tag and current_tag == telegram_tag.strip().lower()):
                return row_index, row
        return None, None
    except Exception as e:
        logger.error(f"Помилка при пошуку користувача за ніком або тегом: {e}")
        return None, None


def update_user_row(row_index, telegram_full_name, telegram_tag, desired_nick, roles):
    user_sheet = get_user_sheet(main_spreadsheet)
    if user_sheet is None:
        logger.error("user_sheet не ініціалізовано, неможливо оновити рядок.")
        return False
    
    try:
        headers = user_sheet.row_values(1)
        required_cols = ["Telegram-нік", "Теґ", "Нік", "Ролі"]
        for col in required_cols:
            if col not in headers:
                logger.error(f"Відсутня необхідна колонка '{col}' в аркуші 'Користувачі'. Заголовки: {headers}")
                return False

        telegram_nick_col_idx = headers.index("Telegram-нік") + 1
        tag_col_idx = headers.index("Теґ") + 1
        nick_col_idx = headers.index("Нік") + 1
        roles_col_idx = headers.index("Ролі") + 1

        user_sheet.update_cell(row_index, telegram_nick_col_idx, telegram_full_name)
        user_sheet.update_cell(row_index, tag_col_idx, telegram_tag)
        user_sheet.update_cell(row_index, nick_col_idx, desired_nick)
        user_sheet.update_cell(row_index, roles_col_idx, roles)
        return True
    except Exception as e:
        logger.error(f"Помилка при оновленні рядка користувача: {e}")
        return False

def append_user_row(telegram_full_name, telegram_tag, desired_nick, roles):
    user_sheet = get_user_sheet(main_spreadsheet)
    if user_sheet is None:
        logger.error("user_sheet не ініціалізовано, неможливо додати рядок.")
        return False
    try:
        user_sheet.append_row([telegram_full_name, telegram_tag, desired_nick, roles])
        return True
    except Exception as e:
        logger.error(f"Помилка при додаванні нового рядка користувача: {e}")
        return False


def append_log_row(telegram_name, telegram_tag, title, chapter, position, nickname):
    if log_sheet is None:
        logger.error("log_sheet не ініціалізовано, неможливо додати запис у лог.")
        return False
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_sheet.append_row([now, telegram_name, telegram_tag, title, chapter, position, nickname])
        return True
    except Exception as e:
        logger.error(f"Помилка при додаванні запису в лог: {e}")
        return False

def update_title_table(title, chapter, role, nickname):
    if titles_sheet is None:
        logger.error("titles_sheet не ініціалізовано, неможливо оновити таблицю.")
        return False

    role_columns = columns_by_role.get(role.lower())
    if not role_columns:
        logger.warning(f"Невідома роль для оновлення: {role}")
        return False

    blocks = get_title_blocks()
    for block_title, start_row, end_row in blocks:
        if normalize_title(block_title) == normalize_title(title):
            rows = titles_sheet.get_all_values()[start_row:end_row]
            for i, row in enumerate(rows):
                if row and len(row) > 0 and chapter.strip() == row[0].strip():
                    actual_row = start_row + i + 1
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
            if row and row[0].strip() and not row[0].strip().lower().startswith("розділ"):
                if current_title is None:
                    current_title = row[0].strip()
                    start_row = i
            elif not any(row) and current_title is not None:
                blocks.append((current_title, start_row, i))
                current_title = None
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
        
        main_role_cols = {
            "клін": headers.index("Осн. Клін") if "Осн. Клін" in headers else -1,
            "переклад": headers.index("Осн. Переклад") if "Осн. Переклад" in headers else -1,
            "тайп": headers.index("Осн. Тайп") if "Осн. Тайп" in headers else -1,
            "редакт": headers.index("Осн. Редакт") if "Осн. Редакт" in headers else -1,
        }

        for i, row in enumerate(data):
            if normalize_title(row[0]) == normalize_title(title):
                row_num = i + 1
                for role, nickname in roles_map.items():
                    col_idx = main_role_cols.get(role)
                    if col_idx != -1 and col_idx is not None:
                        titles_sheet.update_cell(row_num, col_idx + 1, nickname)
                return True
        logger.warning(f"Тайтл '{title}' не знайдено для встановлення основних ролей.")
        return False
    except Exception as e:
        logger.error(f"Помилка при встановленні основних ролей: {e}")
        return False