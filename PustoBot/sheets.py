# PustoBot/sheets.py
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
import re
import logging
import os
import json
from collections import defaultdict 

# --- Налаштування та Ініціалізація ---
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
    "клін": "Клін",
    "переклад": "Переклад",
    "тайп": "Тайп",
    "редакт": "Редакт",
    "ред": "Редакт",
}
STATUS_DONE = "✅"
STATUS_TODO = "❌"
PUBLISHED_DONE = "✔️"
PUBLISHED_TODO = "❌"
COLUMN_TITLE_NUMBER = 1 # Колонка A

def normalize_title(title):
    """Нормалізує назву тайтлу для пошуку."""
    return re.sub(r'[^\\w\\s]', '', title).lower().strip()

# --- Припускаємо, що connect_to_google_sheets коректно ініціалізує global змінні ---
def connect_to_google_sheets():
    """Ініціалізує з'єднання з Google Sheets."""
    # Примітка: Додайте тут свою логіку підключення (використовуючи `credentials.json` або змінні середовища)
    # та ініціалізуйте global змінні titles_sheet, users_sheet, log_sheet.
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
        global client
        client = gspread.authorize(creds)
        
        spreadsheet_key = os.getenv("SPREADSHEET_KEY") # Необхідно додати цю змінну оточення!
        if not spreadsheet_key:
             logger.error("Змінна SPREADSHEET_KEY не встановлена.")
             return False

        global main_spreadsheet, log_sheet, titles_sheet, users_sheet
        main_spreadsheet = client.open_by_key(spreadsheet_key)
        titles_sheet = main_spreadsheet.worksheet("Тайтли")
        users_sheet = main_spreadsheet.worksheet("Користувачі")
        log_sheet = main_spreadsheet.worksheet("Журнал")
        
        initialize_header_map()
        load_nickname_map()
        return True
    except Exception as e:
         logger.error(f"Помилка підключення до Google Sheets: {e}")
         return False

def initialize_header_map():
    """Створює глобальну карту колонок (припущення на основі структури)."""
    global COLUMN_MAP
    # Припущення про індекси колонок на основі опису структури
    COLUMN_MAP = {
        "Тайтли": 1,
        "Клін-Статус": 2,
        "Клін-Людина": 3,
        "Переклад-Статус": 4,
        "Переклад-Людина": 5,
        "Тайп-Статус": 6,
        "Тайп-Людина": 7,
        "Редакт-Статус": 8,
        "Редакт-Людина": 9,
        "Дедлайн": 10,
        "Публікація-Статус": 11,
    }
    return True

def load_nickname_map():
    """Завантажує мапу нікнеймів {Telegram-тег: Нік} з аркуша 'Користувачі'."""
    global NICKNAME_MAP
    if users_sheet is None:
        logger.error("Аркуш 'Користувачі' не ініціалізовано.")
        return 
    try:
        users_data = users_sheet.get_all_values()
        for row in users_data[1:]: # Припускаємо, що 1-й рядок - заголовок
            if len(row) >= 4:
                telegram_tag = row[1].strip().lstrip('@') # Теґ
                user_nick = row[2].strip()                 # Нік
                if telegram_tag and user_nick:
                    NICKNAME_MAP[telegram_tag.lower()] = user_nick
    except Exception as e:
        logger.error(f"Помилка при завантаженні карти нікнеймів: {e}")

def resolve_user_nickname(telegram_tag, proposed_nickname):
    """Визначає нік користувача (завдання 1)."""
    if proposed_nickname:
        return proposed_nickname

    if not NICKNAME_MAP:
        load_nickname_map()
    
    # Шукаємо зареєстрований нік за тегом
    user_nick = NICKNAME_MAP.get(telegram_tag.lower().lstrip('@'))
    
    if user_nick:
        return user_nick
    
    # Використовуємо Telegram Tag (без @) як резервний
    return telegram_tag.lstrip('@')

def find_title_block(title_identifier):
    """Знаходить рядок заголовку блоку тайтлу і кінець блоку."""
    if titles_sheet is None or not COLUMN_MAP:
        return None, None
        
    normalized_identifier = normalize_title(title_identifier)
    
    try:
        data = titles_sheet.get_all_values()
        start_row = 0
        end_row = len(data)

        # 1. Пошук рядка заголовку тайтлу (за назвою або номером)
        title_blocks = []
        for i, row in enumerate(data):
            # Рядок вважається заголовком тайтлу, якщо він має назву та імена людей у колонках ролей
            title_col_idx = COLUMN_MAP["Тайтли"] - 1
            person_col_idx = COLUMN_MAP["Клін-Людина"] - 1 
            
            if len(row) > title_col_idx and row[title_col_idx].strip() and \
               len(row) > person_col_idx and row[person_col_idx].strip():
                title_blocks.append({'row': i + 1, 'name': row[title_col_idx].strip()})
        
        # Визначаємо start_row
        if title_identifier.isdigit():
            target_index = int(title_identifier)
            if 0 < target_index <= len(title_blocks):
                start_row = title_blocks[target_index - 1]['row']
        else:
            for block in title_blocks:
                if normalize_title(block['name']) == normalized_identifier:
                    start_row = block['row']
                    break
            
        if start_row == 0:
            return None, None
                
        # 2. Пошук кінця блоку (наступний порожній рядок або наступний заголовок тайтлу)
        next_title_index = -1
        for i, block in enumerate(title_blocks):
            if block['row'] > start_row:
                next_title_index = block['row']
                break

        if next_title_index != -1:
            end_row = next_title_index - 1
        else:
            # Кінець таблиці або перед першим порожнім рядком
            for i in range(start_row + 1, titles_sheet.row_count):
                if not titles_sheet.cell(i + 1, COLUMN_MAP["Тайтли"]).value:
                    end_row = i 
                    break
            else:
                 end_row = titles_sheet.row_count # Якщо немає порожнього рядка
            
        return start_row, end_row

    except Exception as e:
        logger.error(f"Помилка при пошуку блоку тайтлу: {e}")
        return None, None

def find_chapter_row(start_row, end_row, chapter_number):
    """Знаходить абсолютний номер рядка для розділу в межах блоку."""
    if titles_sheet is None or not COLUMN_MAP:
        return None
    
    # Дані про розділи починаються з 5-го рядка блоку
    data_start_row = start_row + 4
    col_chapter = COLUMN_MAP["Тайтли"] 
    
    try:
        chapter_cells = titles_sheet.range(data_start_row, col_chapter, end_row, col_chapter)
        for cell in chapter_cells:
            if cell.value.strip() == str(chapter_number).strip():
                return cell.row 
        return None
    except Exception as e:
        logger.error(f"Помилка при пошуку рядка розділу: {e}")
        return None

def get_title_number_and_name(title_identifier):
    """Знаходить Номер Тайтлу (індекс) та його оригінальну Назву за Назвою або Номером."""
    if titles_sheet is None or not COLUMN_MAP:
        return None, None

    normalized_identifier = normalize_title(title_identifier)

    try:
        data = titles_sheet.get_all_values()
        title_blocks = []
        
        # Знайти всі заголовки тайтлів
        for i, row in enumerate(data):
            title_col_idx = COLUMN_MAP["Тайтли"] - 1
            person_col_idx = COLUMN_MAP["Клін-Людина"] - 1 
            
            if len(row) > title_col_idx and row[title_col_idx].strip() and \
               len(row) > person_col_idx and row[person_col_idx].strip():
                title_blocks.append(row[title_col_idx].strip())
        
        # Пошук за номером (індексом) або назвою
        for title_number, title_name in enumerate(title_blocks, 1):
            if normalized_identifier == normalize_title(title_name) or str(title_number) == title_identifier:
                return str(title_number), title_name
        return None, None
        
    except Exception as e:
        logger.error(f"Помилка при отриманні номера та назви тайтлу: {e}")
        return None, None

def update_title_table(title_identifier, chapter_number, role, nickname):
    """Оновлює статус ролі - ставить галочку, пише нік та дату (завдання 1)."""
    if title_identifier.isdigit():
        _, title_identifier = get_title_number_and_name(title_identifier)
        if not title_identifier: return False

    start_row, end_row = find_title_block(title_identifier)
    if start_row is None: return False
    
    row_index = find_chapter_row(start_row, end_row, chapter_number)
    if row_index is None: return False
        
    try:
        current_date = datetime.now().strftime("%Y-%m-%d")
        role_base = ROLE_MAPPING.get(role.lower())
        
        if role_base:
            # Колонка "Статус"
            status_col = COLUMN_MAP.get(f"{role_base}-Статус")
            if status_col is not None:
                titles_sheet.update_cell(row_index, status_col, STATUS_DONE)

            # Колонка "Людина" (нік та дата)
            person_col = COLUMN_MAP.get(f"{role_base}-Людина")
            if person_col is not None:
                new_value = f"{nickname} - {current_date}"
                titles_sheet.update_cell(row_index, person_col, new_value)
                return True
                 
        return False

    except Exception as e:
        logger.error(f"Помилка при оновленні статусу ролі: {e}")
        return False

def set_publish_status(title_identifier, chapter_number):
    """Оновлює статус розділу на 'Опубліковано' (завдання 3)."""
    if title_identifier.isdigit():
        _, title_identifier = get_title_number_and_name(title_identifier)
        if not title_identifier:
            logger.warning(f"Тайтл з номером '{title_identifier}' не знайдено.")
            return "error", None

    start_row, end_row = find_title_block(title_identifier)
    if start_row is None:
        logger.warning(f"Блок тайтлу '{title_identifier}' не знайдено.")
        return "error", None
        
    original_title = titles_sheet.cell(start_row, COLUMN_MAP["Тайтли"]).value
    row_index = find_chapter_row(start_row, end_row, chapter_number)
    if row_index is None:
        logger.warning(f"Розділ '{chapter_number}' для тайтлу '{original_title}' не знайдено.")
        return "error", None
    
    try:
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # Колонка "Публікація-Статус"
        pub_status_col = COLUMN_MAP.get("Публікація-Статус")
        if pub_status_col is not None:
            titles_sheet.update_cell(row_index, pub_status_col, PUBLISHED_DONE)

        # Колонка "Дедлайн" (дата публікації)
        deadline_col = COLUMN_MAP.get("Дедлайн")
        if deadline_col is not None:
             titles_sheet.update_cell(row_index, deadline_col, current_date)
        
        return "success", original_title

    except Exception as e:
        logger.error(f"Помилка при оновленні статусу публікації: {e}")
        return "error", None

def get_title_status_data(title_identifier):
    """Отримує всі дані по тайтлу для команди /status (завдання 4)."""
    resolved_title_name = title_identifier
    if title_identifier and title_identifier.isdigit():
        _, resolved_title_name = get_title_number_and_name(title_identifier)
        if not resolved_title_name: return None, None
            
    start_row, end_row = find_title_block(resolved_title_name)
    if start_row is None: return None, None
        
    original_title = titles_sheet.cell(start_row, COLUMN_MAP["Тайтли"]).value
    
    data_range_start_row = start_row + 4 
    max_col_index = max(COLUMN_MAP.values())
    
    data_range_values = titles_sheet.range(data_range_start_row, 1, end_row, max_col_index).get_all_values()
    
    records = []
    
    # Індекси колонок
    col_chapter = COLUMN_MAP["Тайтли"] - 1 
    col_pub_status = COLUMN_MAP.get("Публікація-Статус") - 1
    col_deadline = COLUMN_MAP.get("Дедлайн") - 1

    role_keys = ["клін", "переклад", "тайп", "редакт"]
    role_cols = {
        key: {
            'status': COLUMN_MAP.get(f"{ROLE_MAPPING.get(key)}-Статус") - 1,
            'person': COLUMN_MAP.get(f"{ROLE_MAPPING.get(key)}-Людина") - 1,
        } for key in role_keys
    }
    
    for row_values in data_range_values:
        chapter_number = row_values[col_chapter].strip() if len(row_values) > col_chapter else ""
        if not chapter_number or not chapter_number.isdigit(): continue
            
        record = {
            'chapter': chapter_number,
            'published': (col_pub_status is not None and len(row_values) > col_pub_status and row_values[col_pub_status] == PUBLISHED_DONE),
            'deadline': row_values[col_deadline].strip() if col_deadline is not None and len(row_values) > col_deadline else '—',
            'roles': {}
        }
        
        for role_key, cols in role_cols.items():
            status_idx = cols['status']
            person_idx = cols['person']
            
            role_status = (status_idx is not None and len(row_values) > status_idx and row_values[status_idx] == STATUS_DONE)
            person_raw = row_values[person_idx].strip() if person_idx is not None and len(row_values) > person_idx else None
            role_person = person_raw.split(' - ')[0].strip() if person_raw and ' - ' in person_raw else person_raw
            
            record['roles'][role_key] = {
                'status': role_status,
                'person': role_person
            }
        
        records.append(record)

    return original_title, records


def append_log_row(telegram_nick, telegram_tag, title, chapter, role, nickname):
    """Додає запис до Журналу."""
    if log_sheet is None:
        logger.error("Аркуш 'Журнал' не ініціалізовано.")
        return
    try:
        log_sheet.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            telegram_nick,
            telegram_tag,
            title,
            chapter,
            role,
            nickname
        ])
    except Exception as e:
        logger.error(f"Помилка при записі в журнал: {e}")