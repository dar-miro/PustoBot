import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
import re
import logging

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
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)
    main_spreadsheet = client.open("DataBase")
    log_sheet = main_spreadsheet.worksheet("Журнал")
    titles_sheet = main_spreadsheet.worksheet("Тайтли")
    logger.info("Успішно підключено до Google Sheets.")
except Exception as e:
    logger.error(f"Помилка підключення до Google Sheets: {e}")
    # Важливо: якщо тут виникла помилка, об'єкти sheet будуть None.
    # Обробники в main.py повинні це враховувати або перевіряти.

# Відповідність ролей і колонок
columns_by_role = {
    "клін": {"nick": "B", "date": "C", "check": "D"},
    "переклад": {"nick": "E", "date": "F", "check": "G"},
    "тайп": {"nick": "H", "date": "I", "check": "J"},
    "ред": {"nick": "K", "date": "L", "check": "M"},
    "редакт": {"nick": "K", "date": "L", "check": "M"},
}

def get_title_sheet():
    if titles_sheet is None:
        logger.error("titles_sheet не ініціалізовано. Можливо, проблема з credentials.json або доступом.")
        # Можна повернути заглушку або викликати виняток, якщо sheet обов'язковий.
        # Для цього бота, краще, щоб виклики функцій з sheets.py перевіряли None.
    return titles_sheet

def normalize_title(t):
    return re.sub(r'\\s+', ' ', t.strip().lower().replace("’", "'"))

def get_user_sheet(main_sheet_instance): # Приймаємо екземпляр основного аркуша
    if main_sheet_instance is None:
        logger.error("main_sheet_instance не передано для get_user_sheet.")
        return None
    try:
        return main_sheet_instance.spreadsheet.worksheet("Користувачі")
    except gspread.exceptions.WorksheetNotFound: # Точніший виняток
        logger.warning("Аркуш 'Користувачі' не знайдено, створюю новий.")
        # Створення нового аркуша з заголовками: "Telegram-нік", "Теґ", "Нік", "Ролі"
        new_sheet = main_sheet_instance.spreadsheet.add_worksheet("Користувачі", rows=100, cols=4) # Змінено cols на 4
        new_sheet.append_row(["Telegram-нік", "Теґ", "Нік", "Ролі"]) # Додаємо заголовки
        return new_sheet
    except Exception as e:
        logger.error(f"Помилка при отриманні або створенні аркуша 'Користувачі': {e}")
        return None

def load_nickname_map():
    user_sheet = get_user_sheet(main_spreadsheet) # Передаємо main_spreadsheet
    if user_sheet is None:
        return {} # Повернути порожній словник, якщо аркуш недоступний

    try:
        # get_all_records() використовує перший рядок як заголовки
        data = user_sheet.get_all_records()
        # Тепер мапа буде з Telegram-нік на Нік.
        # Колонка "Теґ" може бути використана для додаткової валідації або ідентифікації.
        nickname_map = {row["Telegram-нік"]: row["Нік"] for row in data if "Telegram-нік" in row and "Нік" in row}
        return nickname_map
    except Exception as e:
        logger.error(f"Помилка при завантаженні мапи нікнеймів: {e}")
        return {}

# НОВА ФУНКЦІЯ: Пошук користувача за ніком або тегом
def find_user_row_by_nick_or_tag(telegram_full_name, telegram_tag, desired_nick):
    user_sheet = get_user_sheet(main_spreadsheet)
    if user_sheet is None:
        logger.error("user_sheet не ініціалізовано, неможливо здійснити пошук.")
        return None, None # Повертаємо row_index і row_data
    
    try:
        all_values = user_sheet.get_all_values()
        if not all_values:
            return None, None
        
        headers = all_values[0]
        try:
            telegram_nick_col_idx = headers.index("Telegram-нік")
            tag_col_idx = headers.index("Теґ")
            nick_col_idx = headers.index("Нік")
        except ValueError as e:
            logger.error(f"Відсутня необхідна колонка в аркуші 'Користувачі': {e}")
            return None, None

        # Починаємо з 1, щоб пропустити заголовки
        for i, row in enumerate(all_values[1:]): 
            # Додаємо i+2, тому що enumerate починається з 0, а all_values[1:] пропускає заголовок
            # і gspread індексується з 1.
            row_index = i + 2 
            
            # Перевірка на достатню довжину рядка, щоб уникнути IndexError
            if len(row) <= max(telegram_nick_col_idx, tag_col_idx, nick_col_idx):
                continue # Пропускаємо рядки, які занадто короткі

            # Перевіряємо за Telegram-нік (повне ім'я) або за "Нік" (бажаний нік)
            # Припустимо, що Telegram-нік є унікальним
            # Або що бажаний_нік також є унікальним для кожного зареєстрованого користувача
            if row[telegram_nick_col_idx].strip().lower() == telegram_full_name.strip().lower() or \
               row[nick_col_idx].strip().lower() == desired_nick.strip().lower():
                return row_index, row # Повертаємо індекс рядка (у gspread) та сам рядок
            
            # Також можна перевірити за тегом Telegram, якщо він заповнений
            if telegram_tag and row[tag_col_idx].strip().lower() == telegram_tag.strip().lower():
                 return row_index, row

        return None, None # Якщо не знайдено
    except Exception as e:
        logger.error(f"Помилка при пошуку користувача за ніком або тегом: {e}")
        return None, None


def update_user_row(row_index, telegram_full_name, telegram_tag, desired_nick, roles):
    user_sheet = get_user_sheet(main_spreadsheet)
    if user_sheet is None:
        logger.error("user_sheet не ініціалізовано, неможливо оновити рядок.")
        return False
    
    try:
        headers = user_sheet.row_values(1)
        # Перевіряємо, чи є всі потрібні колонки
        required_cols = ["Telegram-нік", "Теґ", "Нік", "Ролі"]
        for col in required_cols:
            if col not in headers:
                logger.error(f"Відсутня необхідна колонка '{col}' в аркуші 'Користувачі'.")
                return False

        telegram_nick_col_idx = headers.index("Telegram-нік") + 1 # +1 для індексу колонки gspread
        tag_col_idx = headers.index("Теґ") + 1
        nick_col_idx = headers.index("Нік") + 1
        roles_col_idx = headers.index("Ролі") + 1

        user_sheet.update_cell(row_index, telegram_nick_col_idx, telegram_full_name)
        user_sheet.update_cell(row_index, tag_col_idx, telegram_tag)
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
        # get_all_records() використовує перший рядок як заголовки,
        # тому append_row додасть до кінця існуючих даних.
        # Перевіряємо, чи є заголовки. Якщо ні, то вони були створені
        # в get_user_sheet, і можна безпечно додавати рядок.
        user_sheet.append_row([telegram_full_name, telegram_tag, desired_nick, roles])
        return True
    except Exception as e:
        logger.error(f"Помилка при додаванні нового рядка користувача: {e}")
        return False


def append_log_row(telegram_name, telegram_tag, title, chapter, position, nickname): # Додано telegram_tag
    if log_sheet is None:
        logger.error("log_sheet не ініціалізовано, неможливо додати запис у лог.")
        return False
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Додаємо telegram_tag до списку значень для логу
        log_sheet.append_row([now, telegram_name, telegram_tag, title, chapter, position, nickname]) 
        return True
    except Exception as e:
        logger.error(f"Помилка при додаванні запису в лог: {e}")
        return False

# ✍️ Оновлення таблиці по знайденому блоку
def update_title_table(title, chapter, role, nickname):
    if titles_sheet is None:
        logger.error("titles_sheet не ініціалізовано, неможливо оновити таблицю.")
        return False

    role_columns = columns_by_role.get(role.lower()) # Використовуємо .lower()
    if not role_columns:
        logger.warning(f"Невідома роль для оновлення: {role}")
        return False

    blocks = get_title_blocks()
    for block_title, start_row, end_row in blocks:
        if normalize_title(block_title) == normalize_title(title):
            rows = titles_sheet.get_all_values()[start_row:end_row]
            for i, row in enumerate(rows):
                # Перевіряємо, чи є в рядку достатньо елементів для доступу до chapter
                if row and len(row) > 0 and chapter.strip() == row[0].strip(): # Порівнюємо розділ
                    actual_row = start_row + i + 1 # +1 для індексації Google Sheets, +1 бо headers
                    now = datetime.now().strftime("%Y-%m-%d")
                    try:
                        titles_sheet.update_acell(f"{role_columns['nick']}{actual_row}", nickname)
                        titles_sheet.update_acell(f"{role_columns['date']}{actual_row}", now)
                        titles_sheet.update_acell(f"{role_columns['check']}{actual_row}", "✅")
                        return True
                    except Exception as e:
                        logger.error(f"Помилка при оновленні комірки в Google Sheets: {e}")
                        return False
    logger.warning(f"Не знайдено розділ '{chapter}' для тайтлу '{title}' для оновлення.")
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
            # Перша колонка не порожня і це не заголовок "Розділ"
            if row and row[0].strip() and not row[0].strip().lower().startswith("розділ"):
                if current_title is None:
                    current_title = row[0].strip()
                    start_row = i
            elif not any(row) and current_title is not None: # Порожній рядок розділяє блоки
                blocks.append((current_title, start_row, i))
                current_title = None
        # Додати останній блок, якщо він є
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
    if titles_sheet is None:
        logger.error("titles_sheet не ініціалізовано, неможливо встановити основні ролі.")
        return False
    try:
        data = titles_sheet.get_all_values()
        headers = data[0] if data else []
        
        # Знайти колонки для 'Осн. Клін', 'Осн. Переклад' тощо
        main_role_cols = {
            "клін": headers.index("Осн. Клін") if "Осн. Клін" in headers else -1,
            "переклад": headers.index("Осн. Переклад") if "Осн. Переклад" in headers else -1,
            "тайп": headers.index("Осн. Тайп") if "Осн. Тайп" in headers else -1,
            "редакт": headers.index("Осн. Редакт") if "Осн. Редакт" in headers else -1,
        }

        for i, row in enumerate(data):
            if normalize_title(row[0]) == normalize_title(title):
                # Рядок заголовка тайтлу
                row_num = i + 1 # індекс рядка в Google Sheets
                for role, nickname in roles_map.items():
                    col_idx = main_role_cols.get(role)
                    if col_idx != -1 and col_idx is not None:
                        titles_sheet.update_cell(row_num, col_idx + 1, nickname) # +1 для індексу колонки
                return True
        logger.warning(f"Тайтл '{title}' не знайдено для встановлення основних ролей.")
        return False
    except Exception as e:
        logger.error(f"Помилка при встановленні основних ролей: {e}")
        return False