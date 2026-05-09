from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from src.domain import PRECATORIO_PATTERN, StatusPrecatorio

PRECATORIO_RE = re.compile(rf"\b{PRECATORIO_PATTERN}\b")
CPF_RE = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
CNPJ_RE = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")
PROCESSO_RE = re.compile(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b")
DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
YEAR_LINE_RE = re.compile(r"^\s*-\s*(\d{4})\s*:\s*(.+)$", re.MULTILINE)

MONTHS = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}


@dataclass(frozen=True)
class ParsedEvent:
    tipo: str
    titulo: str
    descricao: str
    data_evento: date | None
    precisao: str


@dataclass(frozen=True)
class ParsedDocument:
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
    eventos: list[ParsedEvent]


def parse_document_text(text: str, fallback_numero: str | None = None) -> ParsedDocument:
    numero = _find_precatorio_number(text, fallback_numero=fallback_numero) or fallback_numero
    if not numero:
        raise ValueError("Numero do precatorio nao encontrado no documento.")

    status, status_motivo = _classify_status(text)
    return ParsedDocument(
        numero=numero,
        credor=_extract_creditor(text),
        documento_credor=_extract_documento_credor(text),
        ente_devedor=_extract_devedor(text),
        processo_originario=_extract_processo_originario(text),
        natureza=_extract_natureza(text),
        valor_centavos=_extract_money(text),
        posicao_fila=_extract_int_after(text, r"posicao(?:\s+estimada)?\s+na\s+fila\s*:\s*(\d+)"),
        previsao_orcamentaria=_extract_int_after(text, r"(?:orcamento\s+previsto|previsao\s+orc)\s*:\s*(\d{4})"),
        status=status,
        status_motivo=status_motivo,
        documento_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        eventos=_extract_events(text, status, status_motivo),
    )


def _find_precatorio_number(text: str, fallback_numero: str | None = None) -> str | None:
    if fallback_numero and fallback_numero in text:
        return fallback_numero

    # Numeros CNJ tambem aparecem como processo originario; so trata como
    # precatorio quando o contexto textual deixar esse papel explicito.
    explicit_patterns = (
        rf"(?:precatorio|precat[oó]rio)\s*(?:n\.?|numero|n[uú]mero)?\s*[:.]?\s*({PRECATORIO_PATTERN})",
        rf"(?:numero|n[uú]mero)\s*[:.]?\s*({PRECATORIO_PATTERN})",
        rf"of\.?\s*req\.?\s*({PRECATORIO_PATTERN})",
    )
    for pattern in explicit_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)

    if fallback_numero:
        return fallback_numero

    match = PRECATORIO_RE.search(text)
    return match.group(0) if match else None


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return without_marks.lower()


def _line_value(text: str, labels: tuple[str, ...]) -> str | None:
    normalized_labels = "|".join(re.escape(label) for label in labels)
    pattern = re.compile(rf"^\s*(?:{normalized_labels})\s*:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
    match = pattern.search(text)
    return _clean_value(match.group(1)) if match else None


def _clean_value(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip())
    cleaned = re.split(r"\s+-\s+(?:cpf|cnpj)\b", cleaned, flags=re.IGNORECASE)[0]
    return cleaned.strip(" .")


def _extract_creditor(text: str) -> str | None:
    value = _line_value(text, ("titular", "beneficiario", "credor"))
    if value:
        return value

    match = re.search(r"como\s+credor\s+([^,\.]+)", text, re.IGNORECASE)
    return _clean_value(match.group(1)) if match else None


def _extract_documento_credor(text: str) -> str | None:
    cpf = CPF_RE.search(text)
    if cpf:
        return cpf.group(0)
    cnpj = CNPJ_RE.search(text)
    return cnpj.group(0) if cnpj else None


def _extract_devedor(text: str) -> str | None:
    value = _line_value(text, ("ente devedor", "devedor", "ente"))
    if value:
        return value

    match = re.search(r"ente\s+devedor\s+o\s+([^\.]+)", text, re.IGNORECASE)
    return _clean_value(match.group(1)) if match else None


def _extract_processo_originario(text: str) -> str | None:
    patterns = [
        r"(?:proc\.?\s*orig|processo\s+originario|proc\.?\s*originario)\s*:\s*(" + PRECATORIO_PATTERN + r")",
        r"processo\s+originario\s+(" + PRECATORIO_PATTERN + r")",
        r"autos\s+judiciais\s+n\.?\s*(" + PRECATORIO_PATTERN + r")",
        r"autos\s+n\.?\s*(" + PRECATORIO_PATTERN + r")",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)

    numbers = PROCESSO_RE.findall(text)
    if len(numbers) > 1:
        return numbers[1]
    return None


def _extract_natureza(text: str) -> str | None:
    return _line_value(text, ("natureza do credito", "natureza", "nat"))


def _extract_money(text: str) -> int | None:
    match = re.search(r"(?:R\$\s*)?(\d{1,3}(?:\.\d{3})*,\d{2})", text)
    if not match:
        return None
    integer_part, cents_part = match.group(1).replace(".", "").split(",")
    return int(integer_part) * 100 + int(cents_part)


def _extract_int_after(text: str, pattern: str) -> int | None:
    match = re.search(pattern, _normalize(text), re.IGNORECASE)
    return int(match.group(1)) if match else None


def _classify_status(text: str) -> tuple[StatusPrecatorio, str]:
    normalized = _normalize(text)

    if _has_critical_status_ambiguity(normalized):
        return (
            StatusPrecatorio.REVISAO_NECESSARIA,
            "Documento contem ambiguidade critica, negacao ou sinais conflitantes sobre pagamento, suspensao ou cancelamento.",
        )

    if _contains_any(normalized, ("cancelado", "cancelamento", "anulado", "sem efeito")):
        return StatusPrecatorio.CANCELADO, "Documento indica cancelamento, anulacao ou perda de efeito."

    if _contains_any(
        normalized,
        (
            "quitado",
            "credito extinto",
            "pagamento integral",
            "pagamento efetivado",
            "extincao por pagamento",
            "baixa determinada",
        ),
    ):
        return StatusPrecatorio.PAGO, "Documento indica pagamento, quitacao ou baixa por pagamento."

    if _contains_any(
        normalized,
        (
            "suspenso",
            "suspensao",
            "liminar",
            "analise documental pendente",
            "documentacao do cessionario incompleta",
            "aguardando regularizacao",
        ),
    ):
        return StatusPrecatorio.SUSPENSO, "Documento indica suspensao ou pendencia impeditiva de pagamento."

    if _contains_any(normalized, ("aguardando pagamento", "aguardando ordem cronologica", "posicao na fila", "orcamento previsto")):
        return StatusPrecatorio.AGUARDANDO_PAGAMENTO, "Documento indica permanencia em fila de pagamento."

    return StatusPrecatorio.AGUARDANDO_PAGAMENTO, "Status nao explicito; classificado como aguardando por conservadorismo."


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)


def _has_critical_status_ambiguity(normalized: str) -> bool:
    # Frases juridicas negadas sao mais seguras como REVISAO_NECESSARIA do que
    # falso positivo de PAGO, SUSPENSO ou CANCELADO por uma palavra isolada.
    status_terms = r"(?:pagamento|deposito|quitacao|baixa|suspensao|suspenso|cancelamento|cancelado)"
    negation_patterns = (
        rf"\bnao\s+(?:ha|consta|existe|houve|foi|foram)\b[^\.\n]{{0,120}}\b{status_terms}\b",
        rf"\bsem\s+(?:noticia|registro|comprovante|decisao)\b[^\.\n]{{0,120}}\b{status_terms}\b",
        rf"\bausente\s+(?:comprovante|registro|decisao)\b[^\.\n]{{0,120}}\b{status_terms}\b",
    )
    indirect_final_state_patterns = (
        r"\bperda\s+de\s+efeito\b",
        r"\bretirad[ao]\b[^\.\n]{0,120}\b(?:relacao|lista)\b[^\.\n]{0,120}\bpagamentos?\b",
        r"\bnao\s+subsiste\b[^\.\n]{0,120}\bobrigacao\s+de\s+pagamento\b",
    )
    return any(re.search(pattern, normalized) for pattern in (*negation_patterns, *indirect_final_state_patterns))


def _extract_events(text: str, status: StatusPrecatorio, status_motivo: str) -> list[ParsedEvent]:
    events: list[ParsedEvent] = []
    events.extend(_extract_historical_events(text))
    oficio_date, oficio_precision = _extract_oficio_date(text)
    if oficio_date:
        events.append(
            ParsedEvent(
                tipo="OFICIO_REQUISITORIO",
                titulo="Oficio requisitorio expedido",
                descricao="Data do oficio requisitorio identificada no documento.",
                data_evento=oficio_date,
                precisao=oficio_precision,
            )
        )

    status_date, status_precision = _extract_status_date(text, status)
    events.append(
        ParsedEvent(
            tipo="STATUS_IDENTIFICADO",
            titulo=f"Status classificado como {status.value}",
            descricao=status_motivo,
            data_evento=status_date,
            precisao=status_precision,
        )
    )
    return _dedupe_events(events)


def _extract_historical_events(text: str) -> list[ParsedEvent]:
    events: list[ParsedEvent] = []
    normalized = _normalize(text)

    ajuizado = re.search(r"ajuizado\s+em\s+([a-z]+)\s+de\s+(\d{4})", normalized)
    if ajuizado:
        month = MONTHS.get(ajuizado.group(1))
        if month:
            events.append(
                ParsedEvent(
                    tipo="AJUIZAMENTO",
                    titulo="Processo ajuizado",
                    descricao="Ajuizamento extraido do texto do documento.",
                    data_evento=date(int(ajuizado.group(2)), month, 1),
                    precisao="mes",
                )
            )

    for match in YEAR_LINE_RE.finditer(text):
        year = int(match.group(1))
        description = _clean_value(match.group(2))
        normalized_description = _normalize(description)
        if "ajuizamento" in normalized_description:
            tipo = "AJUIZAMENTO"
            titulo = "Processo ajuizado"
        elif "transito" in normalized_description:
            tipo = "TRANSITO_JULGADO"
            titulo = "Transito em julgado"
        else:
            tipo = "HISTORICO_DOCUMENTO"
            titulo = "Evento historico informado"

        events.append(
            ParsedEvent(
                tipo=tipo,
                titulo=titulo,
                descricao=description,
                data_evento=date(year, 1, 1),  # Eventos com apenas ano usam 1 de janeiro e preservam precisao.
                precisao="ano",
            )
        )
    return events


def _extract_oficio_date(text: str) -> tuple[date | None, str]:
    patterns = [
        r"(?:oficio\s+requisitorio\s+expedido\s+em|data\s+oficio|oficio\s+requisitorio|oficio)\s*:\s*([^\n]+)",
        r"oficio\s+requisitorio\s+foi\s+expedido\s+.+?\s+em\s+([^\.]+)",
    ]
    return _extract_date_near(text, patterns)


def _extract_status_date(text: str, status: StatusPrecatorio) -> tuple[date | None, str]:
    normalized = _normalize(text)
    if status == StatusPrecatorio.SUSPENSO:
        return _extract_date_near(normalized, (r"decisao\s+proferida\s+em\s+([^,\n\.]+)",))
    if status == StatusPrecatorio.PAGO:
        return _extract_date_near(
            normalized,
            (
                r"pagamento\s+integral\s+realizado\s+em\s+([^,\n\.]+)",
                r"pagamento\s+efetivado\s+em\s+([^,\n\.]+)",
                r"baixa\s+determinada\s+.+?\s+em\s+([^,\n\.]+)",
            ),
        )
    return None, "desconhecida"


def _extract_date_near(text: str, patterns: tuple[str, ...] | list[str]) -> tuple[date | None, str]:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        parsed = _parse_date_fragment(match.group(1))
        if parsed[0]:
            return parsed
    return None, "desconhecida"


def _parse_date_fragment(fragment: str) -> tuple[date | None, str]:
    numeric = DATE_RE.search(fragment)
    if numeric:
        day, month, year = map(int, numeric.groups())
        return date(year, month, day), "dia"

    normalized = _normalize(fragment)
    full = re.search(r"(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})", normalized)
    if full:
        month = MONTHS.get(full.group(2))
        if month:
            return date(int(full.group(3)), month, int(full.group(1))), "dia"

    month_year = re.search(r"([a-z]+)\s+de\s+(\d{4})", normalized)
    if month_year:
        month = MONTHS.get(month_year.group(1))
        if month:
            return date(int(month_year.group(2)), month, 1), "mes"

    return None, "desconhecida"


def _dedupe_events(events: list[ParsedEvent]) -> list[ParsedEvent]:
    seen: set[tuple[str, str, date | None, str]] = set()
    deduped: list[ParsedEvent] = []
    for event in events:
        key = (event.tipo, event.titulo, event.data_evento, event.descricao)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(event)
    return deduped
