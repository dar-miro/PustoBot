import re
from collections import defaultdict

def parse_message(text, thread_title=None, bot_username=None):
    """
    Парсить повідомлення користувача на складові:
    - тайтл (або береться з thread_title)
    - розділ (chapter)
    - роль (role)
    - нікнейм (nickname) — необов’язковий
    """
    if text is None:
        return None

    stripped_text = text.strip()
    if not stripped_text:
        return None

    parts = stripped_text.split()

    # Визначаємо список допустимих ролей
    role_keywords = ["клін", "переклад", "тайп", "ред", "редакт"]

    # Якщо текст починається з @бота — пропускаємо цей тег
    if bot_username and parts and parts[0].lower() == f"@{bot_username.lower()}":
        parts = parts[1:]
    
    # Якщо бот був згаданий в середині тексту, то він теж може бути пропущений
    parts = [part for part in parts if part.lower() != f"@{bot_username.lower()}"]
    
    if not parts:
        return None

    # Спробуємо розпарсити формат для гілки: "Розділ Роль [Нік]"
    if thread_title and len(parts) >= 2:
        # Перевіряємо, чи перший елемент - це число, а другий - роль
        if re.match(r"^\d+$", parts[0]) and parts[1].lower() in role_keywords:
            chapter = parts[0]
            role = parts[1].lower()
            nickname = parts[2] if len(parts) > 2 else None
            return thread_title, chapter, role, nickname

    # Спробуємо розпарсити повний формат: "Тайтл Розділ Роль [Нік]"
    # Знаходимо кінець назви тайтлу
    title_parts = []
    i = 0
    while i < len(parts):
        # Якщо наступний елемент - це число, а за ним - роль, це кінець назви тайтлу
        if re.match(r"^\d+$", parts[i]) and i + 1 < len(parts) and parts[i+1].lower() in role_keywords:
            break
        title_parts.append(parts[i])
        i += 1
    
    title = " ".join(title_parts).strip()
    
    if not title or i >= len(parts):
        return None

    chapter = parts[i]
    role = parts[i+1].lower()
    nickname = parts[i+2] if len(parts) > i + 2 else None
    
    return title, chapter, role, nickname

def parse_members_string(text):
    """
    Парсить рядок з учасниками для команди /thread.
    Формат: `клін - Nick1, переклад - Nick2`
    Повертає: (title, {role: [nick1, nick2], ...})
    """
    parts = text.split()
    if not parts:
        return None, {}

    title_parts = []
    roles_map = defaultdict(list)
    current_role = None
    role_keywords = ["клін", "переклад", "тайп", "ред", "редакт"]

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
        elif current_role and part != "-": # Якщо є поточна роль і це не роз'єднувальний символ
            roles_map[current_role].append(part)
        
        i += 1
    
    return title, roles_map