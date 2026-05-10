from __future__ import annotations

from enum import Enum


PRECATORIO_PATTERN = r"\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}"
PRECATORIO_FULL_PATTERN = rf"^{PRECATORIO_PATTERN}$"
OFICIO_PRECATORIO_PATTERN = r"\d{4}/\d{6}"
COLETA_PRECATORIO_PATTERN = rf"(?:{PRECATORIO_PATTERN}|{OFICIO_PRECATORIO_PATTERN})"
COLETA_PRECATORIO_FULL_PATTERN = rf"^{COLETA_PRECATORIO_PATTERN}$"


class StatusPrecatorio(str, Enum):
    AGUARDANDO_PAGAMENTO = "AGUARDANDO_PAGAMENTO"
    SUSPENSO = "SUSPENSO"
    PAGO = "PAGO"
    CANCELADO = "CANCELADO"
    REVISAO_NECESSARIA = "REVISAO_NECESSARIA"


class TaskStatus(str, Enum):
    PENDENTE = "PENDENTE"
    CONCLUIDA = "CONCLUIDA"
    CANCELADA = "CANCELADA"


class TaskAction(str, Enum):
    MONITORAR_PAGAMENTO = "MONITORAR_PAGAMENTO"
    ACOMPANHAR_SUSPENSAO = "ACOMPANHAR_SUSPENSAO"
    CONCILIAR_PAGAMENTO = "CONCILIAR_PAGAMENTO"
    AUDITAR_CANCELAMENTO = "AUDITAR_CANCELAMENTO"
    REVISAR_CLASSIFICACAO = "REVISAR_CLASSIFICACAO"


TASK_RULES: dict[StatusPrecatorio, tuple[TaskAction, int, str]] = {
    StatusPrecatorio.REVISAO_NECESSARIA: (
        TaskAction.REVISAR_CLASSIFICACAO,
        1,
        "Documento exige revisao antes da decisao operacional.",
    ),
    StatusPrecatorio.SUSPENSO: (
        TaskAction.ACOMPANHAR_SUSPENSAO,
        2,
        "Status impede pagamento e exige acompanhamento ativo.",
    ),
    StatusPrecatorio.AGUARDANDO_PAGAMENTO: (
        TaskAction.MONITORAR_PAGAMENTO,
        3,
        "Precatorio esta apto para monitoramento de fila e orcamento.",
    ),
    StatusPrecatorio.CANCELADO: (
        TaskAction.AUDITAR_CANCELAMENTO,
        4,
        "Cancelamento deve ser auditado antes de encerramento operacional.",
    ),
    StatusPrecatorio.PAGO: (
        TaskAction.CONCILIAR_PAGAMENTO,
        5,
        "Pagamento identificado deve ser conciliado e baixado.",
    ),
}


def task_rule_for_status(status: StatusPrecatorio) -> tuple[TaskAction, int, str]:
    return TASK_RULES[status]
