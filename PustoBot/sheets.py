import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

# Головні аркуші
log_sheet = client.open("DataBase").worksheet("Журнал")
main_sheet = client.open("DataBase").sheet1  # Таблиця для адміністраторів

def get_main_sheet():
    return main_sheet

def get_user_sheet():
    try:
        return main_sheet.spreadsheet.worksheet("Користувачі")
    except:
        return main_sheet.spreadsheet.add_worksheet("Користувачі", rows=100, cols=3)

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
