from __future__ import annotations

from src.document_extraction import (
    HybridDocumentExtractor,
    LlmAssistedDocumentExtractor,
    RuleBasedDocumentExtractor,
    build_document_extractor,
    extract_document_text,
)
from src.domain import StatusPrecatorio


def test_extrator_padrao_preserva_parser_por_regras() -> None:
    text = """
    PRECATORIO N. 0067842-91.2022.8.16.0000
    Credor: LUIZ FERNANDO MARTINS ROCHA
    Ente Devedor: MUNICIPIO DE FOZ DO IGUACU
    Processo originario: 0007781-45.2016.8.16.0030
    Natureza do credito: alimentar
    Valor inscrito: R$ 98.340,75
    Situacao: AGUARDANDO ORDEM CRONOLOGICA
    Posicao estimada na fila: 428
    """

    result = extract_document_text(text)

    assert result.method == "rule_based"
    assert result.document.status == StatusPrecatorio.AGUARDANDO_PAGAMENTO
    assert result.document.posicao_fila == 428
    assert result.confidence >= 0.8
    assert result.llm_recommended is False


def test_extrator_nao_exige_fila_ou_orcamento_para_precatorio_pago() -> None:
    text = """
    Precatorio de numero 0028934-17.2017.8.16.0000 referente ao processo
    originario 0000891-23.2009.8.16.0001, tendo como credor PEDRO HENRIQUE
    ALVES DA SILVA, portador do CPF de numero 789.012.345-67, e como ente
    devedor o Municipio de Maringa.
    Valor original inscrito: R$ 56.230,00.
    Informamos que o referido precatorio foi QUITADO em sua totalidade.
    """

    result = RuleBasedDocumentExtractor().extract(text)

    assert result.document.status == StatusPrecatorio.PAGO
    assert result.document.posicao_fila is None
    assert result.document.previsao_orcamentaria is None
    assert "Campo esperado ausente: posicao_fila." not in result.warnings
    assert "Campo esperado ausente: previsao_orcamentaria." not in result.warnings
    assert "Campo esperado ausente: natureza." not in result.warnings


def test_extrator_exige_fila_e_orcamento_para_precatorio_aguardando_pagamento() -> None:
    text = """
    PRECATORIO N. 0067842-91.2022.8.16.0000
    Credor: LUIZ FERNANDO MARTINS ROCHA
    Ente Devedor: MUNICIPIO DE FOZ DO IGUACU
    Processo originario: 0007781-45.2016.8.16.0030
    Natureza do credito: alimentar
    Valor inscrito: R$ 98.340,75
    Situacao: AGUARDANDO PAGAMENTO
    """

    result = RuleBasedDocumentExtractor().extract(text)

    assert result.document.status == StatusPrecatorio.AGUARDANDO_PAGAMENTO
    assert "Campo esperado ausente: posicao_fila." in result.warnings
    assert "Campo esperado ausente: previsao_orcamentaria." in result.warnings


def test_extrator_recomenda_llm_quando_documento_e_ambiguo() -> None:
    text = """
    PRECATORIO N. 0067842-91.2022.8.16.0000
    Documento recebido sem campos estruturados claros.
    """

    result = RuleBasedDocumentExtractor().extract(text)

    assert result.method == "rule_based"
    assert result.document.status == StatusPrecatorio.AGUARDANDO_PAGAMENTO
    assert result.confidence < 0.75
    assert result.llm_recommended is True
    assert "Status classificado por fallback conservador." in result.warnings


def test_extrator_recomenda_llm_em_ambiguidade_critica() -> None:
    text = """
    PRECATORIO N. 0088888-44.2024.8.16.0000
    Credor: MARIA APARECIDA GOMES
    Ente Devedor: MUNICIPIO DE PONTA GROSSA
    Valor inscrito: R$ 212.450,30
    Nao ha comprovante de deposito integral, baixa definitiva ou decisao de cancelamento.
    """

    result = RuleBasedDocumentExtractor().extract(text)

    assert result.document.status == StatusPrecatorio.REVISAO_NECESSARIA
    assert result.confidence <= 0.6
    assert result.llm_recommended is True
    assert "Documento possui ambiguidade critica de status." in result.warnings


def test_extrator_hibrido_mantem_regras_quando_llm_nao_foi_configurada() -> None:
    text = """
    PRECATORIO N. 0067842-91.2022.8.16.0000
    Documento recebido sem campos estruturados claros.
    """

    result = HybridDocumentExtractor(llm_extractor=None).extract(text)

    assert result.method == "rule_based"
    assert result.llm_recommended is True


def test_build_extractor_mantem_ia_desligada_por_padrao(monkeypatch) -> None:
    monkeypatch.delenv("LLM_ENABLED", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    result = build_document_extractor().extract(
        """
        PRECATORIO N. 0067842-91.2022.8.16.0000
        Documento recebido sem campos estruturados claros.
        """
    )

    assert result.method == "rule_based"
    assert result.llm_recommended is True
    assert not any("GROQ_API_KEY" in warning for warning in result.warnings)


def test_build_extractor_sinaliza_chave_ausente_quando_ia_ligada(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    result = build_document_extractor().extract(
        """
        PRECATORIO N. 0067842-91.2022.8.16.0000
        Documento recebido sem campos estruturados claros.
        """
    )

    assert result.method == "rule_based"
    assert result.llm_recommended is True
    assert "LLM habilitada, mas GROQ_API_KEY nao configurada." in result.warnings


def test_extrator_llm_processa_resposta_json_mockada(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": """
                            {
                              "numero": "0067842-91.2022.8.16.0000",
                              "credor": "LUIZ FERNANDO MARTINS ROCHA",
                              "documento_credor": "231.987.654-00",
                              "ente_devedor": "MUNICIPIO DE FOZ DO IGUACU",
                              "processo_originario": "0007781-45.2016.8.16.0030",
                              "natureza": "alimentar",
                              "valor_centavos": 9834075,
                              "posicao_fila": 428,
                              "previsao_orcamentaria": 2026,
                              "status": "AGUARDANDO_PAGAMENTO",
                              "status_motivo": "Documento informa aguardando ordem cronologica.",
                              "eventos": [
                                {
                                  "tipo": "STATUS_IDENTIFICADO",
                                  "titulo": "Status identificado",
                                  "descricao": "Aguardando ordem cronologica",
                                  "data_evento": null,
                                  "precisao": "desconhecida"
                                }
                              ],
                              "confianca": 0.92,
                              "warnings": [],
                              "evidencias": ["Situacao: AGUARDANDO ORDEM CRONOLOGICA"]
                            }
                            """
                        }
                    }
                ]
            }

    calls = []

    def fake_post(*args, **kwargs):
        calls.append((args, kwargs))
        return FakeResponse()

    monkeypatch.setattr("src.document_extraction.httpx.post", fake_post)

    result = LlmAssistedDocumentExtractor(api_key="fake-key").extract(
        """
        PRECATORIO N. 0067842-91.2022.8.16.0000
        Documento recebido sem campos estruturados claros.
        """
    )

    assert result.method == "llm_assisted"
    assert result.document.status == StatusPrecatorio.AGUARDANDO_PAGAMENTO
    assert result.document.posicao_fila == 428
    assert result.confidence == 0.92
    assert result.llm_recommended is False
    assert calls[0][0][0] == "https://api.groq.com/openai/v1/chat/completions"
