from __future__ import annotations

from enum import Enum


PRECATORIO_PATTERN = r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"
PRECATORIO_FULL_PATTERN = rf"^{PRECATORIO_PATTERN}$"


class StatusPrecatorio(str, Enum):
    AGUARDANDO_PAGAMENTO = "AGUARDANDO_PAGAMENTO"
    SUSPENSO = "SUSPENSO"
    PAGO = "PAGO"
    CANCELADO = "CANCELADO"


class TaskStatus(str, Enum):
    PENDENTE = "PENDENTE"
    CONCLUIDA = "CONCLUIDA"
    CANCELADA = "CANCELADA"


class TaskAction(str, Enum):
    MONITORAR_PAGAMENTO = "MONITORAR_PAGAMENTO"
    ACOMPANHAR_SUSPENSAO = "ACOMPANHAR_SUSPENSAO"
    CONCILIAR_PAGAMENTO = "CONCILIAR_PAGAMENTO"
    AUDITAR_CANCELAMENTO = "AUDITAR_CANCELAMENTO"


TASK_RULES: dict[StatusPrecatorio, tuple[TaskAction, int, str]] = {
    StatusPrecatorio.SUSPENSO: (
        TaskAction.ACOMPANHAR_SUSPENSAO,
        1,
        "Status impede pagamento e exige acompanhamento ativo.",
    ),
    StatusPrecatorio.AGUARDANDO_PAGAMENTO: (
        TaskAction.MONITORAR_PAGAMENTO,
        2,
        "Precatorio esta apto para monitoramento de fila e orcamento.",
    ),
    StatusPrecatorio.CANCELADO: (
        TaskAction.AUDITAR_CANCELAMENTO,
        3,
        "Cancelamento deve ser auditado antes de encerramento operacional.",
    ),
    StatusPrecatorio.PAGO: (
        TaskAction.CONCILIAR_PAGAMENTO,
        4,
        "Pagamento identificado deve ser conciliado e baixado.",
    ),
}


def task_rule_for_status(status: StatusPrecatorio) -> tuple[TaskAction, int, str]:
    return TASK_RULES[status]
