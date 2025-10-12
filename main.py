# main.py

import logging
import re
import gspread
import asyncio
import os
import sys
from aiohttp import web
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from datetime import datetime
import gspread.utils

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
GOOGLE_CREDENTIALS_FILE = os.environ.get("GOOGLE_CREDENTIALS_FILE", 'credentials.json')
SPREADSHEET_KEY = os.environ.get("SPREADSHEET_KEY")

# Налаштування логування
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Словник для ролей (ТЕПЕР БЕЗ БЕТИ, БЕТА ДИНАМІЧНО ДОДАЄТЬСЯ)
ROLE_TO_COLUMN_BASE = {
    "клін": "Клін",
    "переклад": "Переклад",
    "тайп": "Тайп",
    "ред": "Редакт",
}
# Публікація
PUBLISH_COLUMN_BASE = "Публікація"

# ЗМІНА 1: Видалення стовпця 'Публікація-Нік' та додавання 'Публікація-Дата';
def generate_sheet_headers(include_beta=False):
    """Генерує список заголовків для аркуша тайтлу; опціонально включаючи Бета;"""
    headers = ['Розділ']
    roles = list(ROLE_TO_COLUMN_BASE.values())
    if include_beta:
        roles.append("Бета") # Додаємо Бета-роль до списку

    for role in roles:
        # Порядок: Нік; Дата; Статус (для основних ролей)
        headers.extend([f'{role}-Нік', f'{role}-Дата', f'{role}-Статус'])

    # ОНОВЛЕНО: Додаємо Публікація-Дата та Публікація-Статус (Нік не потрібен)
    headers.extend([f'{PUBLISH_COLUMN_BASE}-Дата', f'{PUBLISH_COLUMN_BASE}-Статус'])
    return headers

# Використовуємо стандартні заголовки без бети як глобальний дефолт
SHEET_HEADERS = generate_sheet_headers(include_beta=False)

# ОНОВЛЕНО: Заголовки для аркуша "Журнал"
LOG_HEADERS = ['Дата', 'Telegram-Нік', 'Нік', 'Тайтл', '№ Розділу', 'Роль']

class SheetsHelper:
    """Клас для інкапсуляції всієї роботи з Google Sheets;"""
    def __init__(self, credentials_file, spreadsheet_key):
        # ... (метод init залишається без змін)
        self.spreadsheet = None
        self.log_sheet = None
        self.users_sheet = None
        try:
            gc = gspread.service_account(filename=credentials_file)
            self.spreadsheet = gc.open_by_key(spreadsheet_key) 
            self._initialize_sheets()
        except Exception as e:
            logger.error(f"Не вдалося підключитися до Google Sheets: {e}")

    # ВИПРАВЛЕННЯ 1: Змінено логіку вставки заголовків
    def _get_or_create_worksheet(self, title_name, headers=None, force_headers=False):
        """
        Отримує або створює аркуш за назвою; 
        Заголовки (якщо передані та force_headers=True) вставляються в рядок 3;
        Аркуші Тайтлів створюються без заголовків тут;
        """
        if not self.spreadsheet: raise ConnectionError("Немає підключення до Google Sheets;")
        try:
            return self.spreadsheet.worksheet(title_name)
        except gspread.WorksheetNotFound:
            logger.info(f"Створення нового аркуша: {title_name}")
            cols = len(headers) if headers else 20
            # Створюємо аркуш
            worksheet = self.spreadsheet.add_worksheet(title=title_name, rows="100", cols=str(cols))
            
            # Тільки якщо `force_headers=True` (для Журналу; Користувачів); вставляємо заголовки
            if headers and force_headers: 
                # Вставляємо порожні рядки 1 та 2
                worksheet.insert_row([], 1) 
                worksheet.insert_row([], 2) 
                # Додаємо заголовки в 3-й рядок
                worksheet.insert_row(headers, 3) 
            return worksheet
            
    def _initialize_sheets(self):
        """Ініціалізує основні аркуші (Журнал; Users; Тайтли);"""
        # Ініціалізація Журналу (force_headers=True)
        try:
            self.log_sheet = self._get_or_create_worksheet("Журнал", LOG_HEADERS, force_headers=True)
        except Exception as e:
            logger.error(f"Не вдалося ініціалізувати аркуш 'Журнал': {e}")
            self.log_sheet = None
            
        # Ініціалізація Користувачів (force_headers=True)
        try:
            self.users_sheet = self._get_or_create_worksheet("Користувачі", ['Telegram-ID', 'Теґ', 'Нік', 'Ролі'], force_headers=True)
        except Exception as e:
            logger.error(f"Не вдалося ініціалізувати аркуш 'Користувачі': {e}")
            self.users_sheet = None

    def _log_action(self, telegram_tag, nickname, title, chapter, role):
        """Додає запис про операцію до аркуша 'Журнал';"""
        if self.log_sheet:
            try:
                current_datetime = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
                # Структура: Дата; Telegram-Нік; Нік; Тайтл; № Розділу; Роль
                log_row = [
                    current_datetime,
                    telegram_tag,
                    nickname,
                    title,
                    str(chapter),
                    role
                ]
                self.log_sheet.append_row(log_row)
            except Exception as e:
                logger.error(f"Помилка логування дії: {e}")
        else:
            logger.warning("Аркуш 'Журнал' не ініціалізовано; логування пропущено;")

    # --- НОВИЙ МЕТОД ДЛЯ ОТРИМАННЯ НІКНЕЙМА ---
    def get_nickname_by_id(self, user_id):
        """Отримує зареєстрований Нік користувача за його Telegram-ID;"""
        if not self.users_sheet: 
            logger.warning("Аркуш 'Користувачі' не ініціалізовано; неможливо отримати нік;")
            return None
        try:
            # Знаходимо користувача за ID (колонка 1)
            user_ids = self.users_sheet.col_values(1)
            str_user_id = str(user_id)
            
            if str_user_id in user_ids:
                row_index = user_ids.index(str(user_id)) + 1
                # Нік знаходиться в колонці 3
                nickname = self.users_sheet.cell(row_index, 3).value
                return nickname if nickname and nickname.strip() else None
            return None
        except Exception as e:
            logger.error(f"Помилка отримання нікнейма для ID {user_id}: {e}")
            return None
    # ---------------------------------------------

    def register_user(self, user_id, username, nickname):
        """Реєструє або оновлює користувача на аркуші 'Користувачі';"""
        if not self.users_sheet: return "Помилка підключення до таблиці 'Користувачі';"
        try:
            users_sheet = self.users_sheet
            # Знаходимо користувача за ID (колонка 1)
            user_ids = users_sheet.col_values(1)
            
            # Якщо таблиця пуста; col_values(1) може повернути список із заголовком
            if user_ids and str(user_id) in user_ids:
                row_index = user_ids.index(str(user_id)) + 1
                # Оновлюємо Теґ (колонка 2) та Нік (колонка 3)
                users_sheet.update_cell(row_index, 2, username)
                users_sheet.update_cell(row_index, 3, nickname)
                return f"✅ Ваші дані оновлено; Нікнейм: {nickname}"
            else:
                # Таблиця 'Користувачі': Telegram-ID; Теґ; Нік; Ролі
                users_sheet.append_row([str(user_id), username, nickname, ''])
                return f"✅ Вас успішно зареєстровано; Нікнейм: {nickname}"
        except Exception as e:
            logger.error(f"Помилка реєстрації: {e}")
            return "❌ Сталася помилка під час реєстрації;"

    # ВИПРАВЛЕННЯ 2: set_team тепер лише встановлює команду в A2
    def set_team(self, title_name, team_string, beta_nickname, telegram_tag, nickname):
        """Створює аркуш (якщо його немає) та встановлює команду тайтлу в A2;"""
        if not self.spreadsheet: return "Помилка підключення до таблиці;"
        
        try:
            # Створюємо аркуш; якщо його немає; (заголовки не додаються)
            worksheet = self._get_or_create_worksheet(title_name) 

            # 1. Записуємо команду в клітинку A2
            worksheet.update_acell('A2', team_string)
            
            # 2. Логування
            self._log_action(
                telegram_tag=telegram_tag,
                nickname=nickname,
                title=title_name,
                chapter="Команда",
                role="Встановлення команди"
            )
            
            beta_info = f" (з Бета-тестером: {beta_nickname})" if beta_nickname else ""
            return f"✅ Команда для тайтлу '{title_name}' успішно встановлена;{beta_info}\n_Шапка (заголовки) будуть створені автоматично при додаванні першого розділу;_"
            
        except gspread.WorksheetNotFound:
            return f"⚠️ Тайтл '{title_name}' не знайдено;"
        except Exception as e:
            logger.error(f"Помилка встановлення команди: {e}")
            return "❌ Сталася помилка при встановленні команди;"

    # ЗМІНА 2: Додавання випадного списку статусу; Оновлення рядка;
    def _prepare_worksheet_headers(self, worksheet, title_name):
        """Перевіряє і створює правильну шапку (заголовки) та встановлює правила валідації (випадний список);"""
        # 1. Визначаємо; чи є бета-роль в команді (рядок A2)
        try:
            team_string = worksheet.acell('A2').value or ''
        except Exception:
            team_string = ''
            
        has_beta_in_team = 'бета -' in team_string.lower()
        required_headers = generate_sheet_headers(include_beta=has_beta_in_team)
        
        # 2. Перевіряємо та створюємо/оновлюємо заголовки в рядку 3
        try:
            current_headers = worksheet.row_values(3)
        except gspread.exceptions.APIError:
            current_headers = []
        
        headers_updated = False
        if not current_headers or current_headers != required_headers:
            logger.info(f"Створення/оновлення заголовків для {title_name}; Бета: {has_beta_in_team}")
            
            # Якщо рядок 3 не порожній; видаляємо його перед вставкою
            try:
                if current_headers: worksheet.delete_rows(3, 3) 
            except Exception:
                pass 
            
            worksheet.insert_row(required_headers, 3) # Вставляємо заголовки в 3-й рядок
            headers_updated = True
            
        # 3. Встановлення правила валідації для статусу (випадний список)
        
        # Визначаємо колонки Статусу (всі; що закінчуються на '-Статус')
        status_cols = [
            i + 1 for i, header in enumerate(required_headers) 
            if header.endswith('-Статус')
        ]
        
    # --- ВИПРАВЛЕННЯ: КОПІЮВАННЯ ФОРМАТУВАННЯ ТА ВСТАВКА ДАНИХ ---
    # Використовуємо values_update для пакетного оновлення (ВИПРАВЛЯЄ ПОМИЛКУ 400)
    # та insert_row для копіювання форматування
     # --- ВИПРАВЛЕННЯ: КОПІЮВАННЯ ФОРМАТУВАННЯ ТА ВСТАВКА ДАНИХ (БЕЗ values_update) ---
    # --- ВИПРАВЛЕНИЙ МЕТОД КОПІЮВАННЯ ФОРМАТУВАННЯ ---
    def _copy_formatting_and_insert_data(self, worksheet, last_data_row_index, new_rows_data):
        """
        Копіює форматування з останнього заповненого рядка, вставляючи нові рядки, 
        і оновлює їх вміст, використовуючи послідовні виклики update().
        """
        num_new_rows = len(new_rows_data)
        if num_new_rows == 0:
            return

        num_cols = len(new_rows_data[0]) 

        # 1. Вставляємо пусті рядки (успадковуючи форматування від попереднього рядка)
        # Вставляємо ПІСЛЯ останнього заповненого рядка (last_data_row_index)
        for i in range(num_new_rows):
             # ВИПРАВЛЕННЯ 2: Використовуємо динамічний індекс для послідовної вставки в кінець.
             # Це забезпечує коректне успадкування форматування.
             insertion_index = last_data_row_index + 1 + i
             # Вставляємо новий рядок (порожній), щоб успадкувати форматування.
             worksheet.insert_row([''] * num_cols, index=insertion_index)
        
        # 2. Оновлення значень у нових рядках (які вже були вставлені)
        for i, row_data in enumerate(new_rows_data):
            # Рядок для оновлення знаходиться на індексі, де він був вставлений
            row_index_to_update = last_data_row_index + 1 + i 
            
            # Використовуємо A1-нотацію для діапазону
            range_name = f'{gspread.utils.rowcol_to_a1(row_index_to_update, 1)}:{gspread.utils.rowcol_to_a1(row_index_to_update, num_cols)}'
            
            # ВИКОРИСТОВУЄМО НАДІЙНИЙ МЕТОД: worksheet.update
            worksheet.update(
                range_name, 
                [row_data], 
                value_input_option='USER_ENTERED'
            )
        
    # --- ВИПРАВЛЕНИЙ МЕТОД ДОДАВАННЯ РОЗДІЛІВ ---
    def add_chapters(self, title_name, chapter_numbers, telegram_tag, nickname):
        """Додає один або кілька розділів до аркуша тайтлу;"""
        if not self.spreadsheet: return "Помилка підключення до таблиці;"
        try:
            try:
                worksheet = self.spreadsheet.worksheet(title_name)
            except gspread.WorksheetNotFound:
                worksheet = self._get_or_create_worksheet(title_name) 

            # 1. Перевірка та створення/оновлення заголовків та валідації
            self._prepare_worksheet_headers(worksheet, title_name)
            
            # Визначаємо; чи є бета-роль в команді (рядок A2) для коректного розміру рядка
            try:
                team_string = worksheet.acell('A2').value or ''
            except Exception:
                team_string = ''
            
            has_beta_in_team = 'бета -' in team_string.lower()
            
            # Генерація ролей для створення рядка
            base_roles = list(ROLE_TO_COLUMN_BASE.values())
            if has_beta_in_team:
                base_roles.append("Бета")
                
            num_roles = len(base_roles)
            
            # 2. Перевірка на дублікати розділів
            all_values = worksheet.get_all_values()
            data_rows = all_values[3:]
            existing_chapters = {row[0] for row in data_rows if row and row[0].strip()} 
            
            chapters_to_add = [c for c in chapter_numbers if str(c) not in existing_chapters]
            duplicate_chapters = [c for c in chapter_numbers if str(c) in existing_chapters]
            
            if not chapters_to_add:
                return f"⚠️ Всі розділи ({'; '.join(map(str, duplicate_chapters))}) для '{title_name}' вже існують;"
            
            # Визначаємо індекс останнього заповненого рядка ДАНИХ (після заголовків)
            last_data_row_index = len(all_values) 

            # 3. Створення рядків для розділів
            new_rows_data = []
            for chapter_number in chapters_to_add:
                # ВИПРАВЛЕННЯ 1: Додаємо одинарну лапку для запобігання конвертації в дату
                new_row_data = [f"'{chapter_number}"] # Розділ
            
                # Додаємо дані для основних ролей (Нік; Дата; Статус='❌')
                for _ in range(num_roles):
                    new_row_data.extend(['', '', '❌']) 
                
                # ОНОВЛЕНО: Додаємо дані для Публікації (Дата=''; Статус='❌')
                new_row_data.extend(['', '❌']) 
                
                new_rows_data.append(new_row_data)

            # --- КОПІЮВАННЯ ФОРМАТУВАННЯ ТА ВСТАВКА ДАНИХ ---
            # Якщо є існуючі дані (last_data_row_index > 3); копіюємо форматування
            if last_data_row_index >= 4: # Рядки з даними починаються з 4-го
                self._copy_formatting_and_insert_data(worksheet, last_data_row_index, new_rows_data)
            else:
                 # Якщо даних ще немає, просто додаємо нові рядки (після заголовків)
                 worksheet.append_rows(new_rows_data)
            # --------------------------------------------------
            
            # 4. Логування (якщо розділів багато; логуємо діапазон)
            if len(chapters_to_add) == 1:
                chapter_log = str(chapters_to_add[0])
                response_msg = f"✅ Додано розділ {chapter_log} до тайтлу '{title_name}'."
            else:
                # При логуванні діапазону для дробових номерів беремо min/max
                try:
                    # Конвертуємо в float для сортування (для коректного min/max дробових)
                    sorted_chapters = sorted([float(c) for c in chapters_to_add])
                    first = sorted_chapters[0]
                    last = sorted_chapters[-1]
                    
                    # Форматуємо назад в рядок (без зайвих .0)
                    str_first = str(first) if '.' in str(first) else str(int(first))
                    str_last = str(last) if '.' in str(last) else str(int(last))
                    
                    chapter_log = f"{str_first}-{str_last} ({len(chapters_to_add)} шт;)"
                except ValueError:
                    # Якщо є нечислові значення; просто логуємо кількість
                    chapter_log = f"({len(chapters_to_add)} шт;)"
                    
                response_msg = f"✅ Додано {len(chapters_to_add)} розділів ({chapter_log}) до тайтлу '{title_name}'."

            self._log_action(telegram_tag=telegram_tag, nickname=nickname, title=title_name, chapter=chapter_log, role="Додано розділ(и)")
            
            if duplicate_chapters:
                response_msg += f"\n⚠️ Розділи ({'; '.join(map(str, duplicate_chapters))}) вже існували і були пропущені;"

            return response_msg
        except Exception as e:
            logger.error(f"Помилка додавання розділу(ів): {e}")
            return "❌ Сталася помилка при додаванні розділу(ів);"
    
    # ЗМІНА 5: Оновлення get_status для фільтрації розділів
    def get_status(self, title_name, chapter_numbers=None):
        """
        Отримує і форматує статус роботи над тайтлом;
        chapter_numbers: список номерів розділів; які потрібно показати (або None для всіх);
        """
        if not self.spreadsheet: return "Помилка підключення до таблиці;"
        try:
            worksheet = self.spreadsheet.worksheet(title_name)
            
            # Отримуємо заголовки та всі дані
            all_values = worksheet.get_all_values()
            if len(all_values) < 4:
                # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
                return f"⚠️ Тайтл '{title_name}' не має розділів; Додайте їх за допомогою `/newchapter`;"
            
            headers = all_values[2] # Рядок 3
            data_rows = all_values[3:] # Рядки з даними (після заголовків)
            team_string = worksheet.acell('A2').value or 'Команда не встановлена' # Рядок 2

            # Фільтрація рядків за номерами розділів
            if chapter_numbers:
                # Множина номерів розділів; які потрібно відобразити (у вигляді рядків)
                target_chapters = {str(c) for c in chapter_numbers}
                data_rows = [row for row in data_rows if row and row[0].strip() in target_chapters]
                
                if not data_rows:
                    # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
                    return f"⚠️ Жодного з вказаних розділів ({'; '.join(map(str, chapter_numbers))}) для '{title_name}' не знайдено;"

            # Визначаємо індекси колонок для Нік; Статус
            col_indices = {}
            role_names = []
            
            for i, header in enumerate(headers):
                if header.endswith('-Нік'):
                    role = header.replace('-Нік', '')
                    col_indices[f'{role}-Нік'] = i
                    role_names.append(role)
                elif header.endswith('-Статус'):
                    role = header.replace('-Статус', '')
                    col_indices[f'{role}-Статус'] = i
                    if role not in role_names:
                        role_names.append(role)
                
            # Форматування виводу
            status_message = [f"📊 *Статус Тайтлу: {title_name}*\n"]
            status_message.append(f"👥 *Команда:*\n_{team_string}_\n")
            
            # Максимальна довжина номера розділу для вирівнювання
            max_len_chapter = max(len(row[0]) for row in data_rows if row and row[0]) if data_rows else 0
            
            # Заголовок таблиці
            header_line = f"`{'Розділ':<{max_len_chapter}}`"
            for role in role_names:
                header_line += f"|`{role[:5]:^5}`"
            status_message.append(header_line)
            
            separator_line = f"`{'-' * max_len_chapter}`"
            for _ in role_names:
                separator_line += "|`-----`"
            status_message.append(separator_line)
            
            # Рядки з даними
            for row in data_rows:
                if not row or not row[0].strip(): continue # Пропускаємо пусті рядки
                
                row_line = f"`{row[0]:<{max_len_chapter}}`"
                for role in role_names:
                    # Використовуємо індекс колонки статусу
                    status_col_key = f'{role}-Статус'
                    status_index = col_indices.get(status_col_key)
                    
                    status_char = row[status_index] if status_index is not None and status_index < len(row) else '?'
                    # Символ: ✅ (виконано); ❌ (не виконано); ⏳ (у роботі); ❓ (відсутній)
                    display_char = '✅' if status_char == '✅' else ('❌' if status_char == '❌' else '❓')
                    
                    # Нік (якщо є)
                    nick_col_key = f'{role}-Нік'
                    nick_index = col_indices.get(nick_col_key)
                    
                    # Логіка для ⏳ (У роботі): Якщо статус ❌; але нік є -> ⏳
                    # Для 'Публікація' nick_index буде None; тому nick буде '' і ⏳ не покажеться;
                    nick = row[nick_index].strip() if nick_index is not None and nick_index < len(row) else ''
                    if status_char == '❌' and nick:
                        display_char = '⏳'
                    
                    row_line += f"|`{display_char:^5}`"
                    
                status_message.append(row_line)

            # Ліміт на вивід: 50 останніх розділів + заголовок (тільки якщо не було вказано конкретний діапазон)
            if not chapter_numbers and len(status_message) > 53:
                status_message = status_message[:3] + ["..."] + status_message[-50:]
            
            return "\n".join(status_message)
            
        except gspread.WorksheetNotFound:
            # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
            return f"⚠️ Тайтл '{title_name}' не знайдено; Перевірте назву або створіть його за допомогою `/team`;"
        except Exception as e:
            logger.error(f"Помилка отримання статусу: {e}")
            return "❌ Сталася помилка при отриманні статусу;"


    def update_chapter_status(self, title_name, chapter_number, role_name, status_char, nickname, telegram_tag):
        """Оновлює статус; дату та нік в таблиці для вказаного розділу та ролі;"""
        if not self.spreadsheet: return "Помилка підключення до таблиці;"
        
        try:
            worksheet = self.spreadsheet.worksheet(title_name)
            headers = worksheet.row_values(3)
            
            # Знаходимо індекс рядка розділу (починаємо з 4-го рядка)
            chapter_cells = worksheet.col_values(1, value_render_option='FORMATTED_VALUE')[3:] # З 4-го рядка
            try:
                row_index = chapter_cells.index(str(chapter_number)) + 4 # +4 тому; що рядок 1; 2; 3 пропущені; 
            except ValueError:
                return f"⚠️ Розділ {chapter_number} для '{title_name}' не знайдено;"
            
            # Парсинг ролі (включаючи синонім 'ред')
            role_key = ROLE_TO_COLUMN_BASE.get(role_name.lower())
            if role_name.lower() == 'бета':
                role_key = 'Бета'
            elif role_name.lower() == 'публікація':
                role_key = PUBLISH_COLUMN_BASE

            if not role_key:
                # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
                return f"⚠️ Невідома роль: {role_name}; Доступні: {'; '.join(ROLE_TO_COLUMN_BASE.keys())}; бета; публікація;"

            # Знаходимо індекси колонок для Нік; Дата; Статус
            
            if role_key == PUBLISH_COLUMN_BASE:
                try:
                    # ОНОВЛЕНО: Публікація має 2 колонки: Дата та Статус (Нік відсутній)
                    date_col_index = headers.index(f'{PUBLISH_COLUMN_BASE}-Дата') + 1
                    status_col_index = headers.index(f'{PUBLISH_COLUMN_BASE}-Статус') + 1
                    nick_col_index = None # Нік для публікації не використовується
                except ValueError:
                    # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
                    return "❌ Помилка: Невірний формат заголовків аркуша тайтлу (Публікація-Дата або Публікація-Статус відсутні);"
            else:
                try:
                    nick_col_index = headers.index(f'{role_key}-Нік') + 1
                    date_col_index = headers.index(f'{role_key}-Дата') + 1
                    status_col_index = headers.index(f'{role_key}-Статус') + 1
                except ValueError:
                    # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
                    return f"❌ Помилка: Колонка для ролі '{role_key}' не знайдена в заголовках; Можливо; ви не встановили бету."


            # 1. Оновлення статусу (завжди)
            new_status = '✅' if status_char == '+' else '❌'
            
            # Оновлюємо значення
            if role_key == PUBLISH_COLUMN_BASE: 
                # Оновлюємо статус
                worksheet.update_cell(row_index, status_col_index, new_status)
                
                # 2. Оновлення Дати (тільки для + або -)
                if status_char == '+':
                    current_date = datetime.now().strftime("%d.%m.%Y")
                    worksheet.update_cell(row_index, date_col_index, current_date)
                elif status_char == '-':
                    # Прибираємо дату при відміні
                    worksheet.update_cell(row_index, date_col_index, '')
            
            else: # Інші ролі
                # Оновлюємо статус
                worksheet.update_cell(row_index, status_col_index, new_status)
                
                # 2. Оновлення Ніка та Дати (тільки для + або -)
                if status_char == '+':
                    current_date = datetime.now().strftime("%d.%m.%Y")
                    worksheet.update_cell(row_index, nick_col_index, nickname)
                    worksheet.update_cell(row_index, date_col_index, current_date)
                elif status_char == '-':
                    # Прибираємо нік та дату при відміні
                    worksheet.update_cell(row_index, nick_col_index, '')
                    worksheet.update_cell(row_index, date_col_index, '')

            # 3. Логування
            self._log_action(
                telegram_tag=telegram_tag,
                nickname=nickname,
                title=title_name,
                chapter=chapter_number,
                role=f"{role_key}{status_char}"
            )

            action = "завершено" if status_char == '+' else "скинуто"
            
            # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
            return f"✅ Статус **{role_key}** для розділу **{chapter_number}** у тайтлі *'{title_name}'* {action};"
            
        except gspread.WorksheetNotFound:
            return f"⚠️ Тайтл '{title_name}' не знайдено;"
        except Exception as e:
            logger.error(f"Помилка оновлення статусу: {e}")
            return "❌ Сталася помилка при оновленні статусу;"
    
# --- Обробники команд Telegram (зміни в parse_title_and_chapters та new_chapter) ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
    await update.message.reply_text("Привіт! Це бот для відстеження роботи над тайтлами; Використовуйте /help для списку команд;");

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 *Список доступних команд:*\n\n"
        "👤 `/register <нікнейм>`\n_Реєструє вас у системі;_\n\n"
        "👥 `/team \"Назва Тайтлу\"`\n_Встановлює команду для тайтлу; Бот запитає про ролі;_\n\n"
        # ВИПРАВЛЕННЯ: Додано приклад дробового розділу та діапазону
        "➕ `/newchapter \"Назва Тайтлу\" <номер_розділу|діапазон>`\n_Додає новий розділ(и) до тайтлу; Назву брати в лапки! Діапазон: 1-20; 20; 20.5; 20.1-20.5_\n\n"
        "📊 `/status \"Назва Тайтлу\" [номер_розділу|діапазон]`\n_Показує статус усіх розділів або вказаного діапазону;_\n\n"
        # ВИПРАВЛЕННЯ: Додано кому як розділювач для ніку
        "🔄 `/updatestatus \"Назва Тайтлу\" <розділ> <роль> <+|->; [нік з пробілами]`\n_Оновлює статус завдання; Нік необов'язковий; Ролі: клін; переклад; тайп; редакт; бета; публікація;_"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
    if not context.args:
        await update.message.reply_text("Будь ласка; вкажіть ваш нікнейм; Приклад: `/register SuperTranslator`")
        return
    nickname = " ".join(context.args)
    # ВИПРАВЛЕННЯ: Використовуємо sheets з контексту
    sheets = context.application.bot_data['sheets_helper']
    telegram_tag = f"@{user.username}" if user.username else user.full_name
    response = sheets.register_user(user.id, telegram_tag, nickname)
    await update.message.reply_text(response)

# ВИПРАВЛЕННЯ: Виправлення синтаксичної помилки з поверненням значень
def parse_title_and_args(text):
    """Парсер для команд; що містять назву тайтлу в лапках;"""
    match = re.search(r'\"(.*?)\"', text)
    if not match:
        # ВИПРАВЛЕННЯ: Змінено на повернення кортежу з двома елементами
        return None, " ".join(text.strip().split())
    title = match.group(1)
    # Повертаємо решту тексту як один рядок; а не список; для подальшого гнучкого парсингу
    remaining_text = text[match.end():].strip()
    return title, remaining_text 

# ЗМІНА 4: Оновлення parse_chapters_arg для підтримки дробових номерів
def parse_chapters_arg(chapter_arg):
    """Парсер для аргументу розділу/діапазону (використовується в new_chapter та status);"""
    if not chapter_arg:
        return None
        
    # Регулярний вираз для перевірки числових значень (цілі або дробові)
    num_pattern = r'(\d+(\.\d+)?)'

    # Перевірка на діапазон (наприклад; 1-20; 20.4-21.1)
    range_match = re.fullmatch(f'{num_pattern}-{num_pattern}', chapter_arg)
    
    if range_match:
        start_str = range_match.group(1)
        end_str = range_match.group(4) # Група 4 відповідає початку другого num_pattern
        
        try:
            start = float(start_str)
            end = float(end_str)
        except ValueError:
            return None # Невірний формат числа
        
        if start <= 0 or end <= 0 or start > end:
            return None # Невірний діапазон
            
        # Якщо обидва кінці — цілі; і діапазон більший за 1; генеруємо цілі
        if start == int(start) and end == int(end) and (end - start) >= 1:
            return [str(i) for i in range(int(start), int(end) + 1)]
            
        # Для дробового діапазону (або діапазону; де start=end; або вони обидва дробові)
        # Враховуємо тільки крайні точки (це обмеження; щоб не генерувати випадкові дробові)
        return [start_str, end_str] if start != end else [start_str]
    
    # Перевірка на єдиний розділ (цілий або дробовий)
    single_match = re.fullmatch(num_pattern, chapter_arg)
    if single_match:
        try:
            chapter = float(chapter_arg)
        except ValueError:
            return None
        
        if chapter <= 0:
            return None # Невірний номер
            
        # Повертаємо рядок; як його ввели; (щоб зберегти дробову частину)
        return [chapter_arg]
    
    return None # Невірний формат

def parse_title_and_chapters_for_new(full_text):
    """Парсер для /newchapter: тайтл та ОДИН розділ або діапазон (обов'язково);"""
    title, remaining_text = parse_title_and_args(full_text)
    
    if not title or not remaining_text:
        return None, None
    
    chapters = parse_chapters_arg(remaining_text)
    return title, chapters

# ЗМІНА 6: Новий парсер для /status
def parse_title_and_chapters_for_status(full_text):
    """Парсер для /status: тайтл та ОПЦІЙНИЙ розділ або діапазон;"""
    title, remaining_text = parse_title_and_args(full_text)
    
    if not title:
        return None, None
    
    # Якщо немає аргументів; повертаємо None для розділів (означає "всі")
    if not remaining_text:
        return title, None
        
    # Якщо є аргумент; парсимо його як розділ/діапазон
    chapters = parse_chapters_arg(remaining_text)
    return title, chapters

async def new_chapter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    full_text = " ".join(context.args)
    title, chapters = parse_title_and_chapters_for_new(full_text)
    
    if not title or not chapters:
        # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
        await update.message.reply_text('Невірний формат; Приклад: `/newchapter "Відьмоварта" 15`; `/newchapter "Відьмоварта" 1-20` або `/newchapter "Відьмоварта" 20.5`')
        return
    
    # ВИПРАВЛЕННЯ: Використовуємо sheets з контексту
    sheets = context.application.bot_data['sheets_helper']
    user = update.effective_user
    telegram_tag = f"@{user.username}" if user.username else user.full_name
    nickname = user.first_name if not user.username else f"@{user.username}"

    # Викликаємо нову функцію; яка обробляє список розділів
    response = sheets.add_chapters(title, chapters, telegram_tag, nickname)
    await update.message.reply_text(response)

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    full_text = " ".join(context.args)
    # ЗМІНА 7: Використовуємо новий парсер
    title, chapters = parse_title_and_chapters_for_status(full_text)
    
    if not title:
        # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
        await update.message.reply_text('Невірний формат; Приклад: `/status "Відьмоварта"` або `/status "Відьмоварта" 1-5`')
        return
    
    # ВИПРАВЛЕННЯ: Використовуємо sheets з контексту
    sheets = context.application.bot_data['sheets_helper']
    # ЗМІНА 8: Передаємо список розділів до get_status
    response = sheets.get_status(title, chapter_numbers=chapters)
    await update.message.reply_text(response, parse_mode="Markdown")

# --- ОНОВЛЕНИЙ ПАРСЕР ДЛЯ /updatestatus ---
def parse_updatestatus_args(full_text):
    """Парсер для /updatestatus; підтримує нікнейм з пробілами після коми;"""
    title, remaining_text = parse_title_and_args(full_text)
    
    if not title:
        return None, None, None, None, None # Додано повернення None для nickname
        
    # Формат: <розділ> <роль> <+|->; [нік з пробілами]
    # Розділяємо рядок на 3+ частини: <розділ> <роль> <+|-> та решта (нік)
    parts = remaining_text.split('; ') # Використовуємо крапку з комою як розділювач

    if len(parts) < 1:
        return title, None, None, None, None # Додано повернення None для nickname

    main_args = parts[0].strip().split()
    
    # Очікуємо 3 основних аргументи
    if len(main_args) != 3:
        return title, None, None, None, None # Додано повернення None для nickname
        
    chapter, role, status_char = main_args[0], main_args[1], main_args[2]

    # Перевірка основних аргументів
    num_pattern = r'^\d+(\.\d+)?$' # Ціле або дробове число
    if not re.fullmatch(num_pattern, chapter) or status_char not in ['+', '-']:
        return title, None, None, None, None # Додано повернення None для nickname
    
    nickname = None
    if len(parts) > 1:
        # Нік - це все; що йде після першої крапки з комою (і пробілу; який ми видалили split'ом)
        nickname = parts[1].strip()
        if not nickname:
            nickname = None # Якщо після крапки з комою нічого не було
            
    return title, chapter, role, status_char, nickname

async def update_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    full_text = " ".join(context.args)
    # ЗМІНА: Використовуємо новий парсер
    # ВИПРАВЛЕННЯ: Додано п'яту змінну для явного ніка
    title, chapter, role, status_char, explicit_nickname = parse_updatestatus_args(full_text)
    
    if not title or not chapter or not role or not status_char:
        # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
        await update.message.reply_text('Невірний формат; Приклад: `/updatestatus "Відьмоварта" 15 клін +` або `/updatestatus "Відьмоварта" 15 клін +; Super Translator`')
        return
    
    # ВИПРАВЛЕННЯ: Використовуємо sheets з контексту
    sheets = context.application.bot_data['sheets_helper']
    user = update.effective_user
    
    # --- ОНОВЛЕННЯ ЛОГІКИ ВИЗНАЧЕННЯ НІКНЕЙМА ---
    if explicit_nickname:
        # 1. Нік вказано в команді (після крапки з комою)
        nickname = explicit_nickname
    else:
        # 2. Нік не вказано; шукаємо зареєстрований
        registered_nickname = sheets.get_nickname_by_id(user.id)
        
        if registered_nickname:
            # Використовуємо зареєстрований нік
            nickname = registered_nickname
        else:
            # 3. Якщо нік не зареєстрований; беремо з Telegram-профілю (як fallback)
            nickname = user.first_name
            if user.username:
                nickname = f"@{user.username}"
            
    # Telegram-тег для логування
    telegram_tag = f"@{user.username}" if user.username else user.full_name

    # Передаємо telegram_tag до методу update_chapter_status
    response = sheets.update_chapter_status(title, chapter, role, status_char, nickname, telegram_tag)
    await update.message.reply_text(response)

# --- ОБРОБНИК КОМАНДИ /team ---
async def team_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє команду /team \"Назва тайтлу\" та запитує ніки для ролей;"""
    full_text = " ".join(context.args)
    title, _ = parse_title_and_args(full_text)
    
    if not title:
        # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
        await update.message.reply_text('Невірний формат; Приклад: `/team "Назва Тайтлу"`')
        return

    # Зберігаємо тайтл у контексті користувача для наступного кроку
    context.user_data['setting_team_for_title'] = title
    
    # Початкове запитання
    prompt = (
        # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
        f"Встановлення команди для тайтлу **'{title}'**; "
        "Будь ласка; введіть ніки в наступному форматі:\n\n"
        "`клін - нік; переклад - нік; тайп - нік; редакт - нік; [бета - нік]`\n\n"
        "Наприклад: `клін - Клінер; переклад - Перекладач; тайп - Тайпер; редакт - Редактор; бета - БетаТест`\n"
        "Бета є необов'язковою;"
    )
    context.user_data['awaiting_team_input'] = True
    
    await update.message.reply_text(prompt, parse_mode="Markdown")

# Обробник текстових повідомлень; який буде слухати після /team
async def handle_team_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє введення користувача після команди /team;"""
    # Перевіряємо; чи ми очікуємо введення команди і чи є тайтл у контексті
    if context.user_data.get('awaiting_team_input') and 'setting_team_for_title' in context.user_data:
        title_name = context.user_data['setting_team_for_title']
        raw_input = update.message.text
        
        # Регулярний вираз для парсингу: роль - нік
        pattern = re.compile(r'(клін|переклад|тайп|редакт|ред|бета)\s*-\s*([^;]+)', re.IGNORECASE)
        matches = pattern.findall(raw_input)
        
        team_nicks = {}
        for role, nick in matches:
            role_lower = role.lower()
            if role_lower == 'ред':
                role_lower = 'редакт'
            team_nicks[role_lower] = nick.strip()

        # Обов'язкові ролі
        required_roles = ['клін', 'переклад', 'тайп', 'редакт']
        missing_roles = [r for r in required_roles if r not in team_nicks]

        if missing_roles:
            # Очищуємо контекст і повертаємо помилку
            del context.user_data['awaiting_team_input']
            del context.user_data['setting_team_for_title']
            # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
            return await update.message.reply_text(
                f"❌ Помилка: Не вказано обов'язкові ролі: {'; '.join(missing_roles)}; Спробуйте ще раз; починаючи з `/team`;"
            )

        # Створення загального рядка команди для клітинки A2
        team_string_parts = []
        beta_nickname = ""
        for role_key in required_roles:
            # ВИПРАВЛЕННЯ: Використовуємо крапку з комою як розділювач в team_string
            team_string_parts.append(f"{role_key} - {team_nicks[role_key]}")
        
        if 'бета' in team_nicks:
            beta_nickname = team_nicks['бета']
            # ВИПРАВЛЕННЯ: Використовуємо крапку з комою як розділювач в team_string
            team_string_parts.append(f"бета - {beta_nickname}")

        # ВИПРАВЛЕННЯ: Використовуємо крапку з комою як розділювач в team_string
        final_team_string = "; ".join(team_string_parts)

        # Отримуємо дані користувача для логування
        user = update.effective_user
        telegram_tag = f"@{user.username}" if user.username else user.full_name
        nickname = user.first_name if not user.username else f"@{user.username}"

        # ВИПРАВЛЕННЯ: Використовуємо sheets з контексту
        sheets = context.application.bot_data['sheets_helper']
        response = sheets.set_team(title_name, final_team_string, beta_nickname, telegram_tag, nickname)

        # Очищуємо контекст
        del context.user_data['awaiting_team_input']
        del context.user_data['setting_team_for_title']

        await update.message.reply_text(response, parse_mode="Markdown")
        
        return

# --- MAIN RUNNER ---

async def run_bot():
    """Основна функція для запуску бота;"""
    # Додати до функції async def run_bot():

    # ПЕРЕВІРКА 1: TELEGRAM_BOT_TOKEN
    # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Критична помилка: Змінна середовища TELEGRAM_BOT_TOKEN не встановлена; Бот не буде запущений;")
        return
    
    # ПЕРЕВІРКА 2: SPREADSHEET_KEY
    # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
    if not SPREADSHEET_KEY:
        logger.error("Критична помилка: Змінна середовища SPREADSHEET_KEY не встановлена; Вкажіть ID вашої Google Таблиці; Бот не буде запущений;")
        return
    
    # Ініціалізація SheetsHelper
    # ВИПРАВЛЕННЯ СИНТАКСИЧНОЇ ПОМИЛКИ: Крапка з комою замінена на кому (роздільник аргументів)
    sheets_helper = SheetsHelper(GOOGLE_CREDENTIALS_FILE, SPREADSHEET_KEY)
    if not sheets_helper.spreadsheet:
        # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
        logger.error("Не вдалося ініціалізувати Google Sheets; Бот не буде запущений;")
        return

    # Ініціалізація Telegram-бота
    bot_app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    bot_app.bot_data['sheets_helper'] = sheets_helper
    
    # Команди
    bot_app.add_handler(CommandHandler("start", start_command))
    bot_app.add_handler(CommandHandler("help", help_command))
    bot_app.add_handler(CommandHandler("register", register))
    bot_app.add_handler(CommandHandler("team", team_command))
    bot_app.add_handler(CommandHandler("newchapter", new_chapter))
    bot_app.add_handler(CommandHandler("status", status))
    bot_app.add_handler(CommandHandler("updatestatus", update_status))
    
    # Обробник для відповіді на команду /team
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_team_input))

 # запуск бота для вебхуків
    await bot_app.initialize()
    await bot_app.start()

    if not hasattr(bot_app, 'update_queue'):
        # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
        logger.error("bot_app has no update_queue attribute!")
        return
        
    # 4. Налаштування веб-сервера aiohttp
    aio_app = web.Application()
    aio_app['bot_app'] = bot_app # Зберігаємо Application у додатку aiohttp
    
    async def webhook_handler(request):
        """Обробник вхідних POST-запитів від Telegram;"""
        bot_app = request.app['bot_app']
        # Отримання та десеріалізація оновлення з тіла запиту
        try:
            update = Update.de_json(await request.json(), bot_app.bot)
        except Exception as e:
            # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
            logger.error(f"Помилка десеріалізації оновлення: {e}")
            return web.Response(status=400)
            
        # Поміщення оновлення в чергу Application
        await bot_app.update_queue.put(update)
        return web.Response() # Telegram очікує 200 OK
    
    # Встановлення вебхука на сервері Telegram
    webhook_path = '/' + TELEGRAM_BOT_TOKEN
    full_webhook_url = WEBHOOK_URL.rstrip('/') + webhook_path
    
    await bot_app.bot.set_webhook(url=full_webhook_url)
    # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
    logger.info(f"Встановлено Webhook на: {full_webhook_url}")
    
    # 5. Налаштування маршрутів aiohttp
    # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
    # ВИПРАВЛЕННЯ СИНТАКСИЧНОЇ ПОМИЛКИ: Крапка з комою замінена на кому (роздільник елементів списку)
    aio_app.add_routes([
        web.get('/health', lambda r: web.Response(text='OK')), # Перевірка працездатності
        web.post(webhook_path, webhook_handler), # Обробник для Telegram
    ])

    # 6. Запуск веб-сервера
    runner = web.AppRunner(aio_app)
    await runner.setup()
    
    port = int(os.environ.get("PORT", 8080))
    # '0.0.0.0' дозволяє слухати на всіх доступних інтерфейсах (важливо для Render)
    site = web.TCPSite(runner, '0.0.0.0', port)
    # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
    logger.info(f"Starting web server on port {port}")
    await site.start()

    # Запобігання виходу головного циклу
    while True:
        await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
        logger.info("Бот зупинено користувачем;")
    except Exception as e:
        # ВИПРАВЛЕННЯ: Використовуємо крапку з комою замість коми
        logger.error(f"Критична помилка запуску: {e}")