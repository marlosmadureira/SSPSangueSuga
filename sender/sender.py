#!/usr/bin/env python3
"""
Envia dados de uma tabela SQL Server para a API de destino em lotes de 1000.
Retoma de onde parou após queda de energia ou conexão (checkpoint em arquivo).
Uso: python sender.py
"""
import json
import os
import re
import time as time_module
from datetime import date, datetime, time
from decimal import Decimal
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

# Importar módulo customizado de notificações (opcional)
try:
    from sendElement import sendMessageElement
    SEND_ELEMENT_AVAILABLE = True
except ImportError:
    SEND_ELEMENT_AVAILABLE = False
    def sendMessageElement(*args, **kwargs):
        pass  # Função vazia se não disponível


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
        sendMessageElement(config.ACCESSTOKEN, config.SALA, f"Erro 1 -> ❌ Erro operacional: {e}")
        print_color(f"❌ Erro operacional: {e}", 31)
        return None
    except pymssql.DatabaseError as e:
        sendMessageElement(config.ACCESSTOKEN, config.SALA, f"Erro 2 -> ❌ Erro de banco de dados: {e}")
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


def serializar_para_json(val: Any) -> Any:
    """
    Converte qualquer valor do SQL Server para tipo JSON-serializável.
    Suporta: date, datetime, time, Decimal, bytes, e tipos aninhados (list, dict).
    """
    if val is None:
        return None
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, time):
        return val.isoformat()
    if isinstance(val, Decimal):
        try:
            return int(val) if val % 1 == 0 else float(val)
        except (ValueError, TypeError):
            return str(val)
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8")
        except Exception:
            return val.hex()
    if isinstance(val, dict):
        return {k: serializar_para_json(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [serializar_para_json(v) for v in val]
    if hasattr(val, "isoformat"):
        return val.isoformat()
    if isinstance(val, (str, int, float, bool)):
        return val
    # UUID, outros objetos -> string
    return str(val)


def serializar_registros_para_json(registros: List[dict]) -> List[dict]:
    """Converte cada registro (dict) para valores 100% JSON-serializáveis."""
    return [{k: serializar_para_json(v) for k, v in reg.items()} for reg in registros]


def _state_key_tabela() -> str:
    """Chave única da tabela atual para o arquivo de estado (uma chave por tabela)."""
    return nome_tabela_postgres()


def _load_state_file() -> dict:
    """Carrega o arquivo de estado completo: { "schema.tabela": { ... }, ... }."""
    if not os.path.isfile(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        sendMessageElement(config.ACCESSTOKEN, config.SALA, f"Erro 3 -> ❌ Erro ")
        return {}


def load_state() -> dict:
    """Retorna o estado apenas da tabela atual (vazio se nunca rodou essa tabela)."""
    all_states = _load_state_file()
    return all_states.get(_state_key_tabela(), {})


def save_state(state: dict, total_enviados: Optional[int] = None) -> None:
    """Salva o estado da tabela atual no arquivo único; mantém estado das outras tabelas."""
    key = _state_key_tabela()
    all_states = _load_state_file()
    entry = dict(state)
    if total_enviados is not None:
        entry["total_enviados"] = total_enviados
    all_states[key] = entry

    path = STATE_FILE
    tmp = f"{path}.tmp.{os.getpid()}"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(all_states, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(1, 4):
            try:
                os.replace(tmp, path)
                return
            except OSError as e:
                if attempt == 3 or getattr(e, "winerror", None) != 5:
                    raise
                time_module.sleep(0.15 * attempt)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


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
    """
    Nome qualificado para o PostgreSQL: schema.tabela (mesmo do SQL Server, sanitizado).
    Ex.: SchCADSUS.TIPEND -> SchCADSUS.TIPEND (receiver criará schema SchCADSUS e tabela TIPEND).
    """
    s = DB_TABLE.replace("[", "").replace("]", "").strip()
    if not s:
        return "public.tabela"
    # Manter schema.tabela; só normalizar espaços e caracteres problemáticos por parte
    parts = s.split(".", 1)
    safe = lambda x: re.sub(r"[^\w]", "_", x.strip()) if x else ""
    if len(parts) == 2:
        schema, tabela = safe(parts[0]) or "public", safe(parts[1]) or "tabela"
        return f"{schema}.{tabela}"
    return safe(parts[0]) or "tabela"


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
        sendMessageElement(config.ACCESSTOKEN, config.SALA, f"Erro 4 -> Nenhuma coluna encontrada para a tabela {DB_TABLE}")
        raise Exception(f"Nenhuma coluna encontrada para a tabela {DB_TABLE}")
    # URL do receiver: ex. http://host:8080/api -> http://host:8080/api/tabela/definir
    base = API_BASE_URL.rstrip("/")
    url = f"{base}/tabela/definir"
    headers = {
        "Authorization": f"Bearer {API_JWT_TOKEN.strip()}",
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
        "Authorization": f"Bearer {API_JWT_TOKEN.strip()}",
        "Content-Type": "application/json",
    }
    # Serializar registros para JSON (date, datetime, Decimal, bytes, etc.)
    registros_json = serializar_registros_para_json(lote)
    payload = {
        "registros": registros_json,
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
    tabela_key = _state_key_tabela()
    if state:
        total_antes = state.get("total_enviados")
        msg = f"Retomando tabela '{tabela_key}' de onde parou."
        if total_antes is not None:
            msg += f" ({total_antes} registros enviados anteriormente.)"
        print(msg)

    # Nome da tabela no PostgreSQL (para criar/inserir no receiver)
    nome_tabela_pg = nome_tabela_postgres()

    # Antes do primeiro lote: garantir que a tabela existe no receiver (enviar definição).
    # Se já existir no PostgreSQL, o receiver não recria e só insere.
    try:
        enviar_definicao_tabela()
        print(f"Estrutura da tabela '{nome_tabela_pg}' enviada ao receiver (criada se não existir).")
    except requests.RequestException as e:
        sendMessageElement(config.ACCESSTOKEN, config.SALA, f"Erro 5 -> Aviso: não foi possível definir tabela no receiver: {e}")
        print(f"Aviso: não foi possível definir tabela no receiver: {e}")
        print("Enviando lotes com nome_tabela mesmo assim (receiver insere se a tabela já existir).")
    except Exception as e:
        sendMessageElement(config.ACCESSTOKEN, config.SALA, f"Erro 6 -> Aviso: erro ao obter/enviar schema: {e}")
        print(f"Aviso: erro ao obter/enviar schema: {e}")
        # Mantém nome_tabela_pg para tentar inserir; se a tabela não existir, o receiver retornará erro.

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
                    time_module.sleep(RETRY_BACKOFF_SECONDS)

            num_lote += 1
            total_enviados += len(lote)
            save_state(new_state, total_enviados=total_enviados)
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
            sendMessageElement(config.ACCESSTOKEN, config.SALA, f"Erro 7 -> ❌ Erro no banco: {e}")
            print_color(f"❌ Erro no banco: {e}", 31)
        else:
            sendMessageElement(config.ACCESSTOKEN, config.SALA, f"Erro 8 -> ❌ Erro inesperado: {e}")
            print_color(f"❌ Erro inesperado: {e}", 31)
        return 1
    return 0


if __name__ == "__main__":
    exit(main())
