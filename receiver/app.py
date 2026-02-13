#!/usr/bin/env python3
"""
API Receiver - Recebe lotes de dados e processa em fila.
Autenticação via JWT (Bearer).
"""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os
import config

# Importar módulo customizado de notificações (opcional)
try:
    from sendElement import sendMessageElement
    SEND_ELEMENT_AVAILABLE = True
except ImportError:
    SEND_ELEMENT_AVAILABLE = False
    def sendMessageElement(*args, **kwargs):
        pass  # Função vazia se não disponível
from models import (
    LoteRequest,
    LoteResponse,
    FilaItemResponse,
    FilaStatsResponse,
    HealthResponse,
    ErrorResponse,
    TabelaDefinirRequest,
    TabelaDefinirResponse,
)
from repository import FilaRepository
from tabela_service import criar_tabela_se_nao_existe, inserir_registros_em_tabela, tabela_existe
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
    "/api/tabela/definir",
    response_model=TabelaDefinirResponse,
    status_code=status.HTTP_200_OK,
    tags=["Protegido"],
    summary="Cria tabela no PostgreSQL a partir do schema do SQL Server (se não existir)",
)
async def definir_tabela(
    body: TabelaDefinirRequest,
    jwt_payload: dict = Depends(verify_token),
):
    """
    Cria a tabela no PostgreSQL com a estrutura enviada.
    Se a tabela já existir, não altera e retorna criada=false.
    O sender deve chamar este endpoint antes de enviar os lotes (ou na primeira execução).
    """
    try:
        colunas_dict = [
            {
                "nome": c.nome,
                "tipo_sqlserver": c.tipo_sqlserver,
                "max_length": c.max_length,
                "numeric_precision": c.numeric_precision,
                "numeric_scale": c.numeric_scale,
                "is_nullable": c.is_nullable if c.is_nullable is not None else True,
            }
            for c in body.colunas
        ]
        criada = criar_tabela_se_nao_existe(body.nome_tabela, colunas_dict)
        return TabelaDefinirResponse(
            ok=True,
            mensagem="Tabela criada com sucesso." if criada else "Tabela já existia. Nenhuma alteração.",
            criada=criada,
        )
    except ValueError as e:
        if SEND_ELEMENT_AVAILABLE:
            sendMessageElement(config.ACCESSTOKEN, config.SALA, f"Erro 1 -> {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if SEND_ELEMENT_AVAILABLE:
            sendMessageElement(config.ACCESSTOKEN, config.SALA, f"Erro 2 -> {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao criar tabela: {str(e)}")


@app.post(
    "/api/lotes",
    response_model=LoteResponse,
    status_code=status.HTTP_200_OK,
    tags=["Protegido"],
    summary="Recebe um lote de registros e enfileira ou insere em tabela (idempotente por checkpoint_key)",
    description="""
    Se checkpoint_key for enviado e já tiver sido recebido antes (retorno após queda),
    o lote não é duplicado e a resposta vem com duplicado=true.
    Se nome_tabela for enviado, os registros são inseridos na tabela no PostgreSQL (que deve ter sido criada via POST /api/tabela/definir). Se a tabela já existir, não recria e apenas insere.
    """,
)
async def receber_lote(
    lote: LoteRequest,
    jwt_payload: dict = Depends(verify_token),
    fila: FilaRepository = Depends(get_fila_repository),
):
    """Recebe um lote de registros; se nome_tabela for informado, insere na tabela; senão enfileira."""
    registros = lote.registros
    total = lote.total if lote.total is not None else len(registros)
    checkpoint_key = lote.checkpoint_key
    nome_tabela = lote.nome_tabela

    # Validação de entrada
    if not registros or not isinstance(registros, list):
        if SEND_ELEMENT_AVAILABLE:
            sendMessageElement(config.ACCESSTOKEN, config.SALA, f"Erro 3 -> Nenhum registro no lote")
        raise HTTPException(
            status_code=400, detail="Nenhum registro no lote"
        )

    # Limitar tamanho do lote
    batch_size = getattr(config, 'BATCH_SIZE', 10000)  # Padrão 10000 se não configurado
    if len(registros) > batch_size:
        if SEND_ELEMENT_AVAILABLE:
            sendMessageElement(config.ACCESSTOKEN, config.SALA, f"Erro 4 -> Lote muito grande. Máximo {batch_size} registros")
        raise HTTPException(
            status_code=400, detail=f"Lote muito grande. Máximo {batch_size} registros"
        )

    # Modo: inserir em tabela no PostgreSQL
    if nome_tabela and nome_tabela.strip():
        if not tabela_existe(nome_tabela.strip()):
            if SEND_ELEMENT_AVAILABLE:
                sendMessageElement(config.ACCESSTOKEN, config.SALA, f"Erro 5 -> Tabela {nome_tabela} não existe. Chame primeiro POST /api/tabela/definir com a estrutura da tabela.")
            raise HTTPException(
                status_code=400,
                detail=f"Tabela '{nome_tabela}' não existe. Chame primeiro POST /api/tabela/definir com a estrutura da tabela.",
            )
        try:
            inseridos = inserir_registros_em_tabela(nome_tabela.strip(), registros)
            return LoteResponse(
                ok=True,
                lote_id=None,
                itens=inseridos,
                duplicado=False,
            )
        except Exception as e:
            if SEND_ELEMENT_AVAILABLE:
                sendMessageElement(config.ACCESSTOKEN, config.SALA, f"Erro 6 -> Erro ao inserir na tabela (POST /api/lotes): {str(e)}")
            logging.exception("Erro ao inserir na tabela (POST /api/lotes)")
            raise HTTPException(status_code=500, detail=f"Erro ao inserir na tabela: {str(e)}")

    # Modo original: enfileirar na fila
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
        if SEND_ELEMENT_AVAILABLE:
            sendMessageElement(config.ACCESSTOKEN, config.SALA, f"Erro 7 -> Erro ao processar lote: {str(e)}")
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
        if SEND_ELEMENT_AVAILABLE:
            sendMessageElement(config.ACCESSTOKEN, config.SALA, f"Erro 8 -> Erro ao processar fila: {str(e)}")
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
        if SEND_ELEMENT_AVAILABLE:
            sendMessageElement(config.ACCESSTOKEN, config.SALA, f"Erro 9 -> Erro ao marcar item como processado: {str(e)}")
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
        if SEND_ELEMENT_AVAILABLE:
            sendMessageElement(config.ACCESSTOKEN, config.SALA, f"Erro 10 -> ID inválido")
        raise HTTPException(status_code=400, detail="ID inválido")
    
    try:
        fila.marcar_item_erro(item_id)
        return {"ok": True}
    except Exception as e:
        if SEND_ELEMENT_AVAILABLE:
            sendMessageElement(config.ACCESSTOKEN, config.SALA, f"Erro 11 -> Erro ao marcar item com erro: {str(e)}")
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
        if SEND_ELEMENT_AVAILABLE:
            sendMessageElement(config.ACCESSTOKEN, config.SALA, f"Erro 12 -> Erro ao obter estatísticas: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao obter estatísticas: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
