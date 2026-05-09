from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class Precatorio(Base, TimestampMixin):
    __tablename__ = "precatorios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    credor: Mapped[str | None] = mapped_column(String(255))
    documento_credor: Mapped[str | None] = mapped_column(String(32))
    ente_devedor: Mapped[str | None] = mapped_column(String(255))
    processo_originario: Mapped[str | None] = mapped_column(String(32))
    natureza: Mapped[str | None] = mapped_column(String(64))
    valor_centavos: Mapped[int | None] = mapped_column(Integer)
    posicao_fila: Mapped[int | None] = mapped_column(Integer)
    previsao_orcamentaria: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    status_motivo: Mapped[str] = mapped_column(Text, nullable=False)
    documento_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class ColetaPrecatorio(Base):
    __tablename__ = "coleta_precatorios"
    __table_args__ = (UniqueConstraint("numero", name="uq_coleta_precatorio_numero"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    origem: Mapped[str] = mapped_column(String(255), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class FilaTask(Base, TimestampMixin):
    __tablename__ = "fila_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    precatorio_numero: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    acao: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    prioridade: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    motivo: Mapped[str] = mapped_column(Text, nullable=False)


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    precatorio_numero: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    tipo: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    descricao: Mapped[str] = mapped_column(Text, nullable=False)
    data_evento: Mapped[date | None] = mapped_column(Date)
    precisao: Mapped[str] = mapped_column(String(16), nullable=False, default="desconhecida")
    origem: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

