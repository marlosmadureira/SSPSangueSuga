from typing import List, Optional, Dict, Any
from pydantic import BaseModel


class LoteRequest(BaseModel):
    registros: List[Dict[str, Any]]
    total: Optional[int] = None
    checkpoint_key: Optional[str] = None


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
