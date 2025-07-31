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
COLUMN_MAP = {} # Глобальна карта колонок

try:
    creds_path = os.path.join(os.path.dirname(__file__), '..', 'credentials.json')
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(creds)
    main_spreadsheet = client.open("DataBase")
    log_sheet = main_spreadsheet.worksheet("Журнал")
    titles_sheet = main_spreadsheet.worksheet("Тайтли")
    logger.info("Успішно підключено до Google Sheets.")
except Exception as e:
    logger.error(f"Помилка підключення до Google Sheets: {e}")

# --- Нова логіка ініціалізації та пошуку ---

def initialize_header_map():
    """
    Читає перші два рядки таблиці 'Тайтли' і створює глобальну карту колонок.
    Ця функція має викликатись один раз при старті бота.
    """
    if titles_sheet is None:
        logger.error("Аркуш 'Тайтли' не ініціалізовано. Неможливо створити карту колонок.")
        return

    try:
        header_rows = titles_sheet.get('A1:O2') # Отримуємо перші 2 рядки до колонки O
        main_headers = header_rows[0]
        sub_headers = header_rows[1]
        
        global COLUMN_MAP
        COLUMN_MAP.clear()
        
        current_main_header = None
        # defaultdict створює вкладений словник, якщо ключ ще не існує
        temp_map = defaultdict(dict)

        for i, main_header_val in enumerate(main_headers):
            # Якщо значення в основному заголовку не порожнє, встановлюємо його як поточний
            if main_header_val.strip():
                current_main_header = main_header_val.strip()
            
            # Якщо є поточний основний заголовок і підзаголовок не порожній
            if current_main_header and sub_headers[i].strip():
                # gspread використовує 1-індексацію, а Python 0-індексацію
                col_letter = gspread.utils.rowcol_to_a1(1, i + 1)[:-1]
                # Зберігаємо нормалізовані назви для легкого доступу
                temp_map[normalize_title(current_main_header)][normalize_title(sub_headers[i])] = i + 1 # Зберігаємо 1-based індекс колонки

        COLUMN_MAP = dict(temp_map)
        logger.info(f"Карту колонок успішно створено: {COLUMN_MAP}")

    except Exception as e:
        logger.error(f"Помилка при ініціалізації карти колонок: {e}")


def find_title_block(title, all_values):
    """
    Знаходить початковий та кінцевий індекс рядка для блоку тайтлу.
    Повертає (start_row_idx, end_row_idx) або (None, None).
    """
    normalized_title_to_find = normalize_title(title)
    title_start_idx = -1
    title_end_idx = -1

    # Шукаємо початок блоку
    for i, row in enumerate(all_values):
        if row and normalize_title(row[0]) == normalized_title_to_find:
            title_start_idx = i
            break
    
    if title_start_idx == -1:
        return None, None

    # Шукаємо кінець блоку (наступний тайтл або кінець даних)
    title_end_idx = len(all_values)
    for i, row in enumerate(all_values[title_start_idx + 1:]):
        # Якщо в першій колонці є значення і в другій пусто, це, ймовірно, новий тайтл
        if row and row[0].strip() and (len(row) == 1 or not row[1].strip()):
            title_end_idx = title_start_idx + i + 1
            break
            
    return title_start_idx, title_end_idx


def update_title_table(title, chapter, role, nickname):
    """
    Оновлює комірки для конкретного розділу та ролі, використовуючи глобальну карту колонок.
    """
    if not COLUMN_MAP:
        logger.error("Карта колонок порожня. Оновлення неможливе.")
        return False

    try:
        all_values = titles_sheet.get_all_values()
        start_idx, end_idx = find_title_block(title, all_values)

        if start_idx is None:
            logger.warning(f"Тайтл '{title}' не знайдено.")
            return False

        # Нормалізуємо роль для пошуку в карті
        normalized_role = normalize_title(role)
        # Мапінг варіацій ролей на канонічні назви з карти
        role_map = {"клін": "клін", "переклад": "переклад", "тайп": "тайп", "ред": "редакт", "редакт": "редакт"}
        canonical_role = role_map.get(normalized_role)
        
        if not canonical_role or canonical_role not in COLUMN_MAP:
            logger.warning(f"Роль '{role}' не знайдено в карті колонок.")
            return False
            
        role_columns = COLUMN_MAP[canonical_role]
        nick_col_idx = role_columns.get('нік') or role_columns.get('shed') # 'shed' для сумісності
        date_col_idx = role_columns.get('дата')
        status_col_idx = role_columns.get('статус')

        if not nick_col_idx or not date_col_idx or not status_col_idx:
            logger.warning(f"Для ролі '{role}' відсутні необхідні колонки (нік/дата/статус) в карті.")
            return False
        
        # Шукаємо розділ в межах блоку
        for i in range(start_idx, end_idx):
            row = all_values[i]
            # Колонка B (індекс 1) - це номер розділу
            if len(row) > 1 and str(row[1]).strip() == str(chapter).strip():
                row_to_update_idx = i + 1 # gspread використовує 1-based індексацію
                now_date = datetime.now().strftime("%d.%m.%Y") # Формат як у таблиці
                
                # Створюємо список для пакетного оновлення
                updates = [
                    {'range': gspread.utils.rowcol_to_a1(row_to_update_idx, nick_col_idx), 'values': [[nickname]]},
                    {'range': gspread.utils.rowcol_to_a1(row_to_update_idx, date_col_idx), 'values': [[now_date]]},
                    {'range': gspread.utils.rowcol_to_a1(row_to_update_idx, status_col_idx), 'values': [["✅"]]},
                ]
                titles_sheet.batch_update(updates)
                logger.info(f"Оновлено тайтл '{title}', розділ '{chapter}', роль '{role}'.")
                return True

        logger.warning(f"Не знайдено розділ '{chapter}' для тайтлу '{title}'.")
        return False

    except Exception as e:
        logger.error(f"Помилка при оновленні таблиці: {e}")
        return False


def set_publish_status(title, chapter):
    """Встановлює статус 'Опубліковано' для розділу."""
    if not COLUMN_MAP:
        logger.error("Карта колонок порожня. Оновлення статусу публікації неможливе.")
        return "error"
        
    try:
        all_values = titles_sheet.get_all_values()
        start_idx, end_idx = find_title_block(title, all_values)

        if start_idx is None:
            logger.warning(f"Тайтл '{title}' не знайдено.")
            return "not_found"

        publish_col_idx = COLUMN_MAP.get('дата дедлайну', {}).get('статус')
        if not publish_col_idx:
            logger.error("Не вдалося знайти колонку статусу публікації в карті.")
            return "error"

        for i in range(start_idx, end_idx):
            row = all_values[i]
            if len(row) > 1 and str(row[1]).strip() == str(chapter).strip():
                row_to_update_idx = i + 1
                titles_sheet.update_cell(row_to_update_idx, publish_col_idx, "✅")
                # Повертаємо оригінальну назву тайтлу з таблиці
                original_title = all_values[start_idx][0]
                return "success", original_title

        logger.warning(f"Не знайдено розділ '{chapter}' для тайтлу '{title}' для публікації.")
        return "chapter_not_found"

    except Exception as e:
        logger.error(f"Помилка при оновленні статусу публікації: {e}")
        return "error"


def get_title_status_data(title):
    """Отримує дані для звіту по статусу, використовуючи нову логіку."""
    try:
        all_values = titles_sheet.get_all_values()
        start_idx, end_idx = find_title_block(title, all_values)

        if start_idx is None:
            logger.warning(f"Тайтл '{title}' не знайдено для отримання статусу.")
            return None, None

        title_data_rows = all_values[start_idx + 2 : end_idx] # Дані починаються через 2 рядки
        original_title = all_values[start_idx][0]
        
        # Створюємо структурований звіт
        status_report = []
        publish_status_col_idx = COLUMN_MAP.get('дата дедлайну', {}).get('статус')

        for row in title_data_rows:
            if not row or not row[1].strip(): # Пропускаємо пусті рядки або без номера розділу
                continue
            
            chapter_number = row[1].strip()
            # Індекс в Python 0-based, тому віднімаємо 1
            is_published = False
            if publish_status_col_idx and len(row) >= publish_status_col_idx:
                is_published = (row[publish_status_col_idx - 1] == "✅")
            
            status_report.append({
                "chapter": chapter_number,
                "published": is_published
            })
            
        return original_title, status_report

    except Exception as e:
        logger.error(f"Помилка при отриманні даних статусу для '{title}': {e}")
        return None, None

# --- Допоміжні та старі функції (без змін або з мінімальними змінами) ---

def normalize_title(t):
    if not isinstance(t, str): return ""
    return re.sub(r'\\s+', ' ', t.strip().lower().replace("’", "'"))

def append_log_row(telegram_name, telegram_tag, title, chapter, position, nickname):
    if log_sheet is None:
        logger.error("log_sheet не ініціалізовано.")
        return False
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_sheet.append_row([now, telegram_name, telegram_tag, title, chapter, position, nickname])
        return True
    except Exception as e:
        logger.error(f"Помилка при додаванні запису в лог: {e}")
        return False

# Функції для /register залишаються без змін, оскільки вони працюють з іншим аркушем
def get_user_sheet(main_sheet_instance):
    if main_sheet_instance is None: return None
    try:
        return main_sheet_instance.worksheet("Користувачі")
    except gspread.exceptions.WorksheetNotFound:
        new_sheet = main_sheet_instance.add_worksheet("Користувачі", rows=100, cols=4)
        new_sheet.append_row(["Telegram-нік", "Теґ", "Нік", "Ролі"])
        return new_sheet
    except Exception as e:
        logger.error(f"Помилка при отриманні аркуша 'Користувачі': {e}")
        return None

def load_nickname_map():
    user_sheet = get_user_sheet(main_spreadsheet)
    if user_sheet is None: return {}
    try:
        data = user_sheet.get_all_records()
        return {row["Telegram-нік"]: row["Нік"] for row in data if "Telegram-нік" in row and "Нік" in row}
    except Exception as e:
        logger.error(f"Помилка при завантаженні мапи нікнеймів: {e}")
        return {}

def find_user_row_by_nick_or_tag(telegram_full_name, telegram_tag, desired_nick):
    user_sheet = get_user_sheet(main_spreadsheet)
    if user_sheet is None: return None, None
    try:
        all_values = user_sheet.get_all_values()
        if not all_values or len(all_values) < 2: return None, None
        headers = all_values[0]
        telegram_nick_col_idx = headers.index("Telegram-нік")
        tag_col_idx = headers.index("Теґ")
        nick_col_idx = headers.index("Нік")
        for i, row in enumerate(all_values[1:]):
            row_index = i + 2
            if len(row) <= max(telegram_nick_col_idx, tag_col_idx, nick_col_idx): continue
            current_telegram_nick = row[telegram_nick_col_idx].strip().lower()
            current_tag = row[tag_col_idx].strip().lower()
            current_nick = row[nick_col_idx].strip().lower()
            if (current_telegram_nick == telegram_full_name.strip().lower() or
                current_nick == desired_nick.strip().lower() or
                (telegram_tag and current_tag == f'@{telegram_tag}'.lower())):
                return row_index, row
        return None, None
    except Exception as e:
        logger.error(f"Помилка при пошуку користувача: {e}")
        return None, None

def _format_telegram_tag(tag):
    if tag:
        tag_str = str(tag).strip()
        return '@' + tag_str if not tag_str.startswith('@') else tag_str
    return ""

def update_user_row(row_index, telegram_full_name, telegram_tag, desired_nick, roles):
    user_sheet = get_user_sheet(main_spreadsheet)
    if user_sheet is None: return False
    try:
        user_sheet.update(f'A{row_index}:D{row_index}', [[telegram_full_name, _format_telegram_tag(telegram_tag), desired_nick, roles]])
        return True
    except Exception as e:
        logger.error(f"Помилка при оновленні рядка користувача: {e}")
        return False

def append_user_row(telegram_full_name, telegram_tag, desired_nick, roles):
    user_sheet = get_user_sheet(main_spreadsheet)
    if user_sheet is None: return False
    try:
        user_sheet.append_row([telegram_full_name, _format_telegram_tag(telegram_tag), desired_nick, roles])
        return True
    except Exception as e:
        logger.error(f"Помилка при додаванні рядка користувача: {e}")
        return False

def set_main_roles(title, roles_map):
    """Встановлює основні ролі для тайтлу. Логіка також оновлена для використання find_title_block."""
    if not COLUMN_MAP:
        logger.error("Карта колонок порожня. Встановлення ролей неможливе.")
        return False
        
    try:
        all_values = titles_sheet.get_all_values()
        start_idx, _ = find_title_block(title, all_values)

        if start_idx is None:
            logger.warning(f"Тайтл '{title}' не знайдено для встановлення ролей.")
            return False

        # Ролі встановлюються у підзаголовку, який є наступним після рядка з назвою тайтлу
        header_row_to_update_idx = start_idx + 2 # 1-based index
        
        updates = []
        role_mapping_canon = {"клін": "клін", "переклад": "переклад", "тайп": "тайп", "редакт": "редакт"}

        for role, nicks_list in roles_map.items():
            canonical_role = role_mapping_canon.get(role.lower())
            if canonical_role and canonical_role in COLUMN_MAP:
                nick_col_idx = COLUMN_MAP[canonical_role].get('shed') or COLUMN_MAP[canonical_role].get('нік')
                if nick_col_idx:
                    nicknames_str = ", ".join(nicks_list)
                    updates.append({
                        'range': gspread.utils.rowcol_to_a1(header_row_to_update_idx, nick_col_idx),
                        'values': [[nicknames_str]]
                    })
        
        if updates:
            titles_sheet.batch_update(updates)
            logger.info(f"Основні ролі для тайтлу '{title}' оновлено.")
            return True
        return False
        
    except Exception as e:
        logger.error(f"Помилка при встановленні основних ролей: {e}")
        return False