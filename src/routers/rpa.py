from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database import get_db
from src.models import ColetaPrecatorio
from src.rpa import coletar_precatorios_tjpr
from src.schemas import ColetaRead, RpaCollectRequest, RpaCollectResponse
from src.services import persist_collected_numbers

router = APIRouter(prefix="/rpa", tags=["rpa"])


@router.post("/coletar", response_model=RpaCollectResponse)
def coletar_precatorios(payload: RpaCollectRequest | None = None, db: Session = Depends(get_db)) -> RpaCollectResponse:
    payload = payload or RpaCollectRequest()
    try:
        numbers = coletar_precatorios_tjpr(payload.ente_devedor, payload.timeout_segundos)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    persist_collected_numbers(numbers, db)
    return RpaCollectResponse(total=len(numbers), numeros=numbers)


@router.get("/coletas", response_model=list[ColetaRead])
def listar_coletas(db: Session = Depends(get_db)) -> list[ColetaRead]:
    query = select(ColetaPrecatorio).order_by(ColetaPrecatorio.ordem, ColetaPrecatorio.id)
    return list(db.execute(query).scalars().all())

