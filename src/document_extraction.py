from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date
from typing import Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError

from src.document_parser import ParsedDocument, ParsedEvent, parse_document_text
from src.domain import StatusPrecatorio

DEFAULT_LLM_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_LLM_MODEL = "llama-3.3-70b-versatile"


@dataclass(frozen=True)
class ExtractionResult:
    document: ParsedDocument
    method: str
    confidence: float
    warnings: list[str]
    llm_recommended: bool


class DocumentExtractor(Protocol):
    def extract(self, text: str, fallback_numero: str | None = None) -> ExtractionResult:
        pass


class RuleBasedDocumentExtractor:
    method = "rule_based"

    def extract(self, text: str, fallback_numero: str | None = None) -> ExtractionResult:
        parsed = parse_document_text(text, fallback_numero=fallback_numero)
        warnings = _build_extraction_warnings(parsed)
        return ExtractionResult(
            document=parsed,
            method=self.method,
            confidence=_estimate_confidence(parsed, warnings),
            warnings=warnings,
            llm_recommended=_should_recommend_llm(parsed, warnings),
        )


class LlmAssistedDocumentExtractor:
    method = "llm_assisted"

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_LLM_MODEL,
        base_url: str = DEFAULT_LLM_BASE_URL,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def extract(self, text: str, fallback_numero: str | None = None) -> ExtractionResult:
        payload = {
            "model": self.model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": _llm_system_prompt(),
                },
                {
                    "role": "user",
                    "content": _llm_user_prompt(text, fallback_numero),
                },
            ],
        }
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        parsed_payload = LlmDocumentPayload.model_validate_json(_extract_json_object(content))
        parsed_document = parsed_payload.to_parsed_document(text, fallback_numero=fallback_numero)
        warnings = list(parsed_payload.warnings)
        if not parsed_payload.evidencias:
            warnings.append("LLM nao retornou evidencias textuais.")
        return ExtractionResult(
            document=parsed_document,
            method=self.method,
            confidence=parsed_payload.confianca,
            warnings=warnings,
            llm_recommended=False,
        )


class HybridDocumentExtractor:
    def __init__(
        self,
        rule_based_extractor: DocumentExtractor | None = None,
        llm_extractor: DocumentExtractor | None = None,
        llm_threshold: float = 0.75,
    ) -> None:
        self.rule_based_extractor = rule_based_extractor or RuleBasedDocumentExtractor()
        self.llm_extractor = llm_extractor
        self.llm_threshold = llm_threshold

    def extract(self, text: str, fallback_numero: str | None = None) -> ExtractionResult:
        result = self.rule_based_extractor.extract(text, fallback_numero=fallback_numero)
        if not result.llm_recommended or result.confidence >= self.llm_threshold:
            return result
        if not self.llm_extractor:
            return result
        try:
            return self.llm_extractor.extract(text, fallback_numero=fallback_numero)
        except (httpx.HTTPError, KeyError, ValueError, ValidationError, json.JSONDecodeError) as exc:
            # A LLM e apenas assistiva: falha externa ou resposta malformada
            # nao deve interromper o fluxo principal da aplicacao.
            warnings = [*result.warnings, f"Falha ao acionar LLM; mantido resultado por regras: {exc}"]
            return ExtractionResult(
                document=result.document,
                method=result.method,
                confidence=result.confidence,
                warnings=warnings,
                llm_recommended=True,
            )


def extract_document_text(text: str, fallback_numero: str | None = None) -> ExtractionResult:
    return build_document_extractor().extract(text, fallback_numero=fallback_numero)


def build_document_extractor() -> HybridDocumentExtractor:
    llm_threshold = float(os.getenv("LLM_CONFIDENCE_THRESHOLD", "0.75"))
    if not _env_flag("LLM_ENABLED"):
        return HybridDocumentExtractor(llm_threshold=llm_threshold)

    # GROQ_API_KEY e a chave concreta do provedor; LLM_API_KEY mantem o
    # adaptador reutilizavel com outros provedores OpenAI-compatible.
    api_key = os.getenv("GROQ_API_KEY") or os.getenv("LLM_API_KEY")
    if not api_key:
        return HybridDocumentExtractor(
            rule_based_extractor=LlmUnavailableRuleBasedExtractor("LLM habilitada, mas GROQ_API_KEY nao configurada."),
            llm_threshold=llm_threshold,
        )

    llm_extractor = LlmAssistedDocumentExtractor(
        api_key=api_key,
        model=os.getenv("LLM_MODEL", DEFAULT_LLM_MODEL),
        base_url=os.getenv("LLM_BASE_URL", DEFAULT_LLM_BASE_URL),
        timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
    )
    return HybridDocumentExtractor(llm_extractor=llm_extractor, llm_threshold=llm_threshold)


class LlmUnavailableRuleBasedExtractor(RuleBasedDocumentExtractor):
    def __init__(self, warning: str) -> None:
        self.warning = warning

    def extract(self, text: str, fallback_numero: str | None = None) -> ExtractionResult:
        result = super().extract(text, fallback_numero=fallback_numero)
        if not result.llm_recommended:
            return result
        return ExtractionResult(
            document=result.document,
            method=result.method,
            confidence=result.confidence,
            warnings=[*result.warnings, self.warning],
            llm_recommended=True,
        )


class LlmEventPayload(BaseModel):
    tipo: str = Field(min_length=3, max_length=64)
    titulo: str = Field(min_length=3, max_length=255)
    descricao: str = Field(min_length=3)
    data_evento: date | None = None
    precisao: str = Field(default="desconhecida", max_length=16)

    def to_parsed_event(self) -> ParsedEvent:
        return ParsedEvent(
            tipo=self.tipo,
            titulo=self.titulo,
            descricao=self.descricao,
            data_evento=self.data_evento,
            precisao=self.precisao,
        )


class LlmDocumentPayload(BaseModel):
    numero: str
    credor: str | None = None
    documento_credor: str | None = None
    ente_devedor: str | None = None
    processo_originario: str | None = None
    natureza: str | None = None
    valor_centavos: int | None = None
    posicao_fila: int | None = None
    previsao_orcamentaria: int | None = None
    status: StatusPrecatorio
    status_motivo: str = Field(min_length=3)
    eventos: list[LlmEventPayload] = Field(default_factory=list)
    confianca: float = Field(ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)
    evidencias: list[str] = Field(default_factory=list)

    def to_parsed_document(self, raw_text: str, fallback_numero: str | None = None) -> ParsedDocument:
        rule_based = parse_document_text(raw_text, fallback_numero=fallback_numero)
        return ParsedDocument(
            numero=self.numero or rule_based.numero,
            credor=self.credor,
            documento_credor=self.documento_credor,
            ente_devedor=self.ente_devedor,
            processo_originario=self.processo_originario,
            natureza=self.natureza,
            valor_centavos=self.valor_centavos,
            posicao_fila=self.posicao_fila,
            previsao_orcamentaria=self.previsao_orcamentaria,
            status=self.status,
            status_motivo=self.status_motivo,
            documento_hash=rule_based.documento_hash,
            eventos=[event.to_parsed_event() for event in self.eventos],
            warnings=[],
        )


def _build_extraction_warnings(parsed: ParsedDocument) -> list[str]:
    warnings: list[str] = list(parsed.warnings)
    expected_fields = {
        "credor": parsed.credor,
        "ente_devedor": parsed.ente_devedor,
        "processo_originario": parsed.processo_originario,
        "valor_centavos": parsed.valor_centavos,
    }
    if parsed.status != StatusPrecatorio.PAGO:
        expected_fields["natureza"] = parsed.natureza
    if parsed.status == StatusPrecatorio.AGUARDANDO_PAGAMENTO:
        expected_fields["posicao_fila"] = parsed.posicao_fila
        expected_fields["previsao_orcamentaria"] = parsed.previsao_orcamentaria
    for field_name, value in expected_fields.items():
        if value is None:
            warnings.append(f"Campo esperado ausente: {field_name}.")

    if parsed.status_motivo.startswith("Status nao explicito"):
        warnings.append("Status classificado por fallback conservador.")
    if parsed.status == StatusPrecatorio.REVISAO_NECESSARIA:
        warnings.append("Documento possui ambiguidade critica de status.")

    if not parsed.eventos:
        warnings.append("Nenhum evento foi extraido para a timeline.")

    return list(dict.fromkeys(warnings))


def _estimate_confidence(parsed: ParsedDocument, warnings: list[str]) -> float:
    confidence = max(0.5, 1.0 - (0.08 * len(warnings)))
    if parsed.status_motivo.startswith("Status nao explicito"):
        confidence = min(confidence, 0.65)
    if parsed.status == StatusPrecatorio.REVISAO_NECESSARIA:
        confidence = min(confidence, 0.6)
    return round(confidence, 2)


def _should_recommend_llm(parsed: ParsedDocument, warnings: list[str]) -> bool:
    if parsed.status_motivo.startswith("Status nao explicito"):
        return True
    if parsed.status == StatusPrecatorio.REVISAO_NECESSARIA:
        return True
    return len(warnings) >= 2


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on", "sim"}


def _extract_json_object(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    fenced = stripped
    if fenced.startswith("```"):
        fenced = re.sub(r"^```(?:json)?\s*", "", fenced)
        fenced = re.sub(r"\s*```$", "", fenced)
    start = fenced.find("{")
    end = fenced.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("LLM nao retornou JSON valido.")
    return fenced[start : end + 1]


def _llm_system_prompt() -> str:
    return """
Voce extrai dados estruturados de textos OCR de precatorios judiciais brasileiros.
Responda somente JSON valido, sem markdown.
Nao invente informacoes ausentes. Use null quando o campo nao estiver claro.
Classifique status em apenas um destes valores:
AGUARDANDO_PAGAMENTO, SUSPENSO, PAGO, CANCELADO, REVISAO_NECESSARIA.
Use REVISAO_NECESSARIA quando houver negacoes ou sinais conflitantes que impeçam classificacao segura.
Datas devem usar ISO 8601 YYYY-MM-DD quando conhecidas.
Quando so houver ano, use YYYY-01-01 e precisao "ano".
Quando so houver mes/ano, use o primeiro dia do mes e precisao "mes".
""".strip()


def _llm_user_prompt(text: str, fallback_numero: str | None) -> str:
    return f"""
Extraia o documento abaixo para este schema JSON:
{{
  "numero": "string",
  "credor": "string ou null",
  "documento_credor": "CPF/CNPJ ou null",
  "ente_devedor": "string ou null",
  "processo_originario": "string ou null",
  "natureza": "alimentar, nao alimentar ou null",
  "valor_centavos": "inteiro ou null",
  "posicao_fila": "inteiro ou null",
  "previsao_orcamentaria": "inteiro com ano ou null",
  "status": "AGUARDANDO_PAGAMENTO|SUSPENSO|PAGO|CANCELADO|REVISAO_NECESSARIA",
  "status_motivo": "justificativa curta",
  "eventos": [
    {{
      "tipo": "AJUIZAMENTO|TRANSITO_JULGADO|OFICIO_REQUISITORIO|STATUS_IDENTIFICADO|HISTORICO_DOCUMENTO",
      "titulo": "string",
      "descricao": "string",
      "data_evento": "YYYY-MM-DD ou null",
      "precisao": "dia|mes|ano|desconhecida"
    }}
  ],
  "confianca": "numero entre 0 e 1",
  "warnings": ["avisos sobre campos ambiguos"],
  "evidencias": ["trechos literais curtos do documento que sustentam a classificacao"]
}}

Numero informado pela rota, se o texto nao trouxer numero claro: {fallback_numero or "null"}

Documento:
\"\"\"
{text}
\"\"\"
""".strip()
