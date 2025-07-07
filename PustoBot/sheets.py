import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
import re

# Авторизація
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

# Основні аркуші
main_spreadsheet = client.open("DataBase")
log_sheet = main_spreadsheet.worksheet("Журнал")
titles_sheet = main_spreadsheet.worksheet("Тайтли")

# Відповідність ролей і колонок
columns_by_role = {
    "клін": {"nick": "B", "date": "C", "check": "D"},
    "переклад": {"nick": "E", "date": "F", "check": "G"},
    "тайп": {"nick": "H", "date": "I", "check": "J"},
    "ред" or "редакт": {"nick": "K", "date": "L", "check": "M"},
}

def get_title_sheet():
    return titles_sheet

def normalize_title(t):
    return re.sub(r'\s+', ' ', t.strip().lower().replace("’", "'"))

def get_user_sheet():
    try:
        return main_spreadsheet.worksheet("Користувачі")
    except:
        return main_spreadsheet.add_worksheet("Користувачі", rows=100, cols=3)

def load_nickname_map():
    user_sheet = get_user_sheet()
    data = user_sheet.get_all_records()
    return {row["Telegram-нік"]: row["Нік"] for row in data if row.get("Telegram-нік") and row.get("Нік")}

def append_log_row(full_name, title, chapter, position, nickname):
    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M"),
        full_name,
        title,
        chapter,
        position,
        nickname
    ]
    log_sheet.append_row(row)

# 🔍 Автоматичне виявлення блоків тайтлів
def get_title_blocks():
    data = titles_sheet.get_all_values()
    blocks = []
    current_title = None
    start = None
    for i, row in enumerate(data):
        if row and row[0].strip() and not row[0].startswith("Розділ"):
            current_title = row[0].strip()
            start = i
        elif not any(row) and current_title:
            blocks.append((current_title, start, i))
            current_title = None
    if current_title:
        blocks.append((current_title, start, len(data)))
    return blocks

# ✍️ Оновлення таблиці по знайденому блоку
def update_title_table(title, chapter, role, nickname):
    role_columns = columns_by_role.get(role)
    if not role_columns:
        return False

    blocks = get_title_blocks()
    for block_title, start_row, end_row in blocks:
        if normalize_title(block_title) == normalize_title(title):
            rows = titles_sheet.get_all_values()[start_row:end_row]
            for i, row in enumerate(rows):
                if row and chapter.strip() in row[0]:
                    actual_row = start_row + i + 1
                    now = datetime.now().strftime("%Y-%m-%d")
                    titles_sheet.update_acell(f"{role_columns['nick']}{actual_row}", nickname)
                    titles_sheet.update_acell(f"{role_columns['date']}{actual_row}", now)
                    titles_sheet.update_acell(f"{role_columns['check']}{actual_row}", "✅")
                    return True
    return False

def set_main_roles(title, roles_map):
    data = titles_sheet.get_all_values()
    for i, row in enumerate(data):
        if normalize_title(row[0]) == normalize_title(title):
            for role, nick in roles_map.items():
                col_info = columns_by_role.get(role.lower())
                if col_info:
                    titles_sheet.update_acell(f"{col_info['nick']}{i+1}", nick)
            return True
    return False

