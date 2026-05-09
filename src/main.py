from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.database import init_db
from src.routers import fila, precatorios, rpa


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Sistema de Precatorios TJPR",
    version="0.1.0",
    description="API para coleta assistida, processamento de documentos, fila e linha do tempo auditavel.",
    lifespan=lifespan,
)

app.include_router(precatorios.router)
app.include_router(fila.router)
app.include_router(rpa.router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}

