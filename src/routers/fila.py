from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.database import get_db
from src.schemas import TaskCreate, TaskRead
from src.services import create_manual_task, queue_query

router = APIRouter(prefix="/fila", tags=["fila"])


@router.get("", response_model=list[TaskRead])
def listar_fila(db: Session = Depends(get_db)) -> list[TaskRead]:
    return list(db.execute(queue_query()).scalars().all())


@router.post("", response_model=TaskRead, status_code=201)
def criar_task(payload: TaskCreate, db: Session = Depends(get_db)) -> TaskRead:
    return create_manual_task(
        precatorio_numero=payload.precatorio_numero,
        acao=payload.acao,
        prioridade=payload.prioridade,
        motivo=payload.motivo,
        db=db,
    )

