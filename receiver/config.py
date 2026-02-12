import os
from dotenv import load_dotenv

load_dotenv()

# JWT
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production").strip()  # Remove espaços e quebras de linha

# PostgreSQL
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_DATABASE = os.getenv("DB_DATABASE", "sspsanguesuga")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

# Base URL da API (para documentação)
BASE_URL = os.getenv("BASE_URL", "http://localhost:8080")

# Itens em "processando" há mais que N minutos voltam para "pendente" (queda do worker)
FILA_PROCESSANDO_TIMEOUT_MINUTES = int(os.getenv("FILA_PROCESSANDO_TIMEOUT_MINUTES", "15"))
