from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from src.database import init_db
from src.routers import fila, precatorios, rpa

OPENAPI_TAGS = [
    {
        "name": "precatorios",
        "description": (
            "Processa documentos locais de precatórios, consulta dados estruturados "
            "e registra eventos da linha do tempo."
        ),
    },
    {
        "name": "fila",
        "description": (
            "Gerencia tarefas futuras derivadas do status classificado de cada precatório."
        ),
    },
    {
        "name": "rpa",
        "description": (
            "Executa a coleta assistida da fila pública do TJPR e persiste somente os "
            "identificadores coletados na ordem original."
        ),
    },
    {
        "name": "health",
        "description": "Verificação simples de disponibilidade da API.",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Sistema de Precatórios TJPR",
    version="0.1.0",
    description=(
        "API para coleta assistida, processamento de documentos OCR, fila de tarefas "
        "e linha do tempo auditável de precatórios."
    ),
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
)

app.include_router(precatorios.router)
app.include_router(fila.router)
app.include_router(rpa.router)


@app.get("/", include_in_schema=False)
def redirecionar_para_docs() -> RedirectResponse:
    return RedirectResponse(url="/docs")


@app.get(
    "/health",
    tags=["health"],
    summary="Verificar disponibilidade",
    description="Retorna um status simples para confirmar que a API está de pé.",
)
def health() -> dict[str, str]:
    return {"status": "ok"}
