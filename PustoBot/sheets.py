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
        header_rows = titles_sheet.get('A1:O2') # Отримуємо перші 2 рядки до колонки O
        main_headers = header_rows[0]
        sub_headers = header_rows[1]
        COLUMN_MAP.clear()
        
        current_main_header = None
        for i, header in enumerate(main_headers):
            if header:
                current_main_header = header
            
            # Якщо підзаголовок існує, використовуємо його, інакше - основний заголовок
            key = sub_headers[i] if len(sub_headers) > i and sub_headers[i] else current_main_header
            if key:
                COLUMN_MAP[key.strip()] = i + 1  # Зберігаємо індекс, починаючи з 1
        
        logger.info("Карту колонок успішно ініціалізовано.")
    except gspread.exceptions.APIError as api_e:
        logger.error(f"Помилка Google Sheets API при ініціалізації карти колонок: {api_e.response.text}")
    except Exception as e:
        logger.error(f"Невідома помилка при ініціалізації карти колонок: {e}")

def load_nickname_map():
    """Завантажує мапу нікнеймів користувачів з таблиці."""
    global NICKNAME_MAP, users_sheet
    users_sheet = get_user_sheet() # Отримуємо аркуш "Користувачі"
    if not users_sheet:
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
        return None
    
    normalized_title = normalize_title(title_name)
    title_list = titles_sheet.col_values(COLUMN_MAP.get("Тайтли", 1)) # Отримуємо всі тайтли
    
    start_row = None
    for i, title in enumerate(title_list):
        if normalize_title(title) == normalized_title:
            start_row = i + 1
            break
            
    if start_row is None:
        logger.warning(f"Тайтл '{title_name}' не знайдено.")
        return None, None
        
    end_row = start_row + 5  # Один рядок заголовка + 5 розділів
    # ... (інша логіка пошуку)
    return start_row, end_row

def find_cell_by_role(title_name, chapter_number, role):
    """Шукає клітинку для певної ролі та розділу."""
    start_row, end_row = find_title_block(title_name)
    if start_row is None:
        return None

    # ... (інша логіка)
    
    column_index = COLUMN_MAP.get(role)
    if not column_index:
        logger.error(f"Карта колонок порожня. Встановлення ролей неможливе.")
        return None
    
    # ... (інша логіка)


def update_cell(title, chapter, role, new_value):
    """Оновлює клітинку в таблиці."""
    if not COLUMN_MAP:
        logger.error("Карта колонок порожня. Оновлення неможливе.")
        return False
        
    cell = find_cell_by_role(title, chapter, role)
    if cell:
        # ... (інша логіка)
        return True
    return False

def update_title_table(title, chapter, role, nickname):
    """Оновлює статус виконання завдання."""
    # ... (інша логіка)

def get_user_sheet():
    """Повертає аркуш 'Користувачі'."""
    global users_sheet
    return users_sheet

def find_user_row_by_nick_or_tag(user_identifier):
    """Шукає рядок користувача за нікнеймом або тегом."""
    user_sheet = get_user_sheet()
    if not user_sheet:
        return None, None
    
    # ... (інша логіка)

def append_user_row(telegram_nick, telegram_tag, nickname, roles):
    """Додає нового користувача в таблицю 'Користувачі'."""
    user_sheet = get_user_sheet()
    if not user_sheet:
        return False
    
    # ... (інша логіка)

def update_user_row(row_index, telegram_nick, telegram_tag, nickname, roles):
    """Оновлює існуючий рядок користувача."""
    user_sheet = get_user_sheet()
    if not user_sheet:
        return False
        
    # ... (інша логіка)

def append_log_row(telegram_nick, telegram_tag, title, chapter, role, nickname):
    """Додає новий запис у журнал."""
    if log_sheet:
        # ... (інша логіка)
        return True
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
        return False
        
    publish_col = COLUMN_MAP.get("Опубліковано")
    if not publish_col:
        logger.error("Колонка 'Опубліковано' не знайдена в карті колонок.")
        return False
    
    # ... (інша логіка)

def set_main_roles(title, roles):
    """Встановлює відповідальних за тайтл."""
    if not COLUMN_MAP:
        logger.error("Карта колонок порожня. Встановлення ролей неможливе.")
        return False
    
    # ... (інша логіка)

def get_title_status_data(title_name):
    """Отримує всі дані по тайтлу для команди /status."""
    if not COLUMN_MAP:
        logger.error("Карта колонок порожня. Неможливо отримати статус.")
        return None
    
    # ... (інша логіка)