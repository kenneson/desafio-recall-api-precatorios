from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from src.database import BASE_DIR
from src.document_extraction import ExtractionResult, extract_document_text
from src.document_parser import ParsedDocument, ParsedEvent
from src.domain import (
    COLETA_PRECATORIO_FULL_PATTERN,
    PRECATORIO_PATTERN,
    StatusPrecatorio,
    TaskAction,
    TaskStatus,
    task_rule_for_status,
)
from src.models import ColetaPrecatorio, FilaTask, Precatorio, TimelineEvent

DOCUMENTS_DIR = BASE_DIR / "documentos"
RPA_SOURCE_URL = "https://www.tjpr.jus.br/precatorios-em-ordem-cronologica-de-pagamento"
PRECATORIO_RE = re.compile(rf"^{PRECATORIO_PATTERN}$")
COLETA_PRECATORIO_RE = re.compile(COLETA_PRECATORIO_FULL_PATTERN)


class DomainError(Exception):
    pass


class InvalidPrecatorioNumber(DomainError):
    pass


class DocumentNotFound(DomainError):
    pass


class PrecatorioNotFound(DomainError):
    pass


@dataclass(frozen=True)
class ProcessamentoResult:
    precatorio: Precatorio
    tarefa: FilaTask
    eventos_criados: int


def validate_precatorio_numero(numero: str) -> str:
    if not PRECATORIO_RE.fullmatch(numero):
        raise InvalidPrecatorioNumber("Numero de precatorio invalido.")
    return numero


def validate_coleta_precatorio_numero(numero: str) -> str:
    if not COLETA_PRECATORIO_RE.fullmatch(numero):
        raise InvalidPrecatorioNumber("Numero coletado de precatorio invalido.")
    return numero


def process_precatorio(numero: str, db: Session) -> ProcessamentoResult:
    numero = validate_precatorio_numero(numero)
    document_path = resolve_document_path(numero)
    extraction = extract_document_text(document_path.read_text(encoding="utf-8"), fallback_numero=numero)
    parsed = extraction.document
    if parsed.numero != numero:
        raise InvalidPrecatorioNumber("Documento localizado pertence a outro precatorio.")

    precatorio = upsert_precatorio(parsed, db, extraction)
    tarefa = enqueue_task_for_status(numero, parsed.status, db)
    eventos_criados = create_timeline_events(numero, parsed.eventos, "documento", db)
    eventos_criados += create_timeline_events(
        numero,
        [
            ParsedEvent(
                tipo="PROCESSAMENTO_SISTEMA",
                titulo="Documento processado pela API",
                descricao="Documento OCR estruturado, status classificado e tarefa enfileirada.",
                data_evento=date.today(),
                precisao="dia",
            )
        ],
        "sistema",
        db,
        dedupe=False,
    )
    db.commit()
    db.refresh(precatorio)
    db.refresh(tarefa)
    return ProcessamentoResult(precatorio=precatorio, tarefa=tarefa, eventos_criados=eventos_criados)


def resolve_document_path(numero: str) -> Path:
    numero = validate_precatorio_numero(numero)
    documents_root = DOCUMENTS_DIR.resolve()
    path = (DOCUMENTS_DIR / f"{numero}.txt").resolve()
    # Evita path traversal mesmo se a validacao da rota mudar no futuro.
    if path.parent != documents_root:
        raise InvalidPrecatorioNumber("Caminho de documento invalido.")
    if not path.exists():
        raise DocumentNotFound("Documento do precatorio nao encontrado.")
    return path


def upsert_precatorio(parsed: ParsedDocument, db: Session, extraction: ExtractionResult | None = None) -> Precatorio:
    precatorio = db.execute(select(Precatorio).where(Precatorio.numero == parsed.numero)).scalar_one_or_none()
    if not precatorio:
        precatorio = Precatorio(numero=parsed.numero, status=parsed.status.value, status_motivo=parsed.status_motivo, documento_hash=parsed.documento_hash)
        db.add(precatorio)

    precatorio.credor = parsed.credor
    precatorio.documento_credor = parsed.documento_credor
    precatorio.ente_devedor = parsed.ente_devedor
    precatorio.processo_originario = parsed.processo_originario
    precatorio.natureza = parsed.natureza
    precatorio.valor_centavos = parsed.valor_centavos
    precatorio.posicao_fila = parsed.posicao_fila
    precatorio.previsao_orcamentaria = parsed.previsao_orcamentaria
    precatorio.status = parsed.status.value
    precatorio.status_motivo = parsed.status_motivo
    precatorio.documento_hash = parsed.documento_hash
    if extraction:
        precatorio.extraction_method = extraction.method
        precatorio.extraction_confidence = extraction.confidence
        precatorio.extraction_warnings = extraction.warnings
        precatorio.llm_recommended = extraction.llm_recommended
    db.flush()
    return precatorio


def enqueue_task_for_status(numero: str, status: StatusPrecatorio, db: Session) -> FilaTask:
    action, priority, reason = task_rule_for_status(status)
    existing = db.execute(
        select(FilaTask).where(
            FilaTask.precatorio_numero == numero,
            FilaTask.acao == action.value,
            FilaTask.status == TaskStatus.PENDENTE.value,
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    task = FilaTask(
        precatorio_numero=numero,
        acao=action.value,
        prioridade=priority,
        status=TaskStatus.PENDENTE.value,
        motivo=reason,
    )
    db.add(task)
    db.flush()
    return task


def create_manual_task(precatorio_numero: str, acao: TaskAction, prioridade: int, motivo: str, db: Session) -> FilaTask:
    task = FilaTask(
        precatorio_numero=validate_precatorio_numero(precatorio_numero),
        acao=acao.value,
        prioridade=prioridade,
        status=TaskStatus.PENDENTE.value,
        motivo=motivo,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def create_timeline_events(
    numero: str,
    events: list[ParsedEvent],
    origem: str,
    db: Session,
    *,
    dedupe: bool = True,
) -> int:
    created = 0
    for event in events:
        if dedupe and _timeline_event_exists(numero, event, origem, db):
            continue
        db.add(
            TimelineEvent(
                precatorio_numero=numero,
                tipo=event.tipo,
                titulo=event.titulo,
                descricao=event.descricao,
                data_evento=event.data_evento,
                precisao=event.precisao,
                origem=origem,
            )
        )
        created += 1
    db.flush()
    return created


def create_manual_timeline_event(numero: str, event: ParsedEvent, db: Session) -> TimelineEvent:
    numero = validate_precatorio_numero(numero)
    timeline_event = TimelineEvent(
        precatorio_numero=numero,
        tipo=event.tipo,
        titulo=event.titulo,
        descricao=event.descricao,
        data_evento=event.data_evento,
        precisao=event.precisao,
        origem="api",
    )
    db.add(timeline_event)
    db.commit()
    db.refresh(timeline_event)
    return timeline_event


def get_precatorio_or_404(numero: str, db: Session) -> Precatorio:
    numero = validate_precatorio_numero(numero)
    precatorio = db.execute(select(Precatorio).where(Precatorio.numero == numero)).scalar_one_or_none()
    if not precatorio:
        raise PrecatorioNotFound("Precatorio nao encontrado.")
    return precatorio


def timeline_query(numero: str) -> Select[tuple[TimelineEvent]]:
    validate_precatorio_numero(numero)
    return (
        select(TimelineEvent)
        .where(TimelineEvent.precatorio_numero == numero)
        .order_by(TimelineEvent.data_evento.is_(None), TimelineEvent.data_evento, TimelineEvent.created_at, TimelineEvent.id)
    )


def queue_query(status: TaskStatus | None = TaskStatus.PENDENTE) -> Select[tuple[FilaTask]]:
    query = select(FilaTask)
    if status:
        query = query.where(FilaTask.status == status.value)
    return query.order_by(FilaTask.prioridade, FilaTask.created_at, FilaTask.id)


def persist_collected_numbers(numbers: list[str], db: Session, source: str = RPA_SOURCE_URL) -> list[ColetaPrecatorio]:
    rows: list[ColetaPrecatorio] = []
    for index, numero in enumerate(numbers, start=1):
        validate_coleta_precatorio_numero(numero)
        row = db.execute(select(ColetaPrecatorio).where(ColetaPrecatorio.numero == numero)).scalar_one_or_none()
        if not row:
            row = ColetaPrecatorio(numero=numero, ordem=index, origem=source)
            db.add(row)
        row.ordem = index
        row.origem = source
        rows.append(row)
    db.commit()
    for row in rows:
        db.refresh(row)
    return rows


def _timeline_event_exists(numero: str, event: ParsedEvent, origem: str, db: Session) -> bool:
    query = select(TimelineEvent).where(
        TimelineEvent.precatorio_numero == numero,
        TimelineEvent.tipo == event.tipo,
        TimelineEvent.titulo == event.titulo,
        TimelineEvent.descricao == event.descricao,
        TimelineEvent.origem == origem,
    )
    if event.data_evento is None:
        query = query.where(TimelineEvent.data_evento.is_(None))
    else:
        query = query.where(TimelineEvent.data_evento == event.data_evento)
    return db.execute(query).first() is not None
