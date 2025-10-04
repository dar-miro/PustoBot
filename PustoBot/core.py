# PustoBot/core.py
import re
from collections import defaultdict

def parse_message(text, thread_title_or_number=None, bot_username=None, from_user_tag=None):
    """
    Парсить повідомлення користувача на складові.
    - title_identifier: Назва Тайтлу (для повного формату) або Номер Тайтлу (для гілки)
    - розділ (chapter)
    - роль (role)
    - нікнейм (nickname) — необов’язковий
    
    Очікувані формати:
    1. У гілці (thread_title_or_number - це Номер Тайтлу): [НомерРозділу] [Роль] [Нік]
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

    role_keywords = ["клін", "переклад", "тайп", "ред", "редакт"]

    # Формат 1: У гілці "Розділ Роль [Нік]" (використовуємо thread_title_or_number)
    if thread_title_or_number and len(parts) >= 2 and parts[0].isdigit():
        chapter = parts[0]
        role = parts[1].lower()
        nickname = parts[2] if len(parts) > 2 else None
        
        if role in role_keywords:
            return {
                'title_identifier': thread_title_or_number,
                'chapter': chapter,
                'role': role,
                'nickname': nickname
            }

    # Формат 2: Повна "Назва Розділ Роль [Нік]"
    if len(parts) >= 3:
        # Шукаємо кінець назви тайтлу (перед номером розділу)
        for i in range(1, len(parts) - 1):
            # Якщо поточний елемент - це цифра (розділ)
            if parts[i].isdigit():
                # Перевіряємо, чи наступний елемент - це роль
                if i + 1 < len(parts) and parts[i+1].lower() in role_keywords:
                    title_identifier = " ".join(parts[:i]).strip()
                    chapter = parts[i]
                    role = parts[i+1].lower()
                    nickname = parts[i+2] if len(parts) > i + 2 else None

                    if title_identifier:
                        return {
                            'title_identifier': title_identifier,
                            'chapter': chapter,
                            'role': role,
                            'nickname': nickname
                        }
                    break
    
    return None