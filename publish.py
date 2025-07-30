from telegram import Update
from telegram.ext import ContextTypes
from datetime import datetime
from PustoBot.sheets import load_nickname_map, normalize_title  # Імпортуємо normalize_title
import gspread
import logging # ДОДАНО: Імпорт модуля logging

# ДОДАНО: Ініціалізація логера
logger = logging.getLogger(__name__)

ROLES = ["Клін", "Переклад", "Тайп", "Редакт"]

async def publish_command(update: Update, context: ContextTypes.DEFAULT_TYPE, sheet):
    message = update.message
    if not message or not message.text:
        return

    args = message.text.strip().split()
    if len(args) < 3:
        await update.message.reply_text("⚠️ Використання: /publish Назва_Тайтлу Розділ")
        return

    chapter = args[-1].strip()
    # Нормалізуємо тайтл для порівняння
    title = normalize_title(' '.join(args[1:-1]))


    # Отримуємо нік із таблиці "Користувачі"
    user_fullname = update.message.from_user.full_name
    # ВИПРАВЛЕНО: load_nickname_map не приймає аргументів
    nickname_map = load_nickname_map() 
    user_nickname = nickname_map.get(user_fullname, user_fullname)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    try:
        rows = sheet.get_all_values()
        if not rows:
            await update.message.reply_text("⚠️ Таблиця 'Тайтли' порожня.")
            return

        headers = rows[0]
        data = rows[1:]

        title_idx = headers.index("Тайтл")
        chapter_idx = headers.index("№ розділу")
        
        # Визначення індексів колонок для ролей
        role_indices = {
            "Клін": {"nick": headers.index("Нік (Клін)"), "date": headers.index("Дата (Клін)"), "status": headers.index("Статус (Клін)")},
            "Переклад": {"nick": headers.index("Нік (Переклад)"), "date": headers.index("Дата (Переклад)"), "status": headers.index("Статус (Переклад)")},
            "Тайп": {"nick": headers.index("Нік (Тайп)"), "date": headers.index("Дата (Тайп)"), "status": headers.index("Статус (Тайп)")},
            "Редакт": {"nick": headers.index("Нік (Редакт)"), "date": headers.index("Дата (Редакт)"), "status": headers.index("Статус (Редакт)")},
        }

    except ValueError as e:
        logger.error(f"Відсутня необхідна колонка в таблиці 'Тайтли': {e}") # ВИПРАВЛЕНО: використання логера
        await update.message.reply_text(f"⚠️ Помилка: не знайдено необхідну колонку в таблиці 'Тайтли' — {e}")
        return
    except gspread.exceptions.APIError as e:
        logger.error(f"Google Sheets API Error: {e}")
        await update.message.reply_text("⚠️ Помилка підключення до Google Sheets API. Зверніться до адміністратора.")
        return
    except Exception as e:
        logger.error(f"Неочікувана помилка в publish_command: {e}")
        await update.message.reply_text("⚠️ Виникла неочікувана помилка. Зверніться до адміністратора.")
        return

    updated_rows_count = 0
    title_found = False

    # Спроба знайти тайтл за нормалізованою назвою
    for i, row in enumerate(data):
        # Перевіряємо, чи рядок має достатньо колонок, щоб уникнути IndexError
        if len(row) <= max(title_idx, chapter_idx):
            continue
        
        # Порівнюємо нормалізовані назви тайтлів та точний розділ
        if normalize_title(row[title_idx]) == title and row[chapter_idx].strip() == chapter:
            title_found = True
            row_num_in_sheet = i + 2 # Рядок у Google Sheet (з урахуванням заголовків)
            
            # Оновлюємо статус для кожної ролі, якщо вона вже присутня в рядку
            for role_name, col_info in role_indices.items():
                if len(row) > col_info['status'] and row[col_info['nick']].strip(): # Перевіряємо, чи нік ролі вже заповнений
                    try:
                        sheet.update_cell(row_num_in_sheet, col_info['status'] + 1, "✅")
                        updated_rows_count += 1
                    except gspread.exceptions.APIError as e:
                        logger.error(f"Помилка оновлення статусу в Google Sheets для {title} {chapter} {role_name}: {e}")
                        await update.message.reply_text(f"⚠️ Помилка оновлення статусу для {role_name}. Спробуйте ще раз.")
                        return

            # Якщо оновили існуючий розділ, ми зробили свою справу
            if updated_rows_count > 0:
                await update.message.reply_text(f"✅ Для тайтлу *{normalize_title(title)}* розділ *{chapter}* оновлено статус до '✅'.", parse_mode="Markdown")
                return
            break # Розділ знайдено та оновлено, виходимо

    if not title_found:
        # Якщо тайтл або розділ не знайдено, можливо, треба додати новий рядок
        # Знаходимо останній рядок у таблиці, щоб додати новий
        try:
            last_row_index = len(sheet.get_all_values())
            new_row_data = [""] * len(headers) # Створюємо порожній рядок за розміром заголовків
            
            # Заповнюємо дані для нового рядка
            new_row_data[title_idx] = title
            new_row_data[chapter_idx] = chapter

            # Заповнюємо статус "✅" та нік для всіх ролей (або лише для тих, що є)
            for role_name, col_info in role_indices.items():
                new_row_data[col_info['nick']] = user_nickname # Можна залишити порожнім або додати user_nickname
                new_row_data[col_info['date']] = now
                new_row_data[col_info['status']] = "✅"
            
            sheet.insert_row(new_row_data, index=last_row_index + 1)
            await update.message.reply_text(f"✅ Додано новий запис для тайтлу *{normalize_title(title)}* розділ *{chapter}* з початковим статусом '✅'.", parse_mode="Markdown")
        except gspread.exceptions.APIError as e:
            logger.error(f"Помилка додавання нового рядка в Google Sheets для {title} {chapter}: {e}")
            await update.message.reply_text("⚠️ Помилка додавання нового запису. Спробуйте ще раз.")
        except Exception as e:
            logger.error(f"Неочікувана помилка при додаванні нового рядка: {e}")
            await update.message.reply_text("⚠️ Виникла неочікувана помилка. Зверніться до адміністратора.")