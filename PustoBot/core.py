# PustoBot/core.py
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
    if thread_title and len(parts) >= 2 and re.match(r"^\d+$", parts[0]) and parts[1].lower() in role_keywords:
        chapter = parts[0]
        role = parts[1].lower()
        nickname = parts[2] if len(parts) > 2 else None
        return thread_title, chapter, role, nickname

    # Спробуємо розпарсити повний формат: "Назва Тайтлу Розділ Роль [Нік]"
    # Знаходимо індекс, де починається розділ
    i = 0
    while i < len(parts) - 2:
        if re.match(r"^\d+$", parts[i]) and parts[i+1].lower() in role_keywords:
            title = " ".join(parts[:i])
            chapter = parts[i]
            role = parts[i+1].lower()
            nickname = parts[i+2] if len(parts) > i+2 else None
            return title, chapter, role, nickname
        i += 1

    return None

def parse_members_string(text):
    """
    Парсить рядок з учасниками для команди /thread.
    Формат: `клін - Nick1, переклад - Nick2`
    Повертає: (title, {role: [nick1, nick2], ...})
    """
    parts = text.split(',')
    roles_map = {}
    for part in parts:
        if '-' in part:
            role, nick = [p.strip() for p in part.split('-', 1)]
            roles_map[role.lower()] = nick
    
    # Ця функція більше не парсить тайтл, оскільки він береться з іншого місця.
    return roles_map