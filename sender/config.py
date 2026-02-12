import os
from dotenv import load_dotenv

load_dotenv()

DB_SERVER = os.getenv("DB_SERVER", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "1433"))
DB_NAME = os.getenv("DB_NAME", "")
DB_USER = os.getenv("DB_USER", "")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_TABLE = os.getenv("DB_TABLE", "")
DB_ORDER_COLUMN = os.getenv("DB_ORDER_COLUMN", "")  # opcional: coluna para ORDER BY
DB_TIMEOUT = int(os.getenv("DB_TIMEOUT", "30"))
DB_LOGIN_TIMEOUT = int(os.getenv("DB_LOGIN_TIMEOUT", "10"))

API_BASE_URL = os.getenv("API_BASE_URL", "").rstrip("/")
API_JWT_TOKEN = os.getenv("API_JWT_TOKEN", "").strip()  # Remove espaços e quebras de linha

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1000"))

# Arquivo de estado para retomar após queda (caminho absoluto ou relativo ao sender)
STATE_FILE = os.getenv("STATE_FILE", os.path.join(os.path.dirname(__file__), ".sender_state.json"))

# Retry em caso de queda de conexão
RETRY_ATTEMPTS = int(os.getenv("RETRY_ATTEMPTS", "5"))
RETRY_BACKOFF_SECONDS = float(os.getenv("RETRY_BACKOFF_SECONDS", "5"))
