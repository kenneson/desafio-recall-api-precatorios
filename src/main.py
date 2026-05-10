from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from src.database import init_db
from src.routers import fila, precatorios, rpa

logger = logging.getLogger(__name__)

OPENAPI_TAGS = [
    {
        "name": "precatorios",
        "description": (
            "Processa documentos locais de precatorios, consulta dados estruturados "
            "e registra eventos da linha do tempo."
        ),
    },
    {
        "name": "fila",
        "description": "Gerencia tarefas futuras derivadas do status classificado de cada precatorio.",
    },
    {
        "name": "rpa",
        "description": (
            "Executa a coleta assistida da fila publica do TJPR e persiste somente "
            "os identificadores coletados da tabela na ordem original."
        ),
    },
    {
        "name": "health",
        "description": "Verificacao simples de disponibilidade da API.",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Sistema de Precatorios TJPR",
    version="0.1.0",
    description=(
        "API para coleta assistida, processamento de documentos OCR, fila de tarefas "
        "e linha do tempo auditavel de precatorios."
    ),
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
)

app.include_router(precatorios.router)
app.include_router(fila.router)
app.include_router(rpa.router)


@app.exception_handler(Exception)
async def tratar_erro_inesperado(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Erro inesperado ao processar requisicao em %s", request.url.path, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "type": "internal_error",
            "detail": "Erro interno inesperado.",
        },
    )


@app.get("/", include_in_schema=False)
def redirecionar_para_docs() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get(
    "/health",
    tags=["health"],
    summary="Verificar disponibilidade",
    description="Retorna um status simples para confirmar que a API esta de pe.",
)
def health() -> dict[str, str]:
    return {"status": "ok"}
