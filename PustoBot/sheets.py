# PustoBot/sheets.py
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
import re
import logging
import os
from collections import defaultdict
import requests

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
STATUS_DONE = "✔️"
STATUS_TODO = "❌"
PUBLISHED_DONE = "✔️"
PUBLISHED_TODO = "❌"

def normalize_title(title):
    return re.sub(r'[^\w\s]', '', title).lower().strip()

def initialize_header_map():
    """
    Читає заголовки таблиці 'Тайтли' і створює глобальну карту колонок.
    Логіка переписана для надійного пошуку в багаторядкових заголовках.
    """
    global COLUMN_MAP
    if titles_sheet is None:
        logger.error("Аркуш 'Тайтли' не ініціалізовано. Неможливо створити карту колонок.")
        return False

    try:
        # Читаємо перші 4 рядки, щоб отримати всі заголовки
        headers = titles_sheet.get_all_values()
        if len(headers) < 4:
            logger.error("Недостатньо рядків для заголовків. Очікується мінімум 4.")
            return False

        header_row_1 = headers[0]
        header_row_3 = headers[2]
        header_row_4 = headers[3]

        COLUMN_MAP = {}

        # Визначаємо індекси головних заголовків ролей
        role_base_cols = {}
        try:
            role_base_cols["Тайтли"] = header_row_1.index("Тайтли")
            role_base_cols["Клін"] = header_row_1.index("Клін")
            role_base_cols["Переклад"] = header_row_1.index("Переклад")
            role_base_cols["Тайп"] = header_row_1.index("Тайп")
            role_base_cols["Редакт"] = header_row_1.index("Редакт")
            role_base_cols["Публікація"] = header_row_1.index("Публікація")
        except ValueError as e:
            logger.error(f"Не вдалося знайти один з головних заголовків: {e}")
            return False

        # Обробка заголовків ролей та підзаголовків
        role_names = ["Клін", "Переклад", "Тайп", "Редакт"]
        for role_name in role_names:
            col_start_index = role_base_cols[role_name]

            # Знаходимо кінець діапазону для поточної ролі
            col_end_index = len(header_row_1)
            next_role_indices = [v for k, v in role_base_cols.items() if v > col_start_index]
            if next_role_indices:
                col_end_index = min(next_role_indices)

            # Знаходимо підзаголовки "Нік", "Дата" та "Статус"
            try:
                sub_header_slice_row3 = header_row_3[col_start_index:col_end_index]
                sub_header_slice_row4 = header_row_4[col_start_index:col_end_index]

                # Для "Нік" ми шукаємо в рядку 4 (header_row_4)
                if role_name in sub_header_slice_row4:
                    col_index = sub_header_slice_row4.index(role_name) + col_start_index
                    COLUMN_MAP[f"{role_name}-Нік"] = col_index + 1
                
                # Для "Дата" та "Статус" ми шукаємо в рядку 3 (header_row_3)
                if "Дата" in sub_header_slice_row3:
                    col_index_date = sub_header_slice_row3.index("Дата") + col_start_index
                    COLUMN_MAP[f"{role_name}-Дата"] = col_index_date + 1

                if "Статус" in sub_header_slice_row3:
                    col_index_status = sub_header_slice_row3.index("Статус") + col_start_index
                    COLUMN_MAP[f"{role_name}-Статус"] = col_index_status + 1
            except ValueError as e:
                logger.warning(f"Не вдалося знайти підзаголовки для ролі '{role_name}': {e}")
        
        # Обробка Публікації
        publish_col_start = role_base_cols["Публікація"]
        publish_slice_row3 = header_row_3[publish_col_start:]
        
        try:
            col_index_deadline = publish_slice_row3.index("Дата дедлайну") + publish_col_start
            COLUMN_MAP["Публікація-Дата дедлайну"] = col_index_deadline + 1
        except ValueError:
            logger.warning("Не вдалося знайти дату дедлайну.")

        try:
            col_index_status = publish_slice_row3.index("Статус") + publish_col_start
            COLUMN_MAP["Публікація-Статус"] = col_index_status + 1
        except ValueError:
            logger.warning("Не вдалося знайти статус публікації.")

        # Обробка інших заголовків
        try:
            COLUMN_MAP["Тайтли"] = role_base_cols["Тайтли"] + 1
            COLUMN_MAP["Розділ №"] = header_row_4.index("Розділ №") + 1
        except ValueError as e:
            logger.error(f"Не вдалося знайти ключові заголовки: {e}")
            return False

        logger.info(f"Карта колонок успішно ініціалізована: {COLUMN_MAP}")
        return True
    except Exception as e:
        logger.error(f"Помилка при ініціалізації карти колонок: {e}")
        return False

def load_nickname_map():
    """Завантажує мапу нікнеймів з аркуша 'Користувачі'."""
    global NICKNAME_MAP
    if users_sheet is None:
        logger.error("Аркуш 'Користувачі' не ініціалізовано.")
        return False

    try:
        users = users_sheet.get_all_values()
        if not users:
            logger.warning("Аркуш 'Користувачі' порожній.")
            return False

        NICKNAME_MAP = {row[1].lower(): row[2] for row in users[1:] if len(row) > 2 and row[1] and row[2]}
        logger.info("Мапа нікнеймів успішно завантажена.")
        return True
    except Exception as e:
        logger.error(f"Помилка при завантаженні мапи нікнеймів: {e}")
        return False

def connect_to_google_sheets():
    """Підключається до Google Sheets і ініціалізує глобальні змінні."""
    global client, main_spreadsheet, log_sheet, titles_sheet, users_sheet
    try:
        creds_path = os.path.join(os.path.dirname(__file__), '..', 'credentials.json')
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
        client = gspread.authorize(creds)
        logger.info("Авторизація Google Sheets успішна.")
        
        main_spreadsheet = client.open("DataBase")
        
        log_sheet = main_spreadsheet.worksheet("Журнал")
        titles_sheet = main_spreadsheet.worksheet("Тайтли")
        users_sheet = main_spreadsheet.worksheet("Користувачі")
        
        logger.info("Всі робочі аркуші знайдено.")
        
        if not initialize_header_map():
            return False
            
        if not load_nickname_map():
            return False
            
        return True
    except gspread.exceptions.SpreadsheetNotFound:
        logger.error("Помилка: Не знайдено спредшит з назвою 'DataBase'. Перевірте назву.")
        return False
    except gspread.exceptions.WorksheetNotFound as e:
        logger.error(f"Помилка: Не знайдено один з аркушів: {e}. Перевірте назви аркушів.")
        return False
    except FileNotFoundError:
        logger.error("Помилка: Файл credentials.json не знайдено.")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Помилка мережі при підключенні: {e}")
        return False
    except Exception as e:
        logger.error(f"Невідома помилка підключення: {e}")
        return False

def find_title_block(title_name):
    """Шукає блок тайтлу за його назвою. Логіка виправлена для пошуку за порожнім рядком-роздільником."""
    try:
        normalized_name = normalize_title(title_name)
        
        titles_col_values = titles_sheet.col_values(COLUMN_MAP["Тайтли"])
        
        try:
            start_index = next(i for i, v in enumerate(titles_col_values) if normalize_title(v) == normalized_name)
            start_row = start_index + 1
        except StopIteration:
            logger.warning(f"Тайтл '{title_name}' не знайдено.")
            return None, None
            
        end_index = start_index
        for i in range(start_index + 1, len(titles_col_values)):
            if not titles_col_values[i]:
                end_index = i - 1
                break
            else:
                end_index = i
        
        end_row = end_index + 1
        
        logger.info(f"Знайдено тайтл '{title_name}' у рядку {start_row}. Блок закінчується на рядку {end_row}.")
        return start_row, end_row

    except Exception as e:
        logger.error(f"Помилка при пошуку блоку тайтлу: {e}")
        return None, None

def find_chapter_row_in_block(start_row, end_row, chapter_number):
    """Шукає рядок розділу всередині блоку тайтлу."""
    try:
        chapter_col_values = titles_sheet.range(f'B{start_row + 1}:B{end_row}')
        for cell in chapter_col_values:
            if cell.value and cell.value.strip() == str(chapter_number):
                return cell.row
        return None
    except Exception as e:
        logger.error(f"Помилка при пошуку рядка розділу: {e}")
        return None

def update_title_table(title_name, chapter_number, role, nickname=None):
    """Оновлює статус та дату для заданого тайтлу, розділу та ролі, а також записує нік виконавця."""
    if not titles_sheet:
        logger.error("Аркуш 'Тайтли' не ініціалізовано.")
        return False

    if role not in ROLE_MAPPING:
        logger.warning(f"Невідома роль: {role}")
        return False
        
    start_row, end_row = find_title_block(title_name)
    if not start_row:
        return False

    chapter_row = find_chapter_row_in_block(start_row, end_row, chapter_number)
    if not chapter_row:
        logger.warning(f"Розділ '{chapter_number}' не знайдено для тайтлу '{title_name}'.")
        return False

    try:
        role_base_name = ROLE_MAPPING[role]
        updates = []
        
        # Оновлюємо нікнейм виконавця
        if nickname and f"{role_base_name}-Нік" in COLUMN_MAP:
            updates.append({'range': gspread.utils.rowcol_to_a1(chapter_row, COLUMN_MAP[f"{role_base_name}-Нік"]), 'values': [[nickname]]})
        
        # Оновлюємо дату
        if f"{role_base_name}-Дата" in COLUMN_MAP:
            current_date = datetime.now().strftime("%d.%m.%Y")
            updates.append({'range': gspread.utils.rowcol_to_a1(chapter_row, COLUMN_MAP[f"{role_base_name}-Дата"]), 'values': [[current_date]]})
            
        # Оновлюємо статус
        if f"{role_base_name}-Статус" in COLUMN_MAP:
            updates.append({'range': gspread.utils.rowcol_to_a1(chapter_row, COLUMN_MAP[f"{role_base_name}-Статус"]), 'values': [[STATUS_DONE]]})

        if updates:
            titles_sheet.batch_update(updates)
            
        return True
    except Exception as e:
        logger.error(f"Помилка при оновленні таблиці: {e}")
        return False


def set_publish_status(title_name, chapter_number):
    """Оновлює статус публікації розділу."""
    if not titles_sheet:
        return "error", "Аркуш 'Тайтли' не ініціалізовано."

    start_row, end_row = find_title_block(title_name)
    if not start_row:
        return "not_found", f"Тайтл '{title_name}' не знайдено."
        
    chapter_row = find_chapter_row_in_block(start_row, end_row, chapter_number)
    if not chapter_row:
        return "not_found", f"Розділ '{chapter_number}' не знайдено."

    try:
        publish_status_col = COLUMN_MAP["Публікація-Статус"]
        titles_sheet.update_cell(chapter_row, publish_status_col, PUBLISHED_DONE)
        
        original_title = titles_sheet.cell(start_row, COLUMN_MAP["Тайтли"]).value
        return "success", original_title
    except Exception as e:
        logger.error(f"Помилка при оновленні статусу публікації: {e}")
        return "error", f"Помилка при оновленні статусу публікації: {e}"


def get_title_status_data(title_name):
    """Отримує всі дані по тайтлу для команди /status."""
    if not titles_sheet or not COLUMN_MAP:
        logger.error("Неініціалізовані ресурси для отримання статусу.")
        return None, None
    
    start_row, end_row = find_title_block(title_name)
    if start_row is None:
        return None, None
        
    original_title = titles_sheet.cell(start_row, COLUMN_MAP["Тайтли"]).value
    
    data_range_start_row = start_row + 1
    data_range = titles_sheet.range(f'A{data_range_start_row}:{gspread.utils.rowcol_to_a1(end_row, titles_sheet.col_count)}')
    
    status_report = []
    
    for row_data in data_range:
        if not row_data[0].value:
            continue
            
        chapter_number = row_data[0].value
        record = {"chapter": chapter_number, "published": False, "roles": {}}
        
        for role_key, col_key in ROLE_MAPPING.items():
            status_col_index = COLUMN_MAP.get(f"{col_key}-Статус")
            if status_col_index is not None and len(row_data) > status_col_index - 1:
                status_value = row_data[status_col_index - 1].value
                record["roles"][role_key] = status_value == STATUS_DONE

        if "Публікація-Статус" in COLUMN_MAP:
            publish_status_col_index = COLUMN_MAP["Публікація-Статус"]
            if publish_status_col_index is not None and len(row_data) > publish_status_col_index - 1:
                publish_status_value = row_data[publish_status_col_index - 1].value
                record["published"] = publish_status_value == PUBLISHED_DONE

        status_report.append(record)
    
    return original_title, status_report

def append_log_row(telegram_nick, telegram_tag, title, chapter, role, user_nick):
    """Додає новий запис у журнал."""
    if not log_sheet:
        logger.error("Аркуш 'Журнал' не ініціалізовано.")
        return

    try:
        now = datetime.now()
        date_str = now.strftime("%d.%m.%Y %H:%M:%S")
        row = [date_str, telegram_nick, telegram_tag, title, chapter, role, user_nick]
        log_sheet.append_row(row)
    except Exception as e:
        logger.error(f"Помилка при додаванні запису в журнал: {e}")

def get_user_sheet():
    return users_sheet

def find_user_row_by_nick_or_tag(nickname, telegram_tag):
    """Шукає рядок користувача за ніком або тегом."""
    if users_sheet is None:
        logger.error("Аркуш 'Користувачі' не ініціалізовано.")
        return None
    try:
        users_data = users_sheet.get_all_values()
        for i, row in enumerate(users_data):
            if len(row) > 2 and row[2].strip().lower() == nickname.lower():
                return i + 1
            if len(row) > 1 and row[1].strip().lower() == telegram_tag.lower():
                return i + 1
        return None
    except Exception as e:
        logger.error(f"Помилка при пошуку користувача: {e}")
        return None

def update_user_row(row_index, telegram_nick, telegram_tag, user_nick, roles):
    """Оновлює рядок користувача."""
    if users_sheet is None:
        logger.error("Аркуш 'Користувачі' не ініціалізовано.")
        return False
    try:
        users_sheet.update(f'A{row_index}', [[telegram_nick, telegram_tag, user_nick, roles]])
        return True
    except Exception as e:
        logger.error(f"Помилка при оновленні рядка користувача: {e}")
        return False

def append_user_row(telegram_nick, telegram_tag, user_nick, roles):
    """Додає новий рядок з користувачем."""
    if users_sheet is None:
        logger.error("Аркуш 'Користувачі' не ініціалізовано.")
        return False
    try:
        users_sheet.append_row([telegram_nick, telegram_tag, user_nick, roles])
        return True
    except Exception as e:
        logger.error(f"Помилка при додаванні нового користувача: {e}")
        return False

def set_main_roles(title_name, roles_map):
    """Зберігає відповідальних за тайтл."""
    if not titles_sheet:
        logger.error("Аркуш 'Тайтли' не ініціалізовано.")
        return False
        
    start_row, _ = find_title_block(title_name)
    if not start_row:
        return False

    try:
        updates = []
        for role, nick in roles_map.items():
            if role in ROLE_MAPPING:
                role_base_name = ROLE_MAPPING[role]
                if f"{role_base_name}-Нік" in COLUMN_MAP:
                    col = COLUMN_MAP[f"{role_base_name}-Нік"]
                    # Оновлюємо нік в рядку, де знаходиться заголовок "Розділ №"
                    updates.append({'range': gspread.utils.rowcol_to_a1(start_row + 1, col), 'values': [[nick]]})
        
        if updates:
            titles_sheet.batch_update(updates)
        return True
    except Exception as e:
        logger.error(f"Помилка при збереженні ролей: {e}")
        return False