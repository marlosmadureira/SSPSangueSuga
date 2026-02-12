"""
Serviço para criar tabelas no PostgreSQL a partir do schema do SQL Server
e inserir registros. Se a tabela já existir, não recria e apenas insere.
"""
import json
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from database import get_db_connection


# Mapeamento SQL Server -> PostgreSQL (tipo e tamanho quando aplicável)
def _sqlserver_tipo_para_postgres(tipo: str, max_length: Optional[int], numeric_precision: Optional[int], numeric_scale: Optional[int]) -> str:
    tipo = (tipo or "").lower().strip()
    if tipo in ("int", "integer"):
        return "INTEGER"
    if tipo == "bigint":
        return "BIGINT"
    if tipo in ("smallint", "tinyint"):
        return "SMALLINT"
    if tipo == "bit":
        return "BOOLEAN"
    if tipo in ("varchar", "nvarchar", "char", "nchar"):
        if max_length and max_length > 0 and max_length < 10485760:
            return f"VARCHAR({max_length})"
        return "TEXT"
    if tipo in ("text", "ntext"):
        return "TEXT"
    if tipo in ("datetime", "datetime2", "smalldatetime"):
        return "TIMESTAMP"
    if tipo == "date":
        return "DATE"
    if tipo == "time":
        return "TIME"
    if tipo in ("decimal", "numeric"):
        p = numeric_precision or 18
        s = numeric_scale if numeric_scale is not None else 0
        return f"NUMERIC({p},{s})"
    if tipo == "float":
        return "DOUBLE PRECISION"
    if tipo == "real":
        return "REAL"
    if tipo == "money":
        return "NUMERIC(19,4)"
    if tipo == "smallmoney":
        return "NUMERIC(10,4)"
    if tipo == "uniqueidentifier":
        return "UUID"
    if tipo in ("varbinary", "binary", "image"):
        return "BYTEA"
    # default
    return "TEXT"


def _identificador_seguro(nome: str) -> str:
    """Retorna identificador seguro para SQL (apenas letras, números, underscore)."""
    if not nome:
        return "col"
    # Remove caracteres inválidos; substitui por underscore
    s = re.sub(r"[^\w]", "_", nome.strip())
    return s if s else "col"


def _parse_schema_tabela(nome_tabela: str) -> tuple:
    """
    Interpreta nome_tabela como 'schema.tabela' ou 'tabela'.
    Retorna (schema, tabela) com identificadores seguros.
    """
    s = (nome_tabela or "").strip().replace("[", "").replace("]", "")
    if not s:
        return ("public", "tabela")
    parts = s.split(".", 1)
    if len(parts) == 2:
        schema = _identificador_seguro(parts[0].strip()) or "public"
        tabela = _identificador_seguro(parts[1].strip())
    else:
        schema = "public"
        tabela = _identificador_seguro(parts[0].strip())
    if not tabela:
        tabela = "tabela"
    return (schema, tabela)


def _schema_tabela_qualificado(nome_tabela: str) -> str:
    """Retorna string qualificada para SQL: "schema"."tabela"."""
    schema, tabela = _parse_schema_tabela(nome_tabela)
    return f'"{schema}"."{tabela}"'


def criar_tabela_se_nao_existe(nome_tabela: str, colunas: List[Dict[str, Any]]) -> bool:
    """
    Cria o schema (se não existir) e a tabela no PostgreSQL (se não existir).
    nome_tabela pode ser "schema.tabela" ou "tabela" (usa public).
    colunas: lista de dicts com nome, tipo_sqlserver, max_length, numeric_precision, numeric_scale, is_nullable.
    Retorna True se a tabela foi criada, False se já existia.
    """
    schema, tabela = _parse_schema_tabela(nome_tabela)
    if not tabela:
        raise ValueError("nome_tabela inválido")

    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Verificar se tabela já existe nesse schema
        cursor.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s
        """, (schema, tabela))
        if cursor.fetchone():
            return False  # já existe

        # Criar schema se não existir (exceto public que já existe)
        if schema != "public":
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')

        partes = []
        for c in colunas:
            nome_col = _identificador_seguro(c.get("nome", "col"))
            tipo_sql = (c.get("tipo_sqlserver") or "varchar").strip().lower()
            max_len = c.get("max_length")
            prec = c.get("numeric_precision")
            scale = c.get("numeric_scale")
            nullable = c.get("is_nullable", True)
            tipo_pg = _sqlserver_tipo_para_postgres(tipo_sql, max_len, prec, scale)
            null_str = "" if nullable else " NOT NULL"
            partes.append(f'"{nome_col}" {tipo_pg}{null_str}')
        colunas_sql = ", ".join(partes)
        qualificado = _schema_tabela_qualificado(nome_tabela)
        sql = f'CREATE TABLE IF NOT EXISTS {qualificado} ({colunas_sql})'
        cursor.execute(sql)
        conn.commit()
        return True


def tabela_existe(nome_tabela: str) -> bool:
    """Verifica se a tabela existe no schema indicado (ou public)."""
    schema, tabela = _parse_schema_tabela(nome_tabela)
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s
        """, (schema, tabela))
        return cursor.fetchone() is not None


def _serializar_valor(val: Any) -> Any:
    """Serializa valor para inserção no PostgreSQL (datetime -> string, etc.)."""
    if val is None:
        return None
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if hasattr(val, "isoformat"):
        return val.isoformat()
    if isinstance(val, (dict, list)):
        return json.dumps(val)
    return val


def inserir_registros_em_tabela(nome_tabela: str, registros: List[Dict[str, Any]]) -> int:
    """
    Insere os registros na tabela. A tabela deve já existir.
    nome_tabela pode ser "schema.tabela" ou "tabela".
    Retorna a quantidade de linhas inseridas.
    """
    qualificado = _schema_tabela_qualificado(nome_tabela)
    if not registros:
        return 0

    # Usar as chaves do primeiro registro como colunas (todas devem ter a mesma estrutura)
    colunas = list(registros[0].keys())
    colunas_safe = [f'"{_identificador_seguro(c)}"' for c in colunas]
    placeholders = ", ".join(["%s"] * len(colunas))
    colunas_str = ", ".join(colunas_safe)
    sql = f'INSERT INTO {qualificado} ({colunas_str}) VALUES ({placeholders})'

    with get_db_connection() as conn:
        cursor = conn.cursor()
        inseridos = 0
        for reg in registros:
            valores = [_serializar_valor(reg.get(c)) for c in colunas]
            try:
                cursor.execute(sql, valores)
                inseridos += 1
            except Exception as e:
                conn.rollback()
                raise RuntimeError(f"Erro ao inserir na tabela {qualificado}: {e}") from e
        conn.commit()
        return inseridos
