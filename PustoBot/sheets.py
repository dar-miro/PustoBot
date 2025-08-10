# PustoBot/sheets.py
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
import re
import logging
import os
from collections import defaultdict

# --- Налаштування та Ініціалізація ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
client = None
main_spreadsheet = None
log_sheet = None
titles_sheet = None
users_sheet = None
COLUMN_MAP = {}
NICKNAME_MAP = {}
ROLE_MAPPING = {
    "клін": "Клін-Статус",
    "переклад": "Переклад-Статус",
    "тайп": "Тайп-Статус",
    "редакт": "Редакт-Статус",
    "ред": "Редакт-Статус",
}
STATUS_DONE = "✅"
STATUS_TODO = "❌"

def initialize_header_map():
    """
    Читає заголовки таблиці 'Тайтли', враховуючи складну структуру,
    і створює глобальну карту колонок.
    """
    global COLUMN_MAP
    if titles_sheet is None:
        logger.error("Аркуш 'Тайтли' не ініціалізовано. Неможливо створити карту заголовків.")
        return
        
    try:
        # Отримуємо всі значення з перших двох рядків
        all_headers = titles_sheet.get('1:2')
        if not all_headers or len(all_headers) < 2:
            logger.error("Не вдалося прочитати заголовки. Недостатньо рядків.")
            return

        top_row = all_headers[0]
        second_row = all_headers[1]
        
        column_map = {}
        # Заповнюємо карту з першого рядка
        for i, header in enumerate(top_row):
            if header:
                column_map[header.strip()] = i + 1
        
        # Доповнюємо карту з другого рядка для колонок з ролями
        current_role_base = None
        for i, header in enumerate(second_row):
            if header:
                current_role_base = header.strip()
            if current_role_base:
                full_header = f"{current_role_base}-{header.strip()}"
                column_map[full_header] = i + 1

        COLUMN_MAP = column_map
        logger.info("Карту заголовків оновлено.")
    except Exception as e:
        logger.error(f"Помилка при створенні карти заголовків: {e}")

def connect_to_google_sheets():
    """Встановлює з'єднання з Google Sheets API."""
    global client, main_spreadsheet, titles_sheet, users_sheet, log_sheet
    try:
        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
        if not creds_json:
            logger.error("Змінна оточення 'GOOGLE_CREDENTIALS_JSON' не встановлена.")
            return False
            
        creds = ServiceAccountCredentials.from_json_keyfile_dict(eval(creds_json), scope)
        client = gspread.authorize(creds)
        main_spreadsheet = client.open("PustoBot")
        titles_sheet = main_spreadsheet.worksheet("Тайтли")
        users_sheet = main_spreadsheet.worksheet("Користувачі")
        log_sheet = main_spreadsheet.worksheet("Журнал")
        initialize_header_map()
        load_nickname_map()
        return True
    except Exception as e:
        logger.error(f"Не вдалося підключитися до Google Sheets: {e}")
        return False

def load_nickname_map():
    """Завантажує нікнейми користувачів з аркуша 'Користувачі'."""
    global NICKNAME_MAP
    if users_sheet is None:
        logger.error("Аркуш 'Користувачі' не ініціалізовано.")
        return
    try:
        records = users_sheet.get_all_records()
        NICKNAME_MAP = {record['Теґ'].lstrip('@').lower(): (record['Telegram-нік'], record['Теґ'], record['Нік'], record['Ролі']) for record in records if record['Теґ']}
        logger.info(f"Завантажено {len(NICKNAME_MAP)} нікнеймів.")
    except Exception as e:
        logger.error(f"Помилка при завантаженні нікнеймів: {e}")

def resolve_user_nickname(telegram_tag):
    """Повертає зареєстрований нікнейм за Telegram-тегом."""
    if telegram_tag and telegram_tag.lower() in NICKNAME_MAP:
        return NICKNAME_MAP[telegram_tag.lower()][2]
    return None

def find_title_block(title_name):
    """Знаходить рядок тайтлу в таблиці 'Тайтли'."""
    if titles_sheet is None or not COLUMN_MAP:
        return None, None
    try:
        titles_column = titles_sheet.col_values(COLUMN_MAP.get("Тайтли"))
        
        # Створюємо словник для швидкого пошуку тайтлів
        title_rows = {normalize_title(val): idx + 1 for idx, val in enumerate(titles_column) if val}
        normalized_title = normalize_title(title_name)

        if normalized_title in title_rows:
            start_row = title_rows[normalized_title]
            
            # Шукаємо кінець блоку - наступний тайтл або кінець таблиці
            end_row = titles_sheet.row_count
            for t_title, t_row in title_rows.items():
                if t_row > start_row and t_row < end_row:
                    end_row = t_row - 1
                    break
            
            return start_row, end_row

    except Exception as e:
        logger.error(f"Помилка при пошуку блоку тайтлу: {e}")
    
    return None, None
    
def find_chapter_row(title_start_row, title_end_row, chapter_number):
    """Знаходить рядок розділу в межах блоку тайтлу."""
    if titles_sheet is None or not COLUMN_MAP:
        return None
    try:
        # Зчитуємо тільки колонку з номерами розділів у межах блоку тайтлу
        chapter_column_range = titles_sheet.range(
            f'A{title_start_row}:{len(COLUMN_MAP)}{title_end_row}'
        )
        for cell in chapter_column_range:
            if cell.col == COLUMN_MAP.get("Розділ №") and cell.value == chapter_number:
                return cell.row
    except Exception as e:
        logger.error(f"Помилка при пошуку рядка розділу: {e}")
    return None
    
def normalize_title(title):
    """Приводить назву тайтлу до єдиного формату."""
    return re.sub(r'[^\w]', '', title.lower().strip())

def update_title_table(title_name, chapter_number, role, nickname_to_set=None):
    """Оновлює статус виконання роботи для розділу."""
    if titles_sheet is None or not COLUMN_MAP:
        return False
    try:
        start_row, end_row = find_title_block(title_name)
        if start_row is None:
            logger.warning(f"Тайтл '{title_name}' не знайдено.")
            return False

        chapter_row = find_chapter_row(start_row, end_row, chapter_number)
        if chapter_row is None:
            logger.warning(f"Розділ '{chapter_number}' для тайтлу '{title_name}' не знайдено.")
            return False

        # Знаходимо назву колонки для статусу та нікнейму
        role_base_name = ROLE_MAPPING.get(role)
        if not role_base_name:
            logger.warning(f"Невідома роль: {role}")
            return False

        updates = []
        
        # 🆕 Виправлено: Оновлюємо нікнейм, тільки якщо він був переданий
        if nickname_to_set and f"{role_base_name.split('-')[0]}-Нік" in COLUMN_MAP:
            updates.append({'range': gspread.utils.rowcol_to_a1(chapter_row, COLUMN_MAP[f"{role_base_name.split('-')[0]}-Нік"]), 'values': [[nickname_to_set]]})
            logger.info(f"Оновлено нікнейм: {nickname_to_set}")
            
        # Оновлюємо дату
        if f"{role_base_name.split('-')[0]}-Дата" in COLUMN_MAP:
            current_date = datetime.now().strftime("%d.%m.%Y")
            updates.append({'range': gspread.utils.rowcol_to_a1(chapter_row, COLUMN_MAP[f"{role_base_name.split('-')[0]}-Дата"]), 'values': [[current_date]]})
            logger.info(f"Оновлено дату: {current_date}")
            
        # Оновлюємо статус
        if role_base_name in COLUMN_MAP:
            updates.append({'range': gspread.utils.rowcol_to_a1(chapter_row, COLUMN_MAP[role_base_name]), 'values': [[STATUS_DONE]]})
            logger.info(f"Оновлено статус: {STATUS_DONE}")

        if updates:
            titles_sheet.batch_update(updates)
            
        return True
    except Exception as e:
        logger.error(f"Помилка при оновленні таблиці: {e}")
        return False
def append_log_row(telegram_full_name, telegram_tag, title, chapter, role, nickname):
    """Додає запис до аркуша 'Журнал'."""
    if log_sheet is None:
        logger.error("Аркуш 'Журнал' не ініціалізовано.")
        return
    try:
        row = [
            datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            telegram_full_name,
            telegram_tag,
            title,
            chapter,
            role,
            nickname
        ]
        log_sheet.append_row(row)
    except Exception as e:
        logger.error(f"Помилка при додаванні запису в журнал: {e}")

def get_title_status_data(title_name):
    """Отримує всі дані по тайтлу для команди /status."""
    if not COLUMN_MAP:
        logger.error("Карта колонок порожня. Неможливо отримати статус.")
        return None, None
    
    start_row, end_row = find_title_block(title_name)
    if start_row is None:
        return None, None
        
    original_title = titles_sheet.cell(start_row, COLUMN_MAP["Тайтли"]).value
    
    data_range_start_row = start_row + 4
    if data_range_start_row > end_row:
        return original_title, []
        
    data_range = titles_sheet.range(
        data_range_start_row, 1, end_row, len(COLUMN_MAP)
    )
    
    records = []
    
    for row_start_index in range(0, len(data_range), len(COLUMN_MAP)):
        row_data = data_range[row_start_index:row_start_index + len(COLUMN_MAP)]
        record = {}
        for cell in row_data:
            for key, col_idx in COLUMN_MAP.items():
                if col_idx == cell.col:
                    if "Розділ" in key and cell.value:
                        record['chapter'] = cell.value
                    elif "Публікація-Статус" in key:
                        record['published'] = cell.value == "Опубліковано"
                    else:
                        role_match = re.search(r'^(.*)-(Статус|Дата|Нік)$', key)
                        if role_match:
                            role_key = role_match.group(1).lower()
                            data_type = role_match.group(2).lower()
                            if role_key not in record:
                                record[role_key] = {}
                            record[role_key][data_type] = cell.value
                    break
        if record:
            records.append(record)
    
    return original_title, records

def set_publish_status(title_name, chapter_number):
    """Оновлює статус розділу на 'Опубліковано'."""
    if titles_sheet is None or not COLUMN_MAP:
        return "error", "Таблиці не ініціалізовано."

    try:
        start_row, end_row = find_title_block(title_name)
        if start_row is None:
            return "error", f"Тайтл '{title_name}' не знайдено."

        chapter_row = find_chapter_row(start_row, end_row, chapter_number)
        if chapter_row is None:
            return "error", f"Розділ '{chapter_number}' для тайтлу '{title_name}' не знайдено."

        original_title = titles_sheet.cell(start_row, COLUMN_MAP["Тайтли"]).value
        
        publish_col = COLUMN_MAP.get("Публікація-Статус")
        if publish_col:
            titles_sheet.update_cell(chapter_row, publish_col, "Опубліковано")
            return "success", original_title
        else:
            return "error", "Колонка 'Публікація-Статус' не знайдена."
            
    except Exception as e:
        logger.error(f"Помилка при оновленні статусу публікації: {e}")
        return "error", f"Виникла помилка: {e}"

def set_main_roles(title_name, roles_map):
    """Записує відповідальних за тайтл."""
    if titles_sheet is None or not COLUMN_MAP:
        return False
    try:
        start_row, end_row = find_title_block(title_name)
        if start_row is None:
            return False
            
        update_range = []
        for role, nickname in roles_map.items():
            normalized_role = next((k for k, v in ROLE_MAPPING.items() if v.lower() == f"{role}-статус"), None)
            if normalized_role:
                col_name = f"{normalized_role.capitalize()}-Нік"
                if col_name in COLUMN_MAP:
                    col_index = COLUMN_MAP[col_name]
                    update_range.append({'range': gspread.utils.rowcol_to_a1(start_row, col_index), 'values': [[nickname]]})

        if update_range:
            titles_sheet.batch_update(update_range)
            return True
            
    except Exception as e:
        logger.error(f"Помилка при записі відповідальних за тайтл: {e}")
    return False

def get_user_sheet():
    """Повертає об'єкт аркуша 'Користувачі'."""
    return users_sheet

def find_user_row_by_nick_or_tag(nickname=None, telegram_tag=None):
    """Шукає користувача за ніком або тегом."""
    if users_sheet is None:
        return None
    
    try:
        records = users_sheet.get_all_records()
        for i, record in enumerate(records):
            if nickname and record['Нік'] == nickname:
                return i + 2, record
            if telegram_tag and record['Теґ'] and record['Теґ'].lstrip('@').lower() == telegram_tag.lstrip('@').lower():
                return i + 2, record
    except Exception as e:
        logger.error(f"Помилка при пошуку користувача: {e}")
    return None, None

def update_user_row(row_index, new_data):
    """Оновлює рядок користувача."""
    if users_sheet is None:
        return False
    
    try:
        # Зчитуємо заголовки, щоб знайти колонки
        headers = users_sheet.row_values(1)
        update_list = []
        for key, value in new_data.items():
            try:
                col_index = headers.index(key) + 1
                update_list.append({'range': gspread.utils.rowcol_to_a1(row_index, col_index), 'values': [[value]]})
            except ValueError:
                logger.warning(f"Колонка '{key}' не знайдена в аркуші 'Користувачі'.")
                continue
        
        if update_list:
            users_sheet.batch_update(update_list)
            return True
    except Exception as e:
        logger.error(f"Помилка при оновленні даних користувача: {e}")
    return False

def append_user_row(new_data):
    """Додає нового користувача."""
    if users_sheet is None:
        return False
    
    try:
        headers = users_sheet.row_values(1)
        row = [new_data.get(header, '') for header in headers]
        users_sheet.append_row(row)
        return True
    except Exception as e:
        logger.error(f"Помилка при додаванні нового користувача: {e}")
    return False