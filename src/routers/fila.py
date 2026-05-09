from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.database import get_db
from src.schemas import TaskCreate, TaskRead
from src.services import create_manual_task, queue_query

router = APIRouter(prefix="/fila", tags=["fila"])


@router.get(
    "",
    response_model=list[TaskRead],
    summary="Consultar fila de processamento",
    description=(
        "Retorna as tarefas enfileiradas para execução futura. A ordenação segue "
        "prioridade crescente e, em caso de empate, a ordem de chegada."
    ),
)
def listar_fila(db: Session = Depends(get_db)) -> list[TaskRead]:
    return list(db.execute(queue_query()).scalars().all())


@router.post(
    "",
    response_model=TaskRead,
    status_code=201,
    summary="Inserir tarefa manual na fila",
    description=(
        "Cria uma tarefa operacional manual para um precatório já identificado. "
        "Esse endpoint complementa a fila automática criada durante o processamento "
        "do documento."
    ),
)
def criar_task(payload: TaskCreate, db: Session = Depends(get_db)) -> TaskRead:
    return create_manual_task(
        precatorio_numero=payload.precatorio_numero,
        acao=payload.acao,
        prioridade=payload.prioridade,
        motivo=payload.motivo,
        db=db,
    )
