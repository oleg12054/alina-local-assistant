MODEL_NAME = "qwen3:8b"
OLLAMA_URL = "http://localhost:11434/api/chat"
REQUEST_TIMEOUT = 600
KEEP_ALIVE = "10m"

# --- интернет-инструмент ---
WEB_ENABLED = True
WEB_TIMEOUT = 150
WEB_SEARCH_MAX_RESULTS = 12
WEB_FETCH_MAX_PAGES = 8

# Мягкое ограничение: чтобы модель не зацикливалась в поиске
MAX_WEB_STEPS = 2