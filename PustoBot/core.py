def parse_message(text, thread_title=None, bot_username=None):
    parts = text.strip().split()
    if bot_username and parts and parts[0].lower() == f"@{bot_username.lower()}":
        parts = parts[1:]
    if len(parts) == 2 and thread_title:
        chapter, position = parts
        nickname = None
        title = thread_title
    elif len(parts) == 3 and thread_title:
        chapter, position, nickname = parts
        title = thread_title
    elif len(parts) == 3:
        title, chapter, position = parts
        nickname = None
    elif len(parts) >= 4:
        title, chapter, position = parts[:3]
        nickname = parts[3]
    else:
        return None
    return title, chapter, position, nickname
