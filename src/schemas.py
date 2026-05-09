from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from src.domain import PRECATORIO_FULL_PATTERN, StatusPrecatorio, TaskAction, TaskStatus


class PrecatorioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    numero: str
    credor: str | None
    documento_credor: str | None
    ente_devedor: str | None
    processo_originario: str | None
    natureza: str | None
    valor_centavos: int | None
    posicao_fila: int | None
    previsao_orcamentaria: int | None
    status: StatusPrecatorio
    status_motivo: str
    documento_hash: str
    created_at: datetime
    updated_at: datetime


class TimelineEventCreate(BaseModel):
    tipo: str = Field(min_length=3, max_length=64)
    titulo: str = Field(min_length=3, max_length=255)
    descricao: str = Field(min_length=3)
    data_evento: date | None = None
    precisao: str = Field(default="dia", min_length=3, max_length=16)


class TimelineEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    precatorio_numero: str
    tipo: str
    titulo: str
    descricao: str
    data_evento: date | None
    precisao: str
    origem: str
    created_at: datetime


class TaskCreate(BaseModel):
    precatorio_numero: str = Field(pattern=PRECATORIO_FULL_PATTERN)
    acao: TaskAction
    prioridade: int = Field(ge=1, le=5)
    motivo: str = Field(min_length=3)


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    precatorio_numero: str
    acao: TaskAction
    prioridade: int
    status: TaskStatus
    motivo: str
    created_at: datetime
    updated_at: datetime


class RpaCollectRequest(BaseModel):
    ente_devedor: str | None = Field(default="Estado do Parana", max_length=120)
    timeout_segundos: int = Field(default=180, ge=30, le=900)


class ColetaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    numero: str
    ordem: int
    origem: str
    collected_at: datetime


class RpaCollectResponse(BaseModel):
    total: int
    numeros: list[str]


class ProcessamentoResponse(BaseModel):
    precatorio: PrecatorioRead
    tarefa: TaskRead
    eventos_criados: int
