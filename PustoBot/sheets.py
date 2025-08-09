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
        logger.error("Аркуш 'Тайтли' не ініціалізовано. Неможливо створити карту колонок.")
        return False
    
    header_row = titles_sheet.row_values(3) # Рядок із заголовками
    
    # Скидаємо стару мапу
    COLUMN_MAP.clear()
    
    # Визначаємо індекси колонок за назвами
    for i, header in enumerate(header_row):
        # Залишаємо тільки назву ролі
        if "-" in header:
            header_key = header.split("-")[0].strip()
        else:
            header_key = header.strip()
            
        # Зберігаємо індекс колонки за ключем (1-based index)
        COLUMN_MAP[header_key] = i + 1
        
    if not COLUMN_MAP:
        logger.error("Не вдалося ініціалізувати карту колонок. Заголовки порожні.")
        return False
        
    logger.info("Карту колонок успішно ініціалізовано.")
    return True

def load_nickname_map():
    """
    Завантажує мапу нікнеймів з аркуша 'Користувачі'
    та ініціалізує глобальну змінну NICKNAME_MAP.
    """
    global NICKNAME_MAP
    if users_sheet is None:
        logger.error("Аркуш 'Користувачі' не ініціалізовано. Неможливо завантажити мапу нікнеймів.")
        return NICKNAME_MAP
    
    records = users_sheet.get_all_records()
    new_map = {rec['Telegram-нік']: rec['Нік'] for rec in records if 'Telegram-нік' in rec and 'Нік' in rec}
    NICKNAME_MAP.update(new_map)
    logger.info("Мапу нікнеймів завантажено.")
    return NICKNAME_MAP


def connect_to_google_sheets():
    """
    Встановлює з'єднання з Google Sheets та ініціалізує глобальні змінні.
    """
    global client, main_spreadsheet, log_sheet, titles_sheet, users_sheet
    
    try:
        # Шлях до credentials.json тепер відносно кореневої папки проєкту
        creds_path = os.path.join(os.path.dirname(__file__), '..', 'credentials.json')
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
        client = gspread.authorize(creds)
        main_spreadsheet = client.open("Pusto_DB")
        
        titles_sheet = main_spreadsheet.worksheet("Тайтли")
        users_sheet = main_spreadsheet.worksheet("Користувачі")
        log_sheet = main_spreadsheet.worksheet("Журнал")
        
        initialize_header_map()
        load_nickname_map()
        
        logger.info("Підключення до Google Sheets успішне.")
        return True
    except gspread.exceptions.APIError as e:
        logger.error(f"Помилка GSpread API: {e}")
        return False
    except FileNotFoundError:
        logger.error("Файл credentials.json не знайдено.")
        return False
    except Exception as e:
        logger.error(f"Невідома помилка при підключенні: {e}")
        return False

def find_title_block(title_name):
    """Шукає блок тайтлу за назвою і повертає рядок початку та кінця."""
    normalized_name = normalize_title(title_name)
    all_titles = titles_sheet.col_values(COLUMN_MAP.get("Тайтли", 1))
    
    start_row = None
    for i, cell_value in enumerate(all_titles):
        if normalize_title(cell_value) == normalized_name:
            start_row = i + 1
            break
            
    if start_row is None:
        return None, None
        
    end_row = start_row + 4
    return start_row, end_row

def find_chapter_row(title_start_row, chapter_number):
    """Знаходить рядок з розділом у блоці тайтлу."""
    chapter_column_index = COLUMN_MAP.get("Розділ №")
    if not chapter_column_index:
        return None
        
    range_to_search = titles_sheet.range(
        title_start_row, chapter_column_index,
        title_start_row + 4, chapter_column_index
    )
    
    for cell in range_to_search:
        if cell.value == str(chapter_number):
            return cell.row
            
    return None

def find_user_row_by_nick_or_tag(nick_or_tag):
    """
    Шукає рядок користувача за ніком або тегом.
    Повертає номер рядка або None.
    """
    users_data = users_sheet.get_all_records()
    for i, record in enumerate(users_data):
        if record.get("Нік") == nick_or_tag or record.get("Теґ") == nick_or_tag:
            return i + 2 # +2, бо get_all_records() починається з рядка 2
    return None

def update_user_row(row_number, data):
    """Оновлює дані вказаного рядка в аркуші 'Користувачі'."""
    try:
        for header, value in data.items():
            col_index = users_sheet.find(header).col
            users_sheet.update_cell(row_number, col_index, value)
        return True
    except Exception as e:
        logger.error(f"Помилка при оновленні рядка користувача: {e}")
        return False

def append_user_row(data):
    """Додає новий рядок в аркуш 'Користувачі'."""
    try:
        headers = users_sheet.row_values(1)
        row_values = [data.get(h, "") for h in headers]
        users_sheet.append_row(row_values, value_input_option='USER_ENTERED')
        return True
    except Exception as e:
        logger.error(f"Помилка при додаванні нового користувача: {e}")
        return False


def get_user_sheet():
    """Повертає об'єкт аркуша 'Користувачі'."""
    return users_sheet

def update_title_table(title_name, chapter_number, role, nickname):
    """
    Оновлює статус виконання роботи для вказаного тайтлу, розділу, ролі та нікнейму.
    """
    if not COLUMN_MAP:
        logger.error("Карта колонок порожня. Неможливо оновити таблицю.")
        return False

    title_start_row, title_end_row = find_title_block(title_name)
    if title_start_row is None:
        logger.warning(f"Тайтл '{title_name}' не знайдено.")
        return False

    chapter_row = find_chapter_row(title_start_row, chapter_number)
    if chapter_row is None:
        logger.warning(f"Розділ '{chapter_number}' не знайдено для тайтлу '{title_name}'.")
        return False
        
    role_column_key = ROLE_MAPPING.get(role)
    if not role_column_key:
        logger.warning(f"Невідома роль: {role}.")
        return False
    
    role_column_index = COLUMN_MAP.get(role_column_key)
    if not role_column_index:
        logger.warning(f"Не знайдено колонку для ролі: {role}.")
        return False

    try:
        # Оновлюємо статус
        status_cell = titles_sheet.cell(chapter_row, role_column_index)
        if status_cell.value == STATUS_DONE:
            logger.info(f"Статус для {title_name}, розділ {chapter_number}, {role} вже виконано.")
            return False
        
        titles_sheet.update_cell(chapter_row, role_column_index, STATUS_DONE)

        # Оновлюємо нікнейм
        nickname_column_index = role_column_index + 1
        titles_sheet.update_cell(chapter_row, nickname_column_index, nickname)
        
        # Оновлюємо дату
        date_column_index = role_column_index + 2
        titles_sheet.update_cell(chapter_row, date_column_index, datetime.now().strftime("%d.%m.%Y"))
        
        logger.info(f"Успішно оновлено: {title_name}, розділ {chapter_number}, {role} для {nickname}.")
        return True
    except Exception as e:
        logger.error(f"Помилка при оновленні таблиці: {e}")
        return False

def append_log_row(telegram_nick, telegram_tag, title, chapter, role, nickname):
    """
    Додає новий рядок у журнал.
    """
    if log_sheet is None:
        logger.error("Аркуш 'Журнал' не ініціалізовано.")
        return False

    try:
        date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row = [date_time, telegram_nick, telegram_tag, title, str(chapter), role, nickname]
        log_sheet.append_row(row, value_input_option='USER_ENTERED')
        logger.info("Рядок додано до журналу.")
        return True
    except Exception as e:
        logger.error(f"Помилка при додаванні рядка до журналу: {e}")
        return False

def get_title_status_data(title_name):
    """
    Отримує всі дані по тайтлу для команди /status.
    """
    if not COLUMN_MAP:
        logger.error("Карта колонок порожня. Неможливо отримати статус.")
        return None, None
    
    start_row, end_row = find_title_block(title_name)
    if start_row is None:
        return None, None
        
    original_title = titles_sheet.cell(start_row, COLUMN_MAP["Тайтли"]).value
    
    data_range_start_row = start_row + 4
    data_range = titles_sheet.range(data_range_start_row, 1, end_row, len(COLUMN_MAP))
    
    records = []
    current_record = {}
    
    for cell in data_range:
        col_key_base = "Розділ №"
        
        for key, col_idx in COLUMN_MAP.items():
            if col_idx == cell.col:
                col_key_base = key
                break
        
        if cell.col == COLUMN_MAP["Розділ №"]:
            if current_record:
                records.append(current_record)
            current_record = {"chapter": cell.value, "published": False}
        
        if col_key_base == "Публікація-Статус" and cell.value:
            current_record["published"] = True
        
        role_key = None
        for r_key, r_value in ROLE_MAPPING.items():
            if r_value == col_key_base:
                role_key = r_key
                break
        
        if role_key:
            current_record[role_key] = {
                "status": cell.value,
                "nickname": titles_sheet.cell(cell.row, cell.col + 1).value,
                "date": titles_sheet.cell(cell.row, cell.col + 2).value
            }

    if current_record:
        records.append(current_record)
        
    return original_title, records


def set_main_roles(title_name, roles_map):
    """
    Записує основних відповідальних за тайтл в заголовок блоку.
    """
    if not COLUMN_MAP:
        logger.error("Карта колонок порожня. Неможливо встановити ролі.")
        return False
        
    title_start_row, _ = find_title_block(title_name)
    if title_start_row is None:
        logger.warning(f"Тайтл '{title_name}' не знайдено.")
        return False
        
    try:
        for role, nickname in roles_map.items():
            role_key = role.lower()
            column_index = COLUMN_MAP.get(role_key)
            if column_index:
                titles_sheet.update_cell(title_start_row + 1, column_index + 1, nickname)
        return True
    except Exception as e:
        logger.error(f"Помилка при встановленні головних ролей: {e}")
        return False

def set_publish_status(title_name, chapter_number):
    """
    Встановлює статус розділу на 'Опубліковано'.
    """
    if not COLUMN_MAP:
        logger.error("Карта колонок порожня. Неможливо встановити статус публікації.")
        return "error", "Internal error."
        
    title_start_row, _ = find_title_block(title_name)
    if title_start_row is None:
        logger.warning(f"Тайтл '{title_name}' не знайдено.")
        return "error", f"Тайтл '{title_name}' не знайдено."
        
    chapter_row = find_chapter_row(title_start_row, chapter_number)
    if chapter_row is None:
        logger.warning(f"Розділ '{chapter_number}' не знайдено для тайтлу '{title_name}'.")
        return "error", f"Розділ '{chapter_number}' не знайдено для тайтлу '{title_name}'."

    try:
        publish_col_index = COLUMN_MAP.get("Публікація-Статус")
        if publish_col_index:
            titles_sheet.update_cell(chapter_row, publish_col_index, "Опубліковано")
            titles_sheet.update_cell(chapter_row, publish_col_index - 1, datetime.now().strftime("%d.%m.%Y"))
            return "success", titles_sheet.cell(title_start_row, COLUMN_MAP["Тайтли"]).value
        else:
            return "error", "Не знайдено колонку 'Публікація-Статус'."
    except Exception as e:
        logger.error(f"Помилка при оновленні статусу публікації: {e}")
        return "error", "Невідома помилка при оновленні."
        
def normalize_title(title):
    """
    Нормалізує назву тайтлу для порівняння.
    """
    if title is None:
        return ""
    # Прибираємо пробіли, переводимо в нижній регістр і видаляємо не-буквено-цифрові символи
    normalized = re.sub(r'[^a-z0-9]', '', title.lower())
    return normalized

def set_main_roles(title_name, roles_map):
    """
    Записує основних відповідальних за тайтл в заголовок блоку.
    """
    if not COLUMN_MAP:
        logger.error("Карта колонок порожня. Неможливо встановити ролі.")
        return False
        
    title_start_row, _ = find_title_block(title_name)
    if title_start_row is None:
        logger.warning(f"Тайтл '{title_name}' не знайдено.")
        return False
        
    try:
        # Новий формат, що використовує назви з `COLUMN_MAP`
        updates = []
        for role, nickname in roles_map.items():
            role_key = role.lower()
            column_index = COLUMN_MAP.get(role_key)
            if column_index:
                cell_range = gspread.utils.rowcol_to_a1(title_start_row + 1, column_index + 1)
                updates.append({
                    'range': cell_range,
                    'values': [[nickname]]
                })
        
        if updates:
            titles_sheet.batch_update(updates)

        return True
    except Exception as e:
        logger.error(f"Помилка при встановленні головних ролей: {e}")
        return False

def set_publish_status(title_name, chapter_number):
    """
    Встановлює статус розділу на 'Опубліковано'.
    """
    if not COLUMN_MAP:
        logger.error("Карта колонок порожня. Неможливо встановити статус публікації.")
        return "error", "Internal error."
        
    title_start_row, _ = find_title_block(title_name)
    if title_start_row is None:
        logger.warning(f"Тайтл '{title_name}' не знайдено.")
        return "error", f"Тайтл '{title_name}' не знайдено."
        
    chapter_row = find_chapter_row(title_start_row, chapter_number)
    if chapter_row is None:
        logger.warning(f"Розділ '{chapter_number}' не знайдено для тайтлу '{title_name}'.")
        return "error", f"Розділ '{chapter_number}' не знайдено для тайтлу '{title_name}'."

    try:
        publish_col_index = COLUMN_MAP.get("Публікація-Статус")
        if publish_col_index:
            titles_sheet.update_cell(chapter_row, publish_col_index, "Опубліковано")
            titles_sheet.update_cell(chapter_row, publish_col_index - 1, datetime.now().strftime("%d.%m.%Y"))
            return "success", titles_sheet.cell(title_start_row, COLUMN_MAP["Тайтли"]).value
        else:
            return "error", "Не знайдено колонку 'Публікація-Статус'."
    except Exception as e:
        logger.error(f"Помилка при оновленні статусу публікації: {e}")
        return "error", "Невідома помилка при оновленні."
        
def get_title_status_data(title_name):
    """
    Отримує всі дані по тайтлу для команди /status.
    """
    if not COLUMN_MAP:
        logger.error("Карта колонок порожня. Неможливо отримати статус.")
        return None, None
    
    start_row, end_row = find_title_block(title_name)
    if start_row is None:
        return None, None
        
    original_title = titles_sheet.cell(start_row, COLUMN_MAP["Тайтли"]).value
    
    data_range_start_row = start_row + 4
    data_range = titles_sheet.range(data_range_start_row, 1, end_row, len(COLUMN_MAP))
    
    records = []
    current_record = {}
    
    for cell in data_range:
        col_key_base = "Розділ №"
        
        for key, col_idx in COLUMN_MAP.items():
            if col_idx == cell.col:
                col_key_base = key
                break
        
        if cell.col == COLUMN_MAP["Розділ №"]:
            if current_record:
                records.append(current_record)
            current_record = {"chapter": cell.value, "published": False}
        
        if col_key_base == "Публікація-Статус" and cell.value:
            current_record["published"] = True
        
        role_key = None
        for r_key, r_value in ROLE_MAPPING.items():
            if r_value == col_key_base:
                role_key = r_key
                break
        
        if role_key:
            current_record[role_key] = {
                "status": cell.value,
                "nickname": titles_sheet.cell(cell.row, cell.col + 1).value,
                "date": titles_sheet.cell(cell.row, cell.col + 2).value
            }

    if current_record:
        records.append(current_record)
        
    return original_title, records