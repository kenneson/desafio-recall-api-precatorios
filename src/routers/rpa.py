from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database import get_db
from src.domain import OFICIO_PRECATORIO_PATTERN
from src.models import ColetaPrecatorio
from src.rpa import RpaNoCollectableNumbers, coletar_precatorios_tjpr
from src.schemas import ColetaRead, RpaCollectRequest, RpaCollectResponse
from src.services import persist_collected_numbers

router = APIRouter(prefix="/rpa", tags=["rpa"])


@router.post(
    "/coletar",
    response_model=RpaCollectResponse,
    summary="Coletar fila publica do TJPR",
    description=(
        "Abre o portal de precatorios do TJPR com Playwright, seleciona o orgao "
        "devedor quando possivel e aguarda a intervencao manual exigida pelo captcha. "
        "Apos a pesquisa, extrai numeros da tabela de resultados preservando a ordem "
        "cronologica. O CNJ completo de Autos do Precatorio tem preferencia; quando "
        "ele vier mascarado, a coleta usa o Oficio Precatorio disponivel."
    ),
    responses={
        422: {
            "description": "Tabela carregada, mas sem identificador de precatorio nas colunas esperadas.",
        },
        503: {
            "description": "Falha operacional no Playwright, dependencia ausente ou tempo esgotado na coleta.",
        },
    },
)
def coletar_precatorios(payload: RpaCollectRequest | None = None, db: Session = Depends(get_db)) -> RpaCollectResponse:
    payload = payload or RpaCollectRequest()
    try:
        numbers = coletar_precatorios_tjpr(payload.ente_devedor, payload.timeout_segundos)
    except RpaNoCollectableNumbers as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    persist_collected_numbers(numbers, db, ente_devedor=payload.ente_devedor)
    return RpaCollectResponse(total=len(numbers), numeros=numbers, avisos=_build_collection_warnings(numbers))


@router.get(
    "/coletas",
    response_model=list[ColetaRead],
    summary="Consultar coletas realizadas",
    description=(
        "Retorna os numeros persistidos pela etapa de RPA, na ordem em que foram "
        "encontrados na listagem publica do TJPR."
    ),
)
def listar_coletas(db: Session = Depends(get_db)) -> list[ColetaRead]:
    query = select(ColetaPrecatorio).order_by(ColetaPrecatorio.ordem, ColetaPrecatorio.id)
    return list(db.execute(query).scalars().all())


def _build_collection_warnings(numbers: list[str]) -> list[str]:
    if any(re.fullmatch(OFICIO_PRECATORIO_PATTERN, number) for number in numbers):
        return [
            "CNJ completo nao estava disponivel na tabela publica; coleta persistida com Oficio Precatorio.",
            "Para processar documentos locais, use o numero CNJ do arquivo em /documentos.",
        ]
    return []
