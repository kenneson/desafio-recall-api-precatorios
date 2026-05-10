from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from src.database import get_db
from src.document_parser import ParsedEvent
from src.domain import PRECATORIO_FULL_PATTERN
from src.schemas import ProcessamentoResponse, PrecatorioRead, TimelineEventCreate, TimelineEventRead
from src.services import (
    DocumentNotFound,
    InvalidPrecatorioNumber,
    PrecatorioNotFound,
    create_manual_timeline_event,
    get_precatorio_or_404,
    process_precatorio,
    timeline_query,
)

router = APIRouter(prefix="/precatorios", tags=["precatorios"])


@router.post(
    "/{numero}/processar",
    response_model=ProcessamentoResponse,
    status_code=201,
    summary="Processar documento do precatorio",
    description=(
        "Localiza o arquivo texto correspondente ao numero informado em /documentos, "
        "extrai os campos estruturados, classifica o status, salva o precatorio, "
        "cria a tarefa de fila coerente com a taxonomia e registra eventos na linha "
        "do tempo."
    ),
)
def processar_precatorio(numero: str = Path(pattern=PRECATORIO_FULL_PATTERN), db: Session = Depends(get_db)) -> ProcessamentoResponse:
    try:
        result = process_precatorio(numero, db)
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidPrecatorioNumber as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ProcessamentoResponse(precatorio=result.precatorio, tarefa=result.tarefa, eventos_criados=result.eventos_criados)


@router.get(
    "/{numero}",
    response_model=PrecatorioRead,
    summary="Consultar precatorio processado",
    description=(
        "Retorna os dados estruturados ja persistidos para um precatorio. "
        "Use este endpoint apos o processamento do documento correspondente."
    ),
)
def obter_precatorio(numero: str = Path(pattern=PRECATORIO_FULL_PATTERN), db: Session = Depends(get_db)) -> PrecatorioRead:
    try:
        return get_precatorio_or_404(numero, db)
    except PrecatorioNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/{numero}/timeline",
    response_model=list[TimelineEventRead],
    summary="Consultar linha do tempo",
    description=(
        "Lista, em ordem cronologica, os eventos extraidos do documento e os eventos "
        "registrados posteriormente pela API."
    ),
)
def listar_timeline(numero: str = Path(pattern=PRECATORIO_FULL_PATTERN), db: Session = Depends(get_db)) -> list[TimelineEventRead]:
    return list(db.execute(timeline_query(numero)).scalars().all())


@router.post(
    "/{numero}/eventos",
    response_model=TimelineEventRead,
    status_code=201,
    summary="Registrar evento manual",
    description=(
        "Adiciona um evento informado pela API a linha do tempo do precatorio. "
        "Serve para registrar atualizacoes posteriores ao documento original, como "
        "contato com cartorio, nova certidao ou revisao operacional."
    ),
)
def criar_evento_timeline(
    payload: TimelineEventCreate,
    numero: str = Path(pattern=PRECATORIO_FULL_PATTERN),
    db: Session = Depends(get_db),
) -> TimelineEventRead:
    event = ParsedEvent(
        tipo=payload.tipo,
        titulo=payload.titulo,
        descricao=payload.descricao,
        data_evento=payload.data_evento,
        precisao=payload.precisao,
    )
    try:
        return create_manual_timeline_event(numero, event, db)
    except InvalidPrecatorioNumber as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
