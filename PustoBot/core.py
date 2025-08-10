# PustoBot/core.py
import re
from collections import defaultdict
from PustoBot.sheets import resolve_user_nickname

def parse_message(text, thread_title=None, bot_username=None, from_user_tag=None):
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

    # Видаляємо тег бота, якщо він є на початку
    if bot_username and stripped_text.lower().startswith(f"@{bot_username.lower()}"):
        stripped_text = stripped_text[len(f"@{bot_username.lower()}"):].strip()

    parts = stripped_text.split()
    
    if not parts:
        return None

    # Визначаємо список допустимих ролей
    role_keywords = ["клін", "переклад", "тайп", "ред", "редакт"]

    # Знаходимо всі ролі, розділи та нікнейми
    found_role = None
    found_chapter = None
    found_nickname = None
    other_parts = []

    for part in parts:
        lower_part = part.lower()
        if lower_part in role_keywords:
            found_role = lower_part
        elif re.match(r'^\d+$', part):
            found_chapter = part
        elif found_role and not found_nickname: # Нікнейм іде одразу після ролі
            found_nickname = part
        else:
            other_parts.append(part)

    title = " ".join(other_parts)
    if thread_title and not title:
        title = thread_title
    
    if not title or not found_chapter or not found_role:
        return None

    return title, found_chapter, found_role, found_nickname

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
        elif current_role:
            roles_map[current_role].append(part)
        i += 1
    
    return title, {role: " ".join(nicks) for role, nicks in roles_map.items()}