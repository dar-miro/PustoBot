import re

def parse_message(text, thread_title=None, bot_username=None):
    """
    Парсить повідомлення користувача на складові:
    - тайтл (або береться з thread_title)
    - розділ (chapter)
    - позиція (position)
    - нікнейм (nickname) — необов’язковий
    """

    parts = text.strip().split()

    # Якщо текст починається з @бота — пропускаємо цей тег
    if bot_username and parts and parts[0].lower() == f"@{bot_username.lower()}":
        parts = parts[1:]

    # Якщо в контексті вже є thread_title, беремо його, не шукаємо в тексті
    if thread_title:
        if len(parts) >= 2:
            chapter, position = parts[:2]
            nickname = parts[2] if len(parts) > 2 else None
            return thread_title, chapter, position, nickname
        return None

    # Якщо thread_title немає — шукаємо номер розділу як першу цифру в тексті
    for i, part in enumerate(parts):
        if re.match(r"^\d+$", part):
            title = " ".join(parts[:i])
            chapter = part
            position = parts[i + 1] if i + 1 < len(parts) else None
            nickname = parts[i + 2] if i + 2 < len(parts) else None

            if position:
                return title, chapter, position, nickname
            return "error"

    # Якщо нічого не підійшло
    return "error"