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