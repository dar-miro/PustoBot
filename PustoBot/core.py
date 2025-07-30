import re

def parse_message(text, thread_title=None, bot_username=None):
    """
    Парсить повідомлення користувача на складові:
    - тайтл (або береться з thread_title)
    - розділ (chapter)
    - позиція (position)
    - нікнейм (nickname) — необов’язковий
    """
    if text is None:
        return None

    stripped_text = text.strip()
    if not stripped_text:
        return None

    parts = stripped_text.split()

    # Якщо текст починається з @бота — пропускаємо цей тег
    if bot_username and parts and parts[0].lower() == f"@{bot_username.lower()}":
        parts = parts[1:]

    # Спробуємо спочатку розпарсити повний формат: "Тайтл Розділ Позиція Нік"
    # Шукаємо перше число, яке може бути розділом
    for i, part in enumerate(parts):
        if re.match(r"^\\d+$", part): # Знайшли потенційний розділ (число)
            if i > 0 and len(parts) > i + 1: # Перевіряємо, що є тайтл і позиція
                title_from_message = " ".join(parts[:i])
                chapter_from_message = part
                position_from_message = parts[i + 1]
                nickname_from_message = parts[i + 2] if i + 2 < len(parts) else None
                
                if title_from_message and chapter_from_message and position_from_message:
                    return title_from_message, chapter_from_message, position_from_message, nickname_from_message
            break # Зупиняємо пошук розділу, якщо знайшли число, але формат неповний


    # Якщо повний формат не знайдено в повідомленні, але є thread_title
    # і повідомлення має вигляд "Розділ Позиція Нік"
    if thread_title and len(parts) >= 2:
        chapter = parts[0]
        position = parts[1]
        nickname = parts[2] if len(parts) > 2 else None
        
        # Перевіримо, чи перший елемент дійсно схожий на розділ (число)
        # та другий на позицію
        if re.match(r"^\\d+$", chapter) and position:
            return thread_title, chapter, position, nickname
    
    return None # Якщо жоден з форматів не підходить


def parse_set_thread_command(text):
    """
    Парсить команду /thread для встановлення тайтлу та основних ролей.
    Формат: /thread Назва Тайтлу Клін - Нік1, Нік2 Переклад - Нік3 Тайп - Нік4 Ред - Нік5
    Повертає: (title, {role: [nick1, nick2], ...})
    """
    parts = text.split()
    if not parts:
        return None, {}

    title_parts = []
    roles_map = {}
    current_role = None
    role_keywords = ["клін", "переклад", "тайп", "ред", "редакт"] # Додано "редакт"

    i = 0
    # Спочатку парсимо назву тайтлу
    while i < len(parts):
        # Якщо знаходимо ключове слово ролі, то це кінець назви тайтлу
        if parts[i].lower() in role_keywords:
            break
        title_parts.append(parts[i])
        i += 1
    
    title = " ".join(title_parts).strip()
    if not title:
        return None, {}

    # Парсимо ролі
    while i < len(parts):
        part = parts[i].lower()
        if part in role_keywords:
            current_role = part
            # Якщо наступний елемент "-", пропускаємо його
            if i + 1 < len(parts) and parts[i+1] == "-":
                i += 1 
            roles_map[current_role] = []
        elif current_role and part != "-": # Якщо є поточна роль і це не роз'єднувальний "-"
            # Обробляємо кілька ніків через кому
            nicks_in_part = [n.strip() for n in part.split(',') if n.strip()]
            roles_map[current_role].extend(nicks_in_part)
        i += 1
    
    # Видаляємо дублікати та прибираємо пусті ніки
    for role, nicks in roles_map.items():
        roles_map[role] = sorted(list(set(n for n in nicks if n)))

    return title, roles_map