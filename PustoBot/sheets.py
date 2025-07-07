import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

# Аркуші
main_spreadsheet = client.open("DataBase")
log_sheet = main_spreadsheet.worksheet("Журнал")
titles_sheet = main_spreadsheet.worksheet("Тайтли")

columns_by_role = {
    "Клінер": {"nick": "B", "date": "C", "check": "D"},
    "Перекладач": {"nick": "E", "date": "F", "check": "G"},
    "Тайпер": {"nick": "H", "date": "I", "check": "J"},
    "Редактор": {"nick": "K", "date": "L", "check": "M"},
}

def get_main_sheet():
    return client.open("DataBase").worksheet("Тайтли")

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

def update_title_table(title, chapter, role, nickname):
    role_columns = columns_by_role.get(role)
    if not role_columns:
        return False

    all_data = titles_sheet.get_all_values()
    title_found = False
    for i, row in enumerate(all_data):
        if row and row[0].strip() == title:
            title_found = True
            continue
        if title_found and row and chapter in row[0]:
            row_index = i + 1  # +1 бо нумерація з 1
            now = datetime.now().strftime("%Y-%m-%d")
            titles_sheet.update_acell(f"{role_columns['nick']}{row_index}", nickname)
            titles_sheet.update_acell(f"{role_columns['date']}{row_index}", now)
            titles_sheet.update_acell(f"{role_columns['check']}{row_index}", "✅")
            return True
    return False
