import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
import re
import logging
import os

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
    creds_path = os.path.join(os.path.dirname(__file__), '..', 'credentials.json')
    creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(creds)
    main_spreadsheet = client.open("DataBase")
    log_sheet = main_spreadsheet.worksheet("Журнал")
    titles_sheet = main_spreadsheet.worksheet("Тайтли")
    logger.info("Успішно підключено до Google Sheets.")
except Exception as e:
    logger.error(f"Помилка підключення до Google Sheets: {e}")

def get_title_sheet():
    if titles_sheet is None:
        logger.error("titles_sheet не ініціалізовано. Можливо, проблема з credentials.json або доступом.")
    return titles_sheet

def normalize_title(t):
    if not isinstance(t, str):
        return ""
    return re.sub(r'\\s+', ' ', t.strip().lower().replace("’", "'"))

def get_user_sheet(main_sheet_instance):
    if main_sheet_instance is None:
        logger.error("main_sheet_instance не передано для get_user_sheet.")
        return None
    try:
        return main_sheet_instance.worksheet("Користувачі")
    except gspread.exceptions.WorksheetNotFound:
        logger.warning("Аркуш 'Користувачі' не знайдено, створюю новий.")
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
        if not all_values or len(all_values) < 2:
            return None, None
        
        headers = all_values[0]
        try:
            telegram_nick_col_idx = headers.index("Telegram-нік")
            tag_col_idx = headers.index("Теґ")
            nick_col_idx = headers.index("Нік")
        except ValueError as e:
            logger.error(f"Відсутня необхідна колонка в аркуші 'Користувачі': {e}. Заголовки: {headers}")
            return None, None

        for i, row in enumerate(all_values[1:]):
            row_index = i + 2
            
            if len(row) <= max(telegram_nick_col_idx, tag_col_idx, nick_col_idx):
                continue

            current_telegram_nick = row[telegram_nick_col_idx].strip().lower() if len(row) > telegram_nick_col_idx else ""
            current_tag = row[tag_col_idx].strip().lower() if len(row) > tag_col_idx else ""
            current_nick = row[nick_col_idx].strip().lower() if len(row) > nick_col_idx else ""

            if current_telegram_nick == telegram_full_name.strip().lower() or \
               current_nick == desired_nick.strip().lower() or \
               (telegram_tag and current_tag == _format_telegram_tag(telegram_tag).strip().lower()):
                return row_index, row
        return None, None
    except Exception as e:
        logger.error(f"Помилка при пошуку користувача за ніком або тегом: {e}")
        return None, None

def _format_telegram_tag(tag):
    """Додає '@' до тегу, якщо його немає, і повертає пустий рядок, якщо тег None або порожній."""
    if tag:
        tag_str = str(tag).strip()
        if tag_str and not tag_str.startswith('@'):
            return '@' + tag_str
        return tag_str
    return ""

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
        user_sheet.update_cell(row_index, tag_col_idx, _format_telegram_tag(telegram_tag))
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
        user_sheet.append_row([telegram_full_name, _format_telegram_tag(telegram_tag), desired_nick, roles])
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

def update_title_table(title, chapter, role, nickname, titles_sheet_instance):
    if titles_sheet_instance is None:
        logger.error("titles_sheet не ініціалізовано, неможливо оновити таблицю.")
        return False

    try:
        all_values = titles_sheet_instance.get_all_values()
        
        # Знаходимо блок для тайтлу
        title_row_idx, header_row_idx = -1, -1
        for i, row in enumerate(all_values):
            if normalize_title(row[0]) == normalize_title(title):
                title_row_idx = i
                header_row_idx = i + 1
                break
        
        if title_row_idx == -1 or header_row_idx >= len(all_values):
            logger.warning(f"Тайтл '{title}' не знайдено для оновлення.")
            return False

        headers_main = all_values[title_row_idx]
        headers_sub = all_values[header_row_idx]
        
        # Знаходимо індекси колонок для ролі
        role_col_start_idx = -1
        try:
            role_col_start_idx = headers_main.index(role.capitalize()) # 'Клін', 'Переклад'
        except ValueError:
            try:
                # Обробка 'редакт', якщо він підпадає під 'Редакт'
                if role == 'редакт' and 'Редакт' in headers_main:
                    role_col_start_idx = headers_main.index('Редакт')
                else:
                    logger.warning(f"Невідома роль для оновлення: {role}")
                    return False
            except ValueError:
                logger.warning(f"Невідома роль для оновлення: {role}")
                return False

        # Знаходимо індекси підколонок
        nick_col_offset = headers_sub[role_col_start_idx:].index("Нік")
        date_col_offset = headers_sub[role_col_start_idx:].index("Дата")
        status_col_offset = headers_sub[role_col_start_idx:].index("Статус")
        
        nick_col_idx = role_col_start_idx + nick_col_offset + 1
        date_col_idx = role_col_start_idx + date_col_offset + 1
        status_col_idx = role_col_start_idx + status_col_offset + 1

        # Шукаємо рядок з потрібним розділом
        start_data_row_idx = header_row_idx + 1
        for i, row in enumerate(all_values[start_data_row_idx:]):
            actual_row_idx = start_data_row_idx + i
            if len(row) > 0 and str(row[0]).strip() == str(chapter).strip():
                now = datetime.now().strftime("%Y-%m-%d")
                
                titles_sheet_instance.update_cell(actual_row_idx + 1, nick_col_idx, nickname)
                titles_sheet_instance.update_cell(actual_row_idx + 1, date_col_idx, now)
                titles_sheet_instance.update_cell(actual_row_idx + 1, status_col_idx, "✅")
                return True

        logger.warning(f"Не знайдено розділ '{chapter}' для тайтлу '{title}' для оновлення.")
        return False
    except Exception as e:
        logger.error(f"Помилка при оновленні комірки в Google Sheets: {e}")
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
            # Якщо перший елемент заповнений, а другий порожній, це може бути тайтл
            if row and row[0].strip() and (len(row) <= 1 or not row[1].strip()):
                if current_title is None:
                    current_title = row[0].strip()
                    # Дані починаються через 2 рядки (після тайтлу і заголовків)
                    start_row = i + 2
            # Якщо поточний рядок порожній і ми в блоці, то це кінець блоку
            elif not any(row) and current_title is not None:
                blocks.append((current_title, start_row, i))
                current_title = None
        # Якщо файл закінчується з блоком, додаємо його
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
    """
    Встановлює основні ролі для тайтлу.
    roles_map: словник {role: [nick1, nick2, ...]}
    Ніки для однієї ролі будуть об'єднані через кому.
    """
    if titles_sheet is None:
        logger.error("titles_sheet не ініціалізовано, неможливо встановити основні ролі.")
        return False
    try:
        data = titles_sheet.get_all_values()
        
        # Знаходимо рядок тайтлу для оновлення
        for i, row in enumerate(data):
            if row and len(row) > 0 and normalize_title(row[0]) == normalize_title(title):
                # Рядок з тайтлом - це i, а заголовки ролей - i+1
                headers_main = data[i]
                main_role_cols = {
                    "клін": headers_main.index("Клін") if "Клін" in headers_main else -1,
                    "переклад": headers_main.index("Переклад") if "Переклад" in headers_main else -1,
                    "тайп": headers_main.index("Тайп") if "Тайп" in headers_main else -1,
                    "редакт": headers_main.index("Редакт") if "Редакт" in headers_main else -1,
                }
                
                # Знаходимо рядок з ніками для оновлення. У вашому форматі це рядок з тайтлом.
                row_num = i + 1
                
                # Оновлюємо колонки для кожної ролі
                headers_sub = data[i+1] if i + 1 < len(data) else []
                
                for role, nicknames_list in roles_map.items():
                    col_idx_main = main_role_cols.get(role)
                    if col_idx_main != -1 and col_idx_main is not None:
                        # Знаходимо колонку 'Нік' в підзаголовках, що належить цій ролі
                        try:
                            # Шукаємо 'Нік' в підзаголовках, починаючи з індексу основної ролі
                            sub_header_slice = headers_sub[col_idx_main:]
                            nick_offset = sub_header_slice.index('Нік')
                            nick_col_idx = col_idx_main + nick_offset
                            
                            nicknames_str = ", ".join(nicknames_list)
                            titles_sheet.update_cell(row_num, nick_col_idx + 1, nicknames_str)
                        except ValueError:
                            logger.warning(f"Не знайдено підколонку 'Нік' для ролі '{role}'")
                return True
        logger.warning(f"Тайтл '{title}' не знайдено для встановлення основних ролей.")
        return False
    except Exception as e:
        logger.error(f"Помилка при встановленні основних ролей: {e}")
        return False