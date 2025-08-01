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
COLUMN_MAP = {} # Глобальна карта колонок
NICKNAME_MAP = {} # Глобальна карта нікнеймів

def initialize_header_map():
    """
    Читає перші два рядки таблиці 'Тайтли' і створює глобальну карту колонок.
    Ця функція має викликатись один раз при старті бота.
    """
    global COLUMN_MAP
    if titles_sheet is None:
        logger.error("Аркуш 'Тайтли' не ініціалізовано. Неможливо створити карту колонок.")
        return
    try:
        header_rows = titles_sheet.get('A1:O2')
        main_headers = header_rows[0]
        sub_headers = header_rows[1] if len(header_rows) > 1 else []
        COLUMN_MAP.clear()
        
        current_main_header = None
        for i, header in enumerate(main_headers):
            if header:
                current_main_header = header
            
            key = sub_headers[i] if i < len(sub_headers) and sub_headers[i] else current_main_header
            if key:
                COLUMN_MAP[key.strip()] = i + 1
        
        logger.info("Карту колонок успішно ініціалізовано.")
    except gspread.exceptions.APIError as api_e:
        logger.error(f"Помилка Google Sheets API при ініціалізації карти колонок: {api_e.response.text}")
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
        
    end_row = start_row
    # знаходимо кінець блоку тайтлу (порожній рядок)
    for i in range(start_row + 1, len(title_list) + 1):
        if i > len(title_list) or not title_list[i-1]:
            end_row = i - 1
            break
    if end_row == start_row:
         end_row = len(title_list) + 1
         
    return start_row, end_row

def find_cell_by_role(title_name, chapter_number, role):
    """Шукає клітинку для певної ролі та розділу."""
    start_row, end_row = find_title_block(title_name)
    if start_row is None:
        return None

    # Номера розділів знаходяться в стовпці "№"
    chapter_col = COLUMN_MAP.get("№")
    if not chapter_col:
        logger.error("Колонка '№' не знайдена в карті колонок.")
        return None

    # Шукаємо рядок з потрібним номером розділу
    row_to_update_index = None
    all_chapters = titles_sheet.col_values(chapter_col, value_render_option='FORMATTED_VALUE')[start_row-1:end_row-1]
    
    for i, chapter in enumerate(all_chapters):
        if str(chapter).strip() == str(chapter_number).strip():
            row_to_update_index = start_row + i
            break
    
    if row_to_update_index is None:
        logger.warning(f"Розділ {chapter_number} для тайтлу '{title_name}' не знайдено.")
        return None

    column_index = COLUMN_MAP.get(role)
    if not column_index:
        logger.error(f"Карта колонок порожня. Встановлення ролей неможливе.")
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
            cell.value = new_value
            titles_sheet.update_cells([cell])
            return True
        except Exception as e:
            logger.error(f"Помилка оновлення клітинки: {e}")
            return False
    return False

def update_title_table(title, chapter, role, nickname):
    """Оновлює статус виконання завдання."""
    cell_to_update = find_cell_by_role(title, chapter, role)
    if cell_to_update:
        current_value = cell_to_update.value
        # Якщо клітинка порожня, встановлюємо новий нікнейм
        if not current_value:
            return update_cell(title, chapter, role, nickname)
        # Якщо клітинка вже містить дані, перевіряємо, чи нікнейм співпадає
        elif current_value.strip().lower() == nickname.strip().lower():
            return True # нічого не робимо, оновлення не потрібне
        # Якщо нікнейм інший, додаємо його через кому
        else:
            new_value = f"{current_value}, {nickname}"
            return update_cell(title, chapter, role, new_value)
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
            return row, i + 2 # +2, бо get_all_records починає з 0, а рядок 1 — це заголовки
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
        
    publish_col = COLUMN_MAP.get("Опубліковано")
    if not publish_col:
        logger.error("Колонка 'Опубліковано' не знайдена в карті колонок.")
        return "error", None
    
    cell_to_update = find_cell_by_role(title, chapter, "№") # Знаходимо рядок по номеру розділу
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
    
    # Використовуємо глобальну мапу нікнеймів
    global NICKNAME_MAP
    
    start_row, _ = find_title_block(title)
    if start_row is None:
        logger.warning(f"Тайтл '{title}' не знайдено для встановлення ролей.")
        return False

    header_row_to_update_idx = start_row + 1 # +1 для рядка з ролями
    
    updates = []
    # Канонічна мапа ролей для уникнення помилок
    role_mapping_canon = {"клін": "Клін", "переклад": "Переклад", "тайп": "Тайп", "ред": "Редакт", "редакт": "Редакт"}
    
    for role, nicks_list in roles_map.items():
        canonical_role = role_mapping_canon.get(role.lower())
        if canonical_role and canonical_role in COLUMN_MAP:
            col_idx = COLUMN_MAP[canonical_role]
            # Розв'язуємо нікнейм за допомогою глобальної мапи
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
        
    title_name_cell = titles_sheet.cell(start_row, COLUMN_MAP["Тайтли"])
    original_title = title_name_cell.value
    
    data_range = titles_sheet.range(start_row + 1, 1, end_row, len(COLUMN_MAP))
    
    records = []
    current_record = {}
    
    for cell in data_range:
        col_name = titles_sheet.cell(start_row + 1, cell.col).value
        # Обробляємо підзаголовки
        if col_name is None or col_name == "":
            col_name = titles_sheet.cell(start_row, cell.col).value
        
        # Перевіряємо, чи починається новий рядок
        if cell.col == 1:
            if current_record:
                records.append(current_record)
            current_record = {"chapter": cell.value, "published": False}
        
        if col_name == "Опубліковано" and cell.value == "Опубліковано":
            current_record["published"] = True
        
        # Додаємо дані інших ролей, якщо вони є
        if col_name and cell.value and col_name not in ["Тайтли", "№", "Опубліковано"]:
            current_record[col_name.lower()] = cell.value

    # Додаємо останній запис
    if current_record:
        records.append(current_record)

    return original_title, records