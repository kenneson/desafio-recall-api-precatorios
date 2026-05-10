from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from src.domain import PRECATORIO_EXAMPLE, PRECATORIO_FORMAT_DESCRIPTION, StatusPrecatorio, TaskAction, TaskStatus


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
    extraction_method: str
    extraction_confidence: float
    extraction_warnings: list[str]
    llm_recommended: bool
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
    precatorio_numero: str = Field(
        description=f"{PRECATORIO_FORMAT_DESCRIPTION} Exemplo: {PRECATORIO_EXAMPLE}.",
        examples=[PRECATORIO_EXAMPLE],
    )
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
    ente_devedor: str | None = Field(
        default="Estado do Parana",
        max_length=120,
        description="Texto usado para tentar selecionar o orgao devedor no dropdown do TJPR.",
    )
    timeout_segundos: int = Field(
        default=180,
        ge=30,
        le=900,
        description="Tempo maximo para o usuario resolver o captcha, clicar em Pesquisar e a tabela aparecer.",
    )


class ColetaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    numero: str
    ordem: int
    origem: str
    collected_at: datetime


class RpaCollectResponse(BaseModel):
    total: int
    numeros: list[str]
    avisos: list[str] = Field(
        default_factory=list,
        description=(
            "Alertas da coleta. Quando o portal exibe Autos do Precatorio mascarado, "
            "a resposta informa que foi persistido o Oficio Precatorio."
        ),
    )


class ProcessamentoResponse(BaseModel):
    precatorio: PrecatorioRead
    tarefa: TaskRead
    eventos_criados: int
