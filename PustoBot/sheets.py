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
        return
    
    try:
        header_rows = titles_sheet.get('A1:AZ4', value_render_option='UNFORMATTED_VALUE')
        if len(header_rows) < 4:
            logger.error("Недостатньо рядків для ініціалізації карти колонок. Перевірте структуру таблиці.")
            return

        COLUMN_MAP.clear()
        
        main_headers = header_rows[0]
        sub_headers = header_rows[2]
        role_nicks_headers = header_rows[3]

        col_index = 1
        main_role = None
        
        # Визначаємо максимальну кількість колонок серед усіх рядків заголовків
        max_cols = max(len(main_headers), len(sub_headers), len(role_nicks_headers))

        for i in range(max_cols):
            # Безпечно отримуємо значення з кожного рядка, уникаючи 'list index out of range'
            main_header = main_headers[i] if i < len(main_headers) else ""
            sub_header = sub_headers[i] if i < len(sub_headers) else ""
            role_nick_header = role_nicks_headers[i] if i < len(role_nicks_headers) else ""

            if main_header and main_header != "":
                main_role = main_header
                
            if main_role:
                if sub_header == "Дата":
                    COLUMN_MAP[f"{main_role}-Дата"] = col_index
                elif sub_header == "Статус":
                    COLUMN_MAP[f"{main_role}-Статус"] = col_index
                elif role_nick_header and role_nick_header != "":
                    # Це колонка ніків під роллю
                    COLUMN_MAP[f"{main_role}-{role_nick_header}"] = col_index
                
            # Обробка колонок Тайтли та Розділ
            if role_nick_header == "Розділ №":
                COLUMN_MAP["Розділ №"] = col_index
            if main_header == "Тайтли":
                COLUMN_MAP["Тайтли"] = col_index
            if sub_header == "Дата дедлайну":
                COLUMN_MAP["Дата дедлайну"] = col_index
            if sub_header == "Статус" and main_header == "Публікація":
                COLUMN_MAP["Публікація-Статус"] = col_index
            
            col_index += 1

        logger.info("Карту колонок успішно ініціалізовано.")
    except Exception as e:
        logger.error(f"Невідома помилка при ініціалізації карти колонок: {e}")

def load_nickname_map():
    """Завантажує мапу нікнеймів користувачів з таблиці."""
    global NICKNAME_MAP, users_sheet
    if users_sheet is None:
        logger.warning("Аркуш 'Користувачі' не знайдено.")
        return
    try:
        data = users_sheet.get_all_records()
        NICKNAME_MAP = {row["Telegram-нік"]: row["Нік"] for row in data if "Telegram-нік" in row and "Нік" in row}
        logger.info("Мапу нікнеймів завантажено.")
    except Exception as e:
        logger.error(f"Помилка при завантаженні мапи нікнеймів: {e}")

def connect_to_google_sheets():
    """
    Підключається до Google Sheets та ініціалізує всі необхідні листи.
    """
    global client, main_spreadsheet, log_sheet, titles_sheet, users_sheet
    try:
        creds_path = os.path.join(os.path.dirname(__file__), '..', 'credentials.json')
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
        client = gspread.authorize(creds)
        main_spreadsheet = client.open("DataBase")
        log_sheet = main_spreadsheet.worksheet("Журнал")
        titles_sheet = main_spreadsheet.worksheet("Тайтли")
        users_sheet = main_spreadsheet.worksheet("Користувачі")
        logger.info("Успішно підключено до Google Sheets.")
        
        initialize_header_map()
        load_nickname_map()
        return True
    except Exception as e:
        logger.error(f"Помилка підключення до Google Sheets: {e}")
        return False

def find_title_block(title_name):
    """Шукає блок тайтлу в таблиці 'Тайтли' та повертає його діапазон рядків."""
    if titles_sheet is None:
        logger.error("Аркуш 'Тайтли' не ініціалізовано.")
        return None, None
    
    normalized_title = normalize_title(title_name)
    title_list = titles_sheet.col_values(COLUMN_MAP.get("Тайтли", 1))
    
    start_row = None
    for i, title in enumerate(title_list):
        if normalize_title(title) == normalized_title:
            start_row = i + 1
            break
            
    if start_row is None:
        logger.warning(f"Тайтл '{title_name}' не знайдено.")
        return None, None
    
    end_row = start_row + 4
    for i in range(start_row + 5, len(title_list) + 1):
        if i > len(title_list) or not title_list[i-1]:
            end_row = i - 1
            break
    if end_row == start_row + 4:
         end_row = len(title_list) + 1
         
    return start_row, end_row

def find_cell_by_role(title_name, chapter_number, role):
    """Шукає клітинку для певної ролі та розділу."""
    start_row, end_row = find_title_block(title_name)
    if start_row is None:
        return None

    chapter_col = COLUMN_MAP.get("Розділ №")
    if not chapter_col:
        logger.error("Колонка 'Розділ №' не знайдена в карті колонок.")
        return None

    row_to_update_index = None
    try:
        chapter_values = titles_sheet.col_values(chapter_col)[start_row + 3: end_row]
        for i, chapter in enumerate(chapter_values):
            if str(chapter).strip() == str(chapter_number).strip():
                row_to_update_index = start_row + 4 + i
                break
    except Exception as e:
        logger.error(f"Помилка при пошуку розділу: {e}")
        return None
    
    if row_to_update_index is None:
        logger.warning(f"Розділ {chapter_number} для тайтлу '{title_name}' не знайдено.")
        return None

    column_key = ROLE_MAPPING.get(role.lower())
    if not column_key:
        logger.error(f"Роль '{role}' не знайдена в ROLE_MAPPING.")
        return None

    column_index = COLUMN_MAP.get(column_key)
    if not column_index:
        logger.error(f"Колонка для ролі '{role}' не знайдена в карті колонок.")
        return None
    
    return titles_sheet.cell(row_to_update_index, column_index)


def update_cell(title, chapter, role, new_value):
    """Оновлює клітинку в таблиці."""
    if not COLUMN_MAP:
        logger.error("Карта колонок порожня. Оновлення неможливе.")
        return False
        
    cell = find_cell_by_role(title, chapter, role)
    if cell:
        try:
            titles_sheet.update_cell(cell.row, cell.col, new_value)
            return True
        except Exception as e:
            logger.error(f"Помилка оновлення клітинки: {e}")
            return False
    return False

def update_title_table(title, chapter, role, nickname):
    """Оновлює статус виконання завдання."""
    status_cell = find_cell_by_role(title, chapter, role)
    if status_cell:
        status_col = status_cell.col
        status_row = status_cell.row
        
        try:
            titles_sheet.update_cell(status_row, status_col, STATUS_DONE)
        except Exception as e:
            logger.error(f"Помилка оновлення статусу: {e}")
            return False
        
        date_col_key = role.lower() + "-Дата"
        date_col = COLUMN_MAP.get(date_col_key)
        if date_col:
            date_value = datetime.now().strftime('%d.%m.%Y')
            try:
                titles_sheet.update_cell(status_row, date_col, date_value)
            except Exception as e:
                logger.error(f"Помилка оновлення дати: {e}")
                return False
                
        nick_col_key = role.lower() + "-нік1" # Припускаємо, що нік1 це перша колонка з ніками
        nick_col = COLUMN_MAP.get(nick_col_key)
        if nick_col:
            try:
                current_nick = titles_sheet.cell(status_row, nick_col).value
                if not current_nick or current_nick.strip().lower() == nickname.strip().lower():
                    titles_sheet.update_cell(status_row, nick_col, nickname)
                else:
                    new_nick = f"{current_nick}, {nickname}"
                    titles_sheet.update_cell(status_row, nick_col, new_nick)
            except Exception as e:
                logger.error(f"Помилка оновлення нікнейму: {e}")
                return False

        return True
    return False

def get_user_sheet():
    """Повертає аркуш 'Користувачі'."""
    global users_sheet
    return users_sheet

def find_user_row_by_nick_or_tag(user_identifier):
    """Шукає рядок користувача за нікнеймом або тегом."""
    user_sheet = get_user_sheet()
    if not user_sheet:
        return None, None
    
    data = user_sheet.get_all_records()
    for i, row in enumerate(data):
        if row.get('Нік', '').lower() == user_identifier.lower() or \
           row.get('Telegram-нік', '').lower() == user_identifier.lower():
            return row, i + 2
    return None, None

def append_user_row(telegram_nick, telegram_tag, nickname, roles):
    """Додає нового користувача в таблицю 'Користувачі'."""
    user_sheet = get_user_sheet()
    if not user_sheet:
        return False
    
    try:
        new_row = [telegram_nick, telegram_tag, nickname, ", ".join(roles), datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
        user_sheet.append_row(new_row, value_input_option='USER_ENTERED')
        return True
    except Exception as e:
        logger.error(f"Помилка додавання нового користувача: {e}")
        return False

def update_user_row(row_index, telegram_nick, telegram_tag, nickname, roles):
    """Оновлює існуючий рядок користувача."""
    user_sheet = get_user_sheet()
    if not user_sheet:
        return False
        
    try:
        update_range = f'A{row_index}:E{row_index}'
        updated_row = [telegram_nick, telegram_tag, nickname, ", ".join(roles), datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
        user_sheet.update(update_range, [updated_row], value_input_option='USER_ENTERED')
        return True
    except Exception as e:
        logger.error(f"Помилка оновлення користувача: {e}")
        return False

def append_log_row(telegram_nick, telegram_tag, title, chapter, role, nickname):
    """Додає новий запис у журнал."""
    if log_sheet:
        try:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            log_sheet.append_row([timestamp, telegram_nick, telegram_tag, title, chapter, role, nickname])
            return True
        except Exception as e:
            logger.error(f"Помилка додавання запису в журнал: {e}")
            return False
    return False

def normalize_title(text):
    """Приводить назву тайтлу до єдиного формату для порівняння."""
    if text:
        return re.sub(r'[\s\W]+', '', text, flags=re.UNICODE).lower()
    return ""

def set_publish_status(title, chapter, status="Опубліковано"):
    """Встановлює статус публікації для розділу."""
    if not COLUMN_MAP:
        logger.error("Карта колонок порожня. Оновлення неможливе.")
        return "error", None
        
    publish_col = COLUMN_MAP.get("Публікація-Статус")
    if not publish_col:
        logger.error("Колонка 'Публікація-Статус' не знайдена в карті колонок.")
        return "error", None
    
    cell_to_update = find_cell_by_role(title, chapter, "клін")
    if cell_to_update:
        row_index = cell_to_update.row
        titles_sheet.update_cell(row_index, publish_col, status)
        return "success", title
    return "not_found", None

def set_main_roles(title, roles_map):
    """Встановлює відповідальних за тайтл."""
    if not COLUMN_MAP:
        logger.error("Карта колонок порожня. Встановлення ролей неможливе.")
        return False
    
    start_row, _ = find_title_block(title)
    if start_row is None:
        logger.warning(f"Тайтл '{title}' не знайдено для встановлення ролей.")
        return False

    header_row_to_update_idx = start_row + 3
    
    updates = []
    role_mapping_canon = {"клін": "Клін", "переклад": "Переклад", "тайп": "Тайп", "ред": "Редакт", "редакт": "Редакт"}
    
    for role, nicks_list in roles_map.items():
        canonical_role = role_mapping_canon.get(role.lower())
        if canonical_role and f"{canonical_role}-нік1" in COLUMN_MAP:
            col_idx = COLUMN_MAP[f"{canonical_role}-нік1"]
            resolved_nicks = [NICKNAME_MAP.get(nick, nick) for nick in nicks_list]
            nicknames_str = ", ".join(resolved_nicks)
            updates.append({
                'range': gspread.utils.rowcol_to_a1(header_row_to_update_idx, col_idx),
                'values': [[nicknames_str]]
            })
    
    if updates:
        try:
            titles_sheet.batch_update(updates)
            return True
        except Exception as e:
            logger.error(f"Помилка пакетного оновлення ролей: {e}")
            return False
    
    return True

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
        
        role_map = {v: k.split('-')[0] for k, v in COLUMN_MAP.items() if '-' in k}
        role_name = role_map.get(col_key_base)
        if role_name and cell.value:
            current_record[role_name.lower()] = cell.value

    if current_record:
        records.append(current_record)

    return original_title, records