# PustoBot/core.py
import re
from collections import defaultdict

def parse_message(text, thread_title=None, bot_username=None, from_user_tag=None):
    """
    Парсить повідомлення користувача на складові:
    - title_identifier: Назва Тайтлу (для повного формату) або Номер Тайтлу (для гілки)
    - розділ (chapter)
    - роль (role)
    - нікнейм (nickname) — необов’язковий
    
    Очікувані формати:
    1. У гілці (thread_title - це Номер Тайтлу): [НомерРозділу] [Роль] [Нік]
    2. Повна: [Назва Тайтлу] [НомерРозділу] [Роль] [Нік]
    """
    if text is None:
        return None

    stripped_text = text.strip()
    if not stripped_text:
        return None

    # Видаляємо тег бота, якщо він є на початку
    if bot_username and stripped_text.lower().startswith(f"@{bot_username.lower()}"):
        stripped_text = stripped_text[len(f"@{bot_username.lower()}"):].strip()

    parts = stripped_text.split()
    
    if not parts:
        return None

    # Визначаємо список допустимих ролей
    role_keywords = ["клін", "переклад", "тайп", "ред", "редакт"]

    found_role = None
    found_chapter = None
    found_nickname = None
    
    # 1. Спроба парсингу для ГІЛКИ (використовуючи Title Number з thread_title)
    # thread_title тут очікується як Номер Тайтлу (рядок)
    if thread_title and thread_title.isdigit(): 
        
        # Шукаємо розділ, роль і нікнейм серед частин
        for part in parts:
            lower_part = part.lower()
            if re.match(r'^\d+$', part) and found_chapter is None:
                found_chapter = part
            elif lower_part in role_keywords and found_role is None:
                found_role = lower_part
            elif found_role and found_nickname is None:
                found_nickname = part
                
        if found_chapter and found_role:
            # Title Identifier - це Номер Тайтлу з гілки
            return thread_title, found_chapter, found_role, found_nickname
            
    # 2. Спроба парсингу для ПОВНОГО ФОРМАТУ: [Назва Тайтлу] [НомерРозділу] [Роль] [Нік]
    
    temp_title_parts = []
    temp_chapter = None
    temp_role = None
    temp_nickname = None
    
    for part in parts:
        lower_part = part.lower()
        
        # Припускаємо, що перший знайдений поспіль набір: [НомерРозділу] [Роль]
        if re.match(r'^\d+$', part) and temp_chapter is None and temp_role is None:
            temp_chapter = part
        elif lower_part in role_keywords and temp_role is None:
            temp_role = lower_part
        elif temp_role and temp_nickname is None:
            temp_nickname = part
        elif temp_chapter is None and temp_role is None:
            # Це частина назви тайтлу
            temp_title_parts.append(part)

    title_identifier = " ".join(temp_title_parts).strip()
    
    # Перевіряємо, чи ми знайшли повний формат
    if title_identifier and temp_chapter and temp_role:
        return title_identifier, temp_chapter, temp_role, temp_nickname
        
    return None

def parse_members_string(text):
    """
    Парсить рядок для команди /thread.
    Новий формат: [TitleNumber] [TitleName...] клін - Nick1, переклад - Nick2 ...
    Повертає: (title_number, title_name, {role: nick})
    """
    parts = text.split()
    # Перша частина має бути номером
    if not parts or not re.match(r'^\d+$', parts[0]):
        return None, None, {}

    title_number = parts[0]
    parts = parts[1:] # Залишаємо решту частин
    
    title_parts = []
    roles_map = defaultdict(list)
    current_role = None
    role_keywords = ["клін", "переклад", "тайп", "ред", "редакт"]

    i = 0
    # Спочатку парсимо назву тайтлу до першого ключового слова ролі або розмежувача '-'
    while i < len(parts):
        if parts[i].lower() in role_keywords or parts[i] == '-':
            break
        title_parts.append(parts[i])
        i += 1
    
    title_name = " ".join(title_parts).strip()
    
    if not title_name:
        return None, None, {} # Назва тайтлу обов'язкова

    # Парсимо ролі
    while i < len(parts):
        part = parts[i].lower()
        if part in role_keywords:
            current_role = part
            i += 1
            # Пропускаємо ' - '
            if i < len(parts) and parts[i] == '-':
                i += 1
        elif current_role:
            # Збираємо нікнейм
            nick_parts = []
            while i < len(parts) and not parts[i].lower() in role_keywords and parts[i] not in [',']:
                nick_parts.append(parts[i])
                i += 1
            
            if nick_parts:
                # Зберігаємо нік як одну частину, бо в таблицю записується одна комірка
                roles_map[current_role] = [" ".join(nick_parts)] 
            
            # Пропускаємо кому, якщо є
            if i < len(parts) and parts[i] == ',':
                i += 1
            
            # Роль оброблена
            current_role = None
        else:
            i += 1 
            
    final_roles_map = {role: nicks[0] for role, nicks in roles_map.items() if nicks}
    
    return title_number, title_name, final_roles_map