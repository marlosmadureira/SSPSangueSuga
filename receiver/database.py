import psycopg2
from psycopg2 import pool
from contextlib import contextmanager
from typing import Optional
import config

# Pool de conexões PostgreSQL
_connection_pool: Optional[pool.ThreadedConnectionPool] = None


def init_db_pool():
    """Inicializa o pool de conexões com PostgreSQL"""
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            host=config.DB_HOST,
            port=config.DB_PORT,
            database=config.DB_DATABASE,
            user=config.DB_USER,
            password=config.DB_PASSWORD
        )
    return _connection_pool


@contextmanager
def get_db_connection():
    """Context manager para obter conexão do pool"""
    pool = init_db_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


def close_db_pool():
    """Fecha o pool de conexões"""
    global _connection_pool
    if _connection_pool:
        _connection_pool.closeall()
        _connection_pool = None
