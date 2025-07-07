from PustoBot.sheets import normalize_title

thread_title_map = {}  # { thread_id: normalized_title }

def set_thread_title(thread_id, title):
    thread_title_map[thread_id] = normalize_title(title)

def get_thread_title(thread_id):
    return thread_title_map.get(thread_id)
