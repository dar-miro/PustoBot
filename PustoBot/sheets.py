# PustoBot/sheets.py
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
import re
import logging
import os
import json
import requests
from collections import defaultdict # Додано імпорт

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
    return re.sub(r'[^\w\s]', '', title).lower().strip()

def initialize_header_map():
    """
    Читає заголовки таблиці 'Тайтли' і створює глобальну карту колонок.
    """
    global COLUMN_MAP
    if titles_sheet is None:
        logger.error("Аркуш 'Тайтли' не ініціалізовано. Неможливо створити карту колонок.")
        return False

    try:
        headers_all = titles_sheet.get_all_values()
        if len(headers_all) < 4:
            logger.error("Недостатньо рядків для заголовків. Очікується мінімум 4.")
            return False

        header_row_1 = headers_all[0]
        header_row_3 = headers_all[2]
        header_row_4 = headers_all[3]

        COLUMN_MAP = {}
        
        # 1. Фіксовані колонки
        COLUMN_MAP["Номер Тайтлу"] = COLUMN_TITLE_NUMBER # Колонка A
        
        try:
             # Нова логіка: шукаємо "Тайтли" у рядку 1, він має бути в B1 (індекс 1)
             titles_col_index = header_row_1.index("Тайтли") + 1
             COLUMN_MAP["Тайтли"] = titles_col_index
        except ValueError:
            logger.error("Не знайдено колонку 'Тайтли'.")
            return False

        # Номер Розділу знаходиться у колонці Тайтлів для рядків розділів (B)
        COLUMN_MAP["Розділ №"] = COLUMN_MAP["Тайтли"]

        # 2. Рольові колонки
        role_base_indices = {}
        for i, header in enumerate(header_row_1):
            if header.strip() in ROLE_MAPPING.values():
                role_base_indices[header.strip()] = i
            if header.strip() == "Публікація":
                role_base_indices["Публікація"] = i

        role_names_list = ["Клін", "Переклад", "Тайп", "Редакт"]
        for role_name in role_names_list:
            if role_name in role_base_indices:
                col_start_index = role_base_indices[role_name]
                
                col_end_index = len(header_row_1)
                for next_role in role_names_list:
                    if next_role != role_name and next_role in role_base_indices and role_base_indices[next_role] > col_start_index:
                        col_end_index = min(col_end_index, role_base_indices[next_role])
                
                try:
                    # Шукаємо підзаголовки
                    sub_header_slice_row3 = header_row_3[col_start_index:col_end_index]
                    sub_header_slice_row4 = header_row_4[col_start_index:col_end_index]
                    
                    if "Нік" in sub_header_slice_row4:
                        col_index = sub_header_slice_row4.index("Нік") + col_start_index
                        COLUMN_MAP[f"{role_name}-Нік"] = col_index + 1
                    if "Дата" in sub_header_slice_row3:
                        col_index_date = sub_header_slice_row3.index("Дата") + col_start_index
                        COLUMN_MAP[f"{role_name}-Дата"] = col_index_date + 1
                    if "Статус" in sub_header_slice_row3:
                        col_index_status = sub_header_slice_row3.index("Статус") + col_start_index
                        COLUMN_MAP[f"{role_name}-Статус"] = col_index_status + 1
                except ValueError as e:
                    logger.warning(f"Не вдалося знайти підзаголовки для ролі '{role_name}': {e}")
        
        # Публікація
        if "Публікація" in role_base_indices:
            publish_col_start = role_base_indices["Публікація"]
            # Обрізаємо до кінця рядка
            publish_slice_row3 = header_row_3[publish_col_start:] 
            publish_slice_row4 = header_row_4[publish_col_start:] 
            
            try:
                # Шукаємо дату дедлайну
                col_index_deadline = -1
                if "Дата дедлайну" in publish_slice_row4:
                    col_index_deadline = publish_slice_row4.index("Дата дедлайну") + publish_col_start
                elif "Дата дедлайну" in publish_slice_row3:
                    col_index_deadline = publish_slice_row3.index("Дата дедлайну") + publish_col_start
                if col_index_deadline != -1:
                    COLUMN_MAP["Публікація-Дата дедлайну"] = col_index_deadline + 1

                # Шукаємо статус публікації
                col_index_status = -1
                if "Статус" in publish_slice_row4:
                    col_index_status = publish_slice_row4.index("Статус") + publish_col_start
                elif "Статус" in publish_slice_row3:
                    col_index_status = publish_slice_row3.index("Статус") + publish_col_start
                if col_index_status != -1:
                    COLUMN_MAP["Публікація-Статус"] = col_index_status + 1
            except ValueError:
                logger.warning("Не вдалося знайти дату дедлайну або статус публікації.")

        logger.info(f"Карта колонок успішно ініціалізована: {COLUMN_MAP}")
        return True
    except Exception as e:
        logger.error(f"Помилка при ініціалізації карти колонок: {e}")
        return False

# ... (load_nickname_map і connect_to_google_sheets залишаються)

def load_nickname_map():
    """Завантажує мапу нікнеймів з аркуша 'Користувачі'."""
    global NICKNAME_MAP
    if users_sheet is None:
        logger.error("Аркуш 'Користувачі' не ініціалізовано.")
        return False

    try:
        users = users_sheet.get_all_values()
        if not users or len(users) < 2:
            logger.warning("Аркуш 'Користувачі' порожній.")
            return False

        # Оновлено: використовуємо Telegram-тег (колонка 2, індекс 1) як ключ
        NICKNAME_MAP = {row[1].strip().lower().lstrip('@'): row[2] for row in users[1:] if len(row) > 2 and row[1] and row[2]}
        logger.info("Мапа нікнеймів успішно завантажена.")
        return True
    except Exception as e:
        logger.error(f"Помилка при завантаженні мапи нікнеймів: {e}")
        return False

def connect_to_google_sheets():
    """
    Підключається до Google Sheets, використовуючи файл credentials.json.
    """
    global client, main_spreadsheet, log_sheet, titles_sheet, users_sheet
    try:
        # 🆕 Змінено: Тепер код читає файл напряму
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
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
    except FileNotFoundError:
        logger.error("Помилка: Файл 'credentials.json' не знайдено.")
        return False
    except gspread.exceptions.SpreadsheetNotFound:
        logger.error("Помилка: Не знайдено спредшит з назвою 'DataBase'. Перевірте назву.")
        return False
    except gspread.exceptions.WorksheetNotFound as e:
        logger.error(f"Помилка: Не знайдено один з аркушів: {e}. Перевірте назви аркушів.")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Помилка мережі при підключенні: {e}")
        return False
    except Exception as e:
        logger.error(f"Невідома помилка підключення: {e}")
        return False

def find_title_block(title_identifier):
    """
    Шукає блок тайтлу за його ідентифікатором (Номер Тайтлу або Назва Тайтлу).
    Повертає: (start_row, end_row, title_name)
    """
    try:
        # Перевіряємо, чи ідентифікатор є номером тайтлу
        is_number_search = title_identifier.isdigit()
        
        titles_col_values = titles_sheet.col_values(COLUMN_MAP["Тайтли"]) # Колонка B
        number_col_values = titles_sheet.col_values(COLUMN_MAP["Номер Тайтлу"]) # Колонка A
        
        start_index = -1 # Індекс у списку (від 0)

        if is_number_search:
            # Шукаємо за Номером Тайтлу (Колонка A)
            try:
                start_index = next(i for i, v in enumerate(number_col_values) if v.strip() == title_identifier)
            except StopIteration:
                logger.warning(f"Тайтл з номером '{title_identifier}' не знайдено.")
                return None, None, None
        else:
            # Шукаємо за Назвою Тайтлу (Колонка B)
            normalized_name = normalize_title(title_identifier)
            try:
                start_index = next(i for i, v in enumerate(titles_col_values) if normalize_title(v) == normalized_name)
            except StopIteration:
                logger.warning(f"Тайтл '{title_identifier}' не знайдено.")
                return None, None, None
            
        start_row = start_index + 1
        
        # Назва тайтлу (завжди беремо з колонки "Тайтли", тобто B)
        title_name = titles_col_values[start_index] if len(titles_col_values) > start_index else title_identifier
            
        # Знаходимо кінець блоку (перший порожній рядок у колонці Номер Тайтлу)
        end_index = start_index
        for i in range(start_index + 1, len(number_col_values)):
            # Перевіряємо на порожній рядок у колонці Номер Тайтлу
            if not number_col_values[i]: 
                end_index = i - 1
                break
            else:
                end_index = i
        
        end_row = end_index + 1
        
        logger.info(f"Знайдено тайтл '{title_name}' у рядку {start_row}. Блок закінчується на рядку {end_row}.")
        return start_row, end_row, title_name

    except Exception as e:
        logger.error(f"Помилка при пошуку блоку тайтлу: {e}")
        return None, None, None

def find_chapter_row_in_block(start_row, end_row, chapter_number):
    """Шукає рядок розділу всередині блоку тайтлу."""
    try:
        chapter_col = COLUMN_MAP["Розділ №"] # Це колонка B (Тайтли/Розділ №)
        
        # Дані розділів починаються з 5-го рядка блоку (start_row + 4, бо 4 рядки шапки)
        start_data_row = start_row + 4 
        range_string = f"{gspread.utils.rowcol_to_a1(start_data_row, chapter_col)}:{gspread.utils.rowcol_to_a1(end_row, chapter_col)}"
        chapter_col_values = titles_sheet.range(range_string)
        
        for cell in chapter_col_values:
            if cell.value and cell.value.strip() == str(chapter_number):
                return cell.row
        return None
    except Exception as e:
        logger.error(f"Помилка при пошуку рядка розділу: {e}")
        return None

def update_title_table(title_identifier, chapter_number, role, nickname_to_set=None):
    """
    Оновлює статус та дату для заданого тайтлу, розділу та ролі, використовуючи ідентифікатор.
    """
    if not titles_sheet:
        logger.error("Аркуш 'Тайтли' не ініціалізовано.")
        return False

    if role not in ROLE_MAPPING:
        logger.warning(f"Невідома роль: {role}")
        return False
        
    start_row, end_row, _ = find_title_block(title_identifier)
    if not start_row:
        return False

    chapter_row = find_chapter_row_in_block(start_row, end_row, chapter_number)
    if not chapter_row:
        logger.warning(f"Розділ '{chapter_number}' не знайдено для тайтлу '{title_identifier}'.")
        return False

    try:
        role_base_name = ROLE_MAPPING[role]
        updates = []
        
        if nickname_to_set and f"{role_base_name}-Нік" in COLUMN_MAP:
            updates.append({'range': gspread.utils.rowcol_to_a1(chapter_row, COLUMN_MAP[f"{role_base_name}-Нік"]), 'values': [[nickname_to_set]]})
            logger.info(f"Оновлено нікнейм для ролі '{role_base_name}': {nickname_to_set}")
        
        if f"{role_base_name}-Дата" in COLUMN_MAP:
            current_date = datetime.now().strftime("%d.%m.%Y")
            updates.append({'range': gspread.utils.rowcol_to_a1(chapter_row, COLUMN_MAP[f"{role_base_name}-Дата"]), 'values': [[current_date]]})
            logger.info(f"Оновлено дату для ролі '{role_base_name}': {current_date}")
            
        if f"{role_base_name}-Статус" in COLUMN_MAP:
            updates.append({'range': gspread.utils.rowcol_to_a1(chapter_row, COLUMN_MAP[f"{role_base_name}-Статус"]), 'values': [[STATUS_DONE]]})
            logger.info(f"Оновлено статус для ролі '{role_base_name}': {STATUS_DONE}")

        if updates:
            titles_sheet.batch_update(updates)
            
        return True
    except Exception as e:
        logger.error(f"Помилка при оновленні таблиці: {e}")
        return False

def resolve_user_nickname(telegram_tag):
    """
    Повертає нікнейм користувача з таблиці, використовуючи його Telegram-тег.
    """
    normalized_tag = telegram_tag.lower().lstrip('@')
    return NICKNAME_MAP.get(normalized_tag)

def set_publish_status(title_identifier, chapter_number):
    """Оновлює статус публікації розділу."""
    if not titles_sheet:
        return "error", "Аркуш 'Тайтли' не ініціалізовано."

    start_row, end_row, title_name = find_title_block(title_identifier)
    if not start_row:
        return "not_found", f"Тайтл '{title_identifier}' не знайдено."
        
    chapter_row = find_chapter_row_in_block(start_row, end_row, chapter_number)
    if not chapter_row:
        return "not_found", f"Розділ '{chapter_number}' не знайдено."

    try:
        publish_status_col = COLUMN_MAP["Публікація-Статус"]
        titles_sheet.update_cell(chapter_row, publish_status_col, PUBLISHED_DONE)
        
        return "success", title_name
    except Exception as e:
        logger.error(f"Помилка при оновленні статусу публікації: {e}")
        return "error", f"Помилка при оновленні статусу публікації: {e}"

def get_title_status_data(title_identifier):
    """Отримує всі дані по тайтлу для команди /status."""
    if not titles_sheet or not COLUMN_MAP:
        logger.error("Неініціалізовані ресурси для отримання статусу.")
        return None, None
    
    start_row, end_row, original_title = find_title_block(title_identifier)
    if start_row is None:
        return None, None
        
    # Дані починаються з 5-го рядка блоку
    data_range_start_row = start_row + 4 
    # Отримуємо дані починаючи з колонки Розділ № (B)
    range_start_col = COLUMN_MAP["Розділ №"]
    
    # Використовуємо B:ОстанняКолонка
    data_range = titles_sheet.range(f'{gspread.utils.rowcol_to_a1(data_range_start_row, range_start_col)}:{gspread.utils.rowcol_to_a1(end_row, titles_sheet.col_count)}')
    
    status_report = []
    
    for row_data in data_range:
        # row_data[0] - це Номер Розділу (колонка B у діапазоні)
        if not row_data[0].value:
            continue
            
        chapter_number = row_data[0].value
        record = {"chapter": chapter_number, "published": False, "roles": {}}
        
        # Зсув від початку діапазону (range_start_col) до початку аркуша (колонка 1)
        range_offset = range_start_col - 1 

        for role_key, col_key in ROLE_MAPPING.items():
            role_base_name = ROLE_MAPPING[role_key]
            status_col_index = COLUMN_MAP.get(f"{role_base_name}-Статус")
            
            if status_col_index is not None:
                # Локальний індекс у рядку даних: глобальний_індекс - зсув_діапазону
                local_index = status_col_index - range_offset
                
                if local_index >= 0 and local_index < len(row_data):
                    status_value = row_data[local_index].value
                    record["roles"][role_key] = status_value == STATUS_DONE

        if "Публікація-Статус" in COLUMN_MAP:
            publish_status_col_index = COLUMN_MAP["Публікація-Статус"]
            local_index = publish_status_col_index - range_offset
            
            if local_index >= 0 and local_index < len(row_data):
                publish_status_value = row_data[local_index].value
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

# Додаткові функції для роботи з Номером Тайтлу
def get_title_name_by_number(title_number):
    """Отримує назву тайтлу за його номером."""
    if not titles_sheet:
        return None
    try:
        col_A = titles_sheet.col_values(COLUMN_MAP["Номер Тайтлу"])
        col_B = titles_sheet.col_values(COLUMN_MAP["Тайтли"]) 
        
        try:
            row_index = next(i for i, v in enumerate(col_A) if v.strip() == str(title_number))
            return col_B[row_index] if len(col_B) > row_index else None
        except StopIteration:
            return None
    except Exception as e:
        logger.error(f"Помилка при отриманні назви тайтлу за номером: {e}")
        return None

def get_title_number_and_name(title_identifier):
    """Повертає (номер, назва) для тайтлу."""
    if not titles_sheet:
        return None, None
        
    start_row, _, title_name = find_title_block(title_identifier)
    if start_row:
        try:
            title_number = titles_sheet.cell(start_row, COLUMN_MAP["Номер Тайтлу"]).value
            return title_number, title_name
        except Exception as e:
            logger.error(f"Помилка при отриманні номера та назви: {e}")
            return None, None
    return None, None


def set_main_roles(title_number, roles_map):
    """Зберігає відповідальних за тайтл, використовуючи Номер Тайтлу."""
    if not titles_sheet:
        logger.error("Аркуш 'Тайтли' не ініціалізовано.")
        return False
    
    # Використовуємо Номер Тайтлу для пошуку
    start_row, _, _ = find_title_block(title_number) 
    if not start_row:
        logger.warning(f"Тайтл з номером '{title_number}' не знайдено для збереження ролей.")
        return False

    # Ніки знаходяться у рядку start_row + 1 (2-й рядок блоку)
    nick_row = start_row + 1

    try:
        updates = []
        for role, nick in roles_map.items():
            if role in ROLE_MAPPING:
                # Отримуємо базове ім'я ролі (наприклад, 'Клін' з 'Клін-Статус')
                role_base_name = ROLE_MAPPING[role]
                if f"{role_base_name}-Нік" in COLUMN_MAP:
                    col = COLUMN_MAP[f"{role_base_name}-Нік"]
                    updates.append({'range': gspread.utils.rowcol_to_a1(nick_row, col), 'values': [[nick]]})
        
        if updates:
            titles_sheet.batch_update(updates)
        return True
    except Exception as e:
        logger.error(f"Помилка при збереженні ролей: {e}")
        return False
        
# ... (решта функцій для користувачів залишаються)
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