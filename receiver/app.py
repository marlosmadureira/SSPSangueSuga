#!/usr/bin/env python3
"""
API Receiver - Recebe lotes de dados e processa em fila.
Autenticação via JWT (Bearer).
"""
from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os
import config
from models import (
    LoteRequest,
    LoteResponse,
    FilaItemResponse,
    FilaStatsResponse,
    HealthResponse,
    ErrorResponse,
)
from repository import FilaRepository
from jwt_auth import verify_token
from database import init_db_pool, close_db_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia ciclo de vida da aplicação"""
    # Startup
    init_db_pool()
    yield
    # Shutdown
    close_db_pool()


app = FastAPI(
    title="API Receptor - Fila de Lotes",
    description="Recebe lotes de dados e processa em fila. Autenticação via JWT (Bearer).",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Middleware para adicionar headers de segurança
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# Função para obter FilaRepository (lazy loading)
def get_fila_repository() -> FilaRepository:
    """Retorna instância do FilaRepository"""
    return FilaRepository(config.FILA_PROCESSANDO_TIMEOUT_MINUTES)


# Rotas públicas (sem JWT)
@app.get("/api/health", response_model=HealthResponse, tags=["Público"])
async def health_check():
    """Health check"""
    return HealthResponse(status="ok")


@app.get("/openapi.yaml", tags=["Público"])
async def get_openapi_yaml():
    """Retorna arquivo OpenAPI/Swagger YAML"""
    from fastapi.responses import Response
    yaml_path = os.path.join(os.path.dirname(__file__), "openapi.yaml")
    if not os.path.exists(yaml_path):
        raise HTTPException(status_code=404, detail="Arquivo não encontrado")
    
    # Substituir {{BASE_URL}} pelo valor da configuração
    with open(yaml_path, "r", encoding="utf-8") as f:
        content = f.read()
        content = content.replace("{{BASE_URL}}", config.BASE_URL)
    
    return Response(
        content=content,
        media_type="application/x-yaml",
        headers={"Content-Disposition": "inline; filename=openapi.yaml"},
    )


# Rotas protegidas (requerem JWT)
@app.post(
    "/api/lotes",
    response_model=LoteResponse,
    status_code=status.HTTP_200_OK,
    tags=["Protegido"],
    summary="Recebe um lote de registros e enfileira (idempotente por checkpoint_key)",
    description="""
    Se checkpoint_key for enviado e já tiver sido recebido antes (retorno após queda),
    o lote não é duplicado e a resposta vem com duplicado=true.
    """,
)
async def receber_lote(
    lote: LoteRequest,
    jwt_payload: dict = Depends(verify_token),
    fila: FilaRepository = Depends(get_fila_repository),
):
    """Recebe um lote de registros e enfileira"""
    registros = lote.registros
    total = lote.total if lote.total is not None else len(registros)
    checkpoint_key = lote.checkpoint_key

    # Validação de entrada
    if not registros or not isinstance(registros, list):
        raise HTTPException(
            status_code=400, detail="Nenhum registro no lote"
        )

    # Limitar tamanho do lote
    if len(registros) > 10000:
        raise HTTPException(
            status_code=400, detail="Lote muito grande. Máximo 10000 registros"
        )

    try:
        lote_id = fila.enfileirar_lote(total, registros, checkpoint_key)
        duplicado = (lote_id == 0 and checkpoint_key is not None)
        return LoteResponse(
            ok=True,
            lote_id=None if duplicado else lote_id,
            itens=len(registros),
            duplicado=duplicado,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar lote: {str(e)}")


@app.get(
    "/api/fila/processar",
    response_model=FilaItemResponse,
    tags=["Protegido"],
    summary="Obtém o próximo item da fila para processar",
    description="""
    Itens que ficaram "processando" por mais que FILA_PROCESSANDO_TIMEOUT_MINUTES
    (ex. queda do worker) são recolocados como pendente e podem ser processados de novo.
    """,
)
async def obter_proximo_item(
    jwt_payload: dict = Depends(verify_token),
    fila: FilaRepository = Depends(get_fila_repository),
):
    """Obtém o próximo item da fila para processar"""
    try:
        item = fila.obter_proximo_item()
        if not item:
            return FilaItemResponse(
                item_id=None,
                lote_id=None,
                indice=None,
                payload=None,
                mensagem="Fila vazia",
            )
        return FilaItemResponse(
            item_id=item["id"],
            lote_id=item["lote_id"],
            indice=item["indice"],
            payload=item["payload"],
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar fila: {str(e)}")


@app.post(
    "/api/fila/{item_id}/concluir",
    tags=["Protegido"],
    summary="Marca item como processado",
)
async def marcar_item_processado(
    item_id: int,
    jwt_payload: dict = Depends(verify_token),
    fila: FilaRepository = Depends(get_fila_repository),
):
    """Marca item como processado"""
    if item_id <= 0:
        raise HTTPException(status_code=400, detail="ID inválido")
    
    try:
        fila.marcar_item_processado(item_id)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar: {str(e)}")


@app.post(
    "/api/fila/{item_id}/erro",
    tags=["Protegido"],
    summary="Marca item com erro",
)
async def marcar_item_erro(
    item_id: int,
    jwt_payload: dict = Depends(verify_token),
    fila: FilaRepository = Depends(get_fila_repository),
):
    """Marca item com erro"""
    if item_id <= 0:
        raise HTTPException(status_code=400, detail="ID inválido")
    
    try:
        fila.marcar_item_erro(item_id)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar: {str(e)}")


@app.get(
    "/api/fila/stats",
    response_model=FilaStatsResponse,
    tags=["Protegido"],
    summary="Estatísticas da fila (pendente, processado, erro)",
)
async def estatisticas_fila(
    jwt_payload: dict = Depends(verify_token),
    fila: FilaRepository = Depends(get_fila_repository),
):
    """Retorna estatísticas da fila"""
    try:
        stats = fila.estatisticas()
        return FilaStatsResponse(**stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao obter estatísticas: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
