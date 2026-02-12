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

import pyodbc
import requests

from config import (
    API_BASE_URL,
    API_JWT_TOKEN,
    BATCH_SIZE,
    DB_DRIVER,
    DB_NAME,
    DB_ORDER_COLUMN,
    DB_PASSWORD,
    DB_SERVER,
    DB_TABLE,
    DB_USER,
    RETRY_ATTEMPTS,
    RETRY_BACKOFF_SECONDS,
    STATE_FILE,
)


def get_connection():
    conn_str = (
        f"DRIVER={{{DB_DRIVER}}};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={DB_NAME};"
        f"UID={DB_USER};"
        f"PWD={DB_PASSWORD};"
    )
    return pyodbc.connect(conn_str)


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


def iterar_lotes(state: dict) -> Iterator[Tuple[List[dict], dict, str]]:
    """
    Gera (lote, novo_estado, checkpoint_key).
    checkpoint_key identifica este lote para idempotência no receiver.
    """
    conn = get_connection()
    cursor = conn.cursor()

    if DB_ORDER_COLUMN:
        # Paginação por chave: retoma após last_order_value (mais estável que OFFSET)
        col = f"[{DB_ORDER_COLUMN}]"
        last_val = state.get("last_order_value")
        while True:
            if last_val is None:
                tsql = f"""
                SELECT * FROM [{DB_TABLE}]
                ORDER BY {col}
                OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY
                """
                cursor.execute(tsql, (BATCH_SIZE,))
            else:
                tsql = f"""
                SELECT * FROM [{DB_TABLE}]
                WHERE {col} > ?
                ORDER BY {col}
                OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY
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
            SELECT * FROM [{DB_TABLE}]
            ORDER BY {order_by}
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
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


def enviar_lote(lote: List[dict], checkpoint_key: str) -> bool:
    url = f"{API_BASE_URL}/lotes"
    headers = {
        "Authorization": f"Bearer {API_JWT_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "registros": lote,
        "total": len(lote),
        "checkpoint_key": checkpoint_key,
    }
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

    total_enviados = 0
    num_lote = 0

    try:
        for lote, new_state, checkpoint_key in iterar_lotes(state):
            for attempt in range(1, RETRY_ATTEMPTS + 1):
                try:
                    enviar_lote(lote, checkpoint_key)
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
    except pyodbc.Error as e:
        print(f"Erro no banco: {e}")
        return 1
    return 0


if __name__ == "__main__":
    exit(main())
