#!/usr/bin/env python3
"""
Envia dados de uma tabela SQL Server para a API de destino em lotes de 1000.
Retoma de onde parou após queda de energia ou conexão (checkpoint em arquivo).
Uso: python sender.py
"""
import json
import os
import time
from datetime import date, datetime
from typing import Any, Iterator, List, Optional, Tuple

try:
    import pymssql
    PYMSSQL_AVAILABLE = True
except ImportError:
    PYMSSQL_AVAILABLE = False

import requests

from config import (
    API_BASE_URL,
    API_JWT_TOKEN,
    BATCH_SIZE,
    DB_LOGIN_TIMEOUT,
    DB_NAME,
    DB_ORDER_COLUMN,
    DB_PASSWORD,
    DB_PORT,
    DB_SERVER,
    DB_TABLE,
    DB_TIMEOUT,
    DB_USER,
    RETRY_ATTEMPTS,
    RETRY_BACKOFF_SECONDS,
    STATE_FILE,
)


def print_color(message: str, color_code: int = 0) -> None:
    """Imprime mensagem com código de cor ANSI."""
    print(f"\033[{color_code}m{message}\033[0m")


def format_table_name(table_name: str) -> str:
    """
    Formata o nome da tabela para SQL Server, suportando schema.tabela.
    Exemplos:
    - "Usuario" -> "[Usuario]"
    - "SchEventos.Usuario" -> "[SchEventos].[Usuario]"
    - "[SchEventos].[Usuario]" -> "[SchEventos].[Usuario]" (mantém como está)
    """
    if not table_name:
        return table_name
    
    # Se já tem colchetes, retorna como está
    if table_name.startswith('[') and table_name.endswith(']'):
        return table_name
    
    # Divide por ponto para separar schema e tabela
    parts = table_name.split('.')
    
    # Remove espaços e adiciona colchetes em cada parte
    formatted_parts = [f"[{part.strip()}]" for part in parts]
    
    return '.'.join(formatted_parts)


def get_connection():
    if not PYMSSQL_AVAILABLE:
        print_color("❌ pymssql não está instalado. Execute: pip install pymssql", 31)
        return None

    try:
        conn = pymssql.connect(
            server=DB_SERVER,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD,
            timeout=DB_TIMEOUT,
            login_timeout=DB_LOGIN_TIMEOUT
        )
        print_color("✅ Conexão Aberta com sucesso.", 32)
        return conn
    except pymssql.OperationalError as e:
        print_color(f"❌ Erro operacional: {e}", 31)
        return None
    except pymssql.DatabaseError as e:
        print_color(f"❌ Erro de banco de dados: {e}", 31)
        return None


def rows_to_dict(cursor) -> List[dict]:
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def serializar_para_estado(val: Any) -> Any:
    """Serializa valor do banco para JSON (ex.: datetime -> string)."""
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return val


def load_state() -> dict:
    if not os.path.isfile(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_state(state: dict) -> None:
    path = STATE_FILE
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=0)
    os.replace(tmp, path)


def obter_schema_tabela(conn) -> list:
    """
    Obtém a estrutura da tabela no SQL Server (INFORMATION_SCHEMA.COLUMNS).
    Retorna lista de dicts com nome, tipo_sqlserver, max_length, numeric_precision, numeric_scale, is_nullable.
    """
    parts = DB_TABLE.replace("[", "").replace("]", "").split(".")
    if len(parts) == 2:
        schema_name, table_name = parts[0].strip(), parts[1].strip()
    else:
        schema_name, table_name = "dbo", parts[0].strip() if parts else ""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT
            COLUMN_NAME,
            DATA_TYPE,
            CHARACTER_MAXIMUM_LENGTH,
            NUMERIC_PRECISION,
            NUMERIC_SCALE,
            IS_NULLABLE
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
    """, (schema_name, table_name))
    rows = cursor.fetchall()
    cursor.close()
    return [
        {
            "nome": row[0],
            "tipo_sqlserver": (row[1] or "varchar").lower(),
            "max_length": row[2] if row[2] is not None and row[2] >= 0 else None,
            "numeric_precision": row[3],
            "numeric_scale": row[4],
            "is_nullable": (row[5] or "YES").upper() == "YES",
        }
        for row in rows
    ]


def nome_tabela_postgres() -> str:
    """Nome da tabela no PostgreSQL (schema_tabela ou tabela, sem caracteres especiais)."""
    s = DB_TABLE.replace("[", "").replace("]", "").strip()
    return s.replace(".", "_").replace(" ", "_") or "tabela"


def enviar_definicao_tabela() -> bool:
    """Envia a definição da tabela para o receiver (POST /api/tabela/definir). Retorna True se OK."""
    conn = get_connection()
    if conn is None:
        raise Exception("Não foi possível conectar ao SQL Server para obter o schema")
    try:
        colunas = obter_schema_tabela(conn)
        conn.close()
    except Exception as e:
        conn.close()
        raise e
    if not colunas:
        raise Exception(f"Nenhuma coluna encontrada para a tabela {DB_TABLE}")
    # URL do receiver: ex. http://host:8080/api -> http://host:8080/api/tabela/definir
    base = API_BASE_URL.rstrip("/")
    url = f"{base}/tabela/definir"
    headers = {
        "Authorization": f"Bearer {API_JWT_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "nome_tabela": nome_tabela_postgres(),
        "colunas": colunas,
    }
    r = requests.post(url, json=payload, headers=headers, timeout=30)
    r.raise_for_status()
    return True


def iterar_lotes(state: dict) -> Iterator[Tuple[List[dict], dict, str]]:
    """
    Gera (lote, novo_estado, checkpoint_key).
    checkpoint_key identifica este lote para idempotência no receiver.
    """
    conn = get_connection()
    if conn is None:
        raise Exception("Não foi possível estabelecer conexão com o banco de dados")
    cursor = conn.cursor()

    # Formata o nome da tabela (suporta schema.tabela)
    table_name = format_table_name(DB_TABLE)

    if DB_ORDER_COLUMN:
        # Paginação por chave: retoma após last_order_value (mais estável que OFFSET)
        col = f"[{DB_ORDER_COLUMN}]"
        last_val = state.get("last_order_value")
        while True:
            if last_val is None:
                tsql = f"""
                SELECT * FROM {table_name}
                ORDER BY {col}
                OFFSET 0 ROWS FETCH NEXT %s ROWS ONLY
                """
                cursor.execute(tsql, (BATCH_SIZE,))
            else:
                tsql = f"""
                SELECT * FROM {table_name}
                WHERE {col} > %s
                ORDER BY {col}
                OFFSET 0 ROWS FETCH NEXT %s ROWS ONLY
                """
                cursor.execute(tsql, (last_val, BATCH_SIZE))
            batch = rows_to_dict(cursor)
            if not batch:
                break
            # Último valor da coluna de ordenação neste lote
            col_index = [c[0] for c in cursor.description].index(DB_ORDER_COLUMN)
            last_in_batch = batch[-1][DB_ORDER_COLUMN]
            new_state = {"last_order_value": serializar_para_estado(last_in_batch)}
            checkpoint_key = f"k_{serializar_para_estado(last_in_batch)}"
            yield batch, new_state, checkpoint_key
            last_val = last_in_batch
            if len(batch) < BATCH_SIZE:
                break
    else:
        # Paginação por OFFSET: retoma a partir do offset salvo
        offset = state.get("offset", 0)
        order_by = "(SELECT NULL)"
        while True:
            tsql = f"""
            SELECT * FROM {table_name}
            ORDER BY {order_by}
            OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
            """
            cursor.execute(tsql, (offset, BATCH_SIZE))
            batch = rows_to_dict(cursor)
            if not batch:
                break
            next_offset = offset + len(batch)
            new_state = {"offset": next_offset}
            checkpoint_key = f"offset_{next_offset}"
            yield batch, new_state, checkpoint_key
            offset = next_offset
            if len(batch) < BATCH_SIZE:
                break

    cursor.close()
    conn.close()


def enviar_lote(lote: List[dict], checkpoint_key: str, nome_tabela: Optional[str] = None) -> bool:
    url = f"{API_BASE_URL.rstrip('/')}/lotes"
    headers = {
        "Authorization": f"Bearer {API_JWT_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "registros": lote,
        "total": len(lote),
        "checkpoint_key": checkpoint_key,
    }
    if nome_tabela:
        payload["nome_tabela"] = nome_tabela
    r = requests.post(url, json=payload, headers=headers, timeout=60)
    r.raise_for_status()
    return True


def main():
    if not all([DB_TABLE, API_BASE_URL, API_JWT_TOKEN]):
        print("Configure DB_TABLE, API_BASE_URL e API_JWT_TOKEN no .env")
        return 1

    state = load_state()
    if state:
        print("Retomando de onde parou (checkpoint anterior encontrado).")

    # Nome da tabela no PostgreSQL (para criar/inserir no receiver)
    nome_tabela_pg = nome_tabela_postgres()

    # Antes do primeiro lote: garantir que a tabela existe no receiver (enviar definição).
    # Se já existir no PostgreSQL, o receiver não recria e só insere.
    try:
        enviar_definicao_tabela()
        print(f"Estrutura da tabela '{nome_tabela_pg}' enviada ao receiver (criada se não existir).")
    except requests.RequestException as e:
        print(f"Aviso: não foi possível definir tabela no receiver: {e}")
        print(f"Enviando lotes com nome_tabela {DB_TABLE} mesmo assim (receiver insere se a tabela já existir).")
        # Mantém nome_tabela_pg para inserção direta; se a tabela não existir, o receiver retornará erro.
    except Exception as e:
        print(f"Aviso: erro ao obter/enviar schema: {e}")
        nome_tabela_pg = None

    total_enviados = 0
    num_lote = 0

    try:
        for lote, new_state, checkpoint_key in iterar_lotes(state):
            for attempt in range(1, RETRY_ATTEMPTS + 1):
                try:
                    enviar_lote(lote, checkpoint_key, nome_tabela=nome_tabela_pg)
                    break
                except requests.RequestException as e:
                    if attempt == RETRY_ATTEMPTS:
                        raise
                    print(f"Falha de conexão (tentativa {attempt}/{RETRY_ATTEMPTS}): {e}. Reagendando em {RETRY_BACKOFF_SECONDS}s...")
                    time.sleep(RETRY_BACKOFF_SECONDS)

            save_state(new_state)
            num_lote += 1
            total_enviados += len(lote)
            print(f"Lote {num_lote}: {len(lote)} registros enviados (total: {total_enviados})")

        print(f"Concluído. Total: {total_enviados} registros em {num_lote} lote(s).")
    except requests.RequestException as e:
        print(f"Erro ao enviar após {RETRY_ATTEMPTS} tentativas: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"Resposta: {e.response.text}")
        print("Execute novamente para retomar de onde parou.")
        return 1
    except Exception as e:
        if PYMSSQL_AVAILABLE and isinstance(e, (pymssql.OperationalError, pymssql.DatabaseError)):
            print_color(f"❌ Erro no banco: {e}", 31)
        else:
            print_color(f"❌ Erro inesperado: {e}", 31)
        return 1
    return 0


if __name__ == "__main__":
    exit(main())
