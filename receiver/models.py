from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class TabelaColunaSchema(BaseModel):
    """Definição de uma coluna (schema SQL Server enviado pelo sender)."""
    nome: str
    tipo_sqlserver: str  # int, varchar, datetime, etc.
    max_length: Optional[int] = None
    numeric_precision: Optional[int] = None
    numeric_scale: Optional[int] = None
    is_nullable: Optional[bool] = True


class TabelaDefinirRequest(BaseModel):
    """Request para criar tabela no PostgreSQL a partir do schema do SQL Server."""
    nome_tabela: str
    colunas: List[TabelaColunaSchema]


class TabelaDefinirResponse(BaseModel):
    ok: bool
    mensagem: str
    criada: bool  # True se a tabela foi criada agora, False se já existia


class LoteRequest(BaseModel):
    registros: List[Dict[str, Any]]
    total: Optional[int] = None
    checkpoint_key: Optional[str] = None
    nome_tabela: Optional[str] = None  # Se informado, insere os registros nesta tabela no PostgreSQL


class LoteResponse(BaseModel):
    ok: bool
    lote_id: Optional[int] = None
    itens: int
    duplicado: bool


class FilaItemResponse(BaseModel):
    item_id: Optional[int] = None
    lote_id: Optional[int] = None
    indice: Optional[int] = None
    payload: Optional[Dict[str, Any]] = None
    mensagem: Optional[str] = None


class FilaStatsResponse(BaseModel):
    pendente: int
    processando: int
    processado: int
    erro: int
    total: int


class HealthResponse(BaseModel):
    status: str


class ErrorResponse(BaseModel):
    erro: str
    mensagem: Optional[str] = None
