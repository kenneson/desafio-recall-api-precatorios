from __future__ import annotations

from pathlib import Path

import pytest

from src.document_parser import parse_document_text
from src.domain import StatusPrecatorio

ROOT = Path(__file__).resolve().parents[1]
DOCUMENTS = ROOT / "documentos"


@pytest.mark.parametrize(
    ("numero", "status"),
    [
        ("0023456-81.2018.8.16.0000", StatusPrecatorio.AGUARDANDO_PAGAMENTO),
        ("0028934-17.2017.8.16.0000", StatusPrecatorio.PAGO),
        ("0037291-55.2019.8.16.0000", StatusPrecatorio.PAGO),
        ("0041872-33.2020.8.16.0000", StatusPrecatorio.SUSPENSO),
        ("0051203-09.2021.8.16.0000", StatusPrecatorio.SUSPENSO),
    ],
)
def test_classifica_status_dos_documentos(numero: str, status: StatusPrecatorio) -> None:
    text = (DOCUMENTS / f"{numero}.txt").read_text(encoding="utf-8")

    parsed = parse_document_text(text, fallback_numero=numero)

    assert parsed.numero == numero
    assert parsed.status == status
    assert parsed.documento_hash
    assert parsed.eventos


def test_extrai_campos_estruturados_de_documento_com_fila() -> None:
    text = (DOCUMENTS / "0023456-81.2018.8.16.0000.txt").read_text(encoding="utf-8")

    parsed = parse_document_text(text)

    assert parsed.credor == "JOSE CARLOS FERREIRA"
    assert parsed.documento_credor == "045.678.912-33"
    assert parsed.ente_devedor == "MUNICIPIO DE CURITIBA"
    assert parsed.processo_originario == "0004521-19.2011.8.16.0001"
    assert parsed.valor_centavos == 8_745_000
    assert parsed.posicao_fila == 312
    assert parsed.previsao_orcamentaria == 2025
    assert "CPF com digito verificador invalido: 045.678.912-33." in parsed.warnings


def test_valida_cpf_com_digito_verificador() -> None:
    text = """
    PRECATORIO N. 0067842-91.2022.8.16.0000
    Credor: LUIZ FERNANDO MARTINS ROCHA
    CPF: 529.982.247-25
    Situacao: AGUARDANDO ORDEM CRONOLOGICA
    """

    parsed = parse_document_text(text)

    assert parsed.documento_credor == "529.982.247-25"
    assert not any("CPF com digito verificador invalido" in warning for warning in parsed.warnings)


def test_valida_cnpj_com_digito_verificador() -> None:
    text = """
    PRECATORIO N. 0067842-91.2022.8.16.0000
    Credor: EMPRESA TESTE LTDA
    CNPJ: 04.252.011/0001-10
    Situacao: AGUARDANDO ORDEM CRONOLOGICA
    """

    parsed = parse_document_text(text)

    assert parsed.documento_credor == "04.252.011/0001-10"
    assert not any("CNPJ com digito verificador invalido" in warning for warning in parsed.warnings)


def test_extrai_posicao_estimada_na_fila() -> None:
    text = """
    PRECATORIO N. 0067842-91.2022.8.16.0000
    Credor: LUIZ FERNANDO MARTINS ROCHA
    Ente Devedor: MUNICIPIO DE FOZ DO IGUACU
    Situacao: AGUARDANDO ORDEM CRONOLOGICA
    Posicao estimada na fila: 428
    Orcamento previsto: 2026
    """

    parsed = parse_document_text(text)

    assert parsed.status == StatusPrecatorio.AGUARDANDO_PAGAMENTO
    assert parsed.posicao_fila == 428
    assert parsed.previsao_orcamentaria == 2026


def test_usa_fallback_quando_texto_tem_apenas_processo_originario() -> None:
    text = """
    COMUNICACAO ADMINISTRATIVA

    Requisicao cadastrada sob referencia interna RP-2024-8844.
    O presente expediente trata de valor reconhecido judicialmente em favor de
    MARIA APARECIDA GOMES, CPF 222.333.444-55, em face do MUNICIPIO DE PONTA
    GROSSA, decorrente dos autos judiciais n. 0004412-77.2018.8.16.0019.

    A memoria de calculo homologada registra montante requisitado de
    R$ 212.450,30.

    O expediente permanece regular, aguardando programacao orcamentaria e
    posterior posicionamento na lista cronologica de pagamentos do ente devedor.
    """

    parsed = parse_document_text(text, fallback_numero="0088888-44.2024.8.16.0000")

    assert parsed.numero == "0088888-44.2024.8.16.0000"
    assert parsed.processo_originario == "0004412-77.2018.8.16.0019"
    assert parsed.status == StatusPrecatorio.REVISAO_NECESSARIA
    assert parsed.status_motivo.startswith("Status nao explicito")


def test_classifica_negacao_de_cancelamento_como_revisao_necessaria() -> None:
    text = """
    PRECATORIO N. 0088888-44.2024.8.16.0000
    Certifico que nao ha comprovante de deposito integral, baixa definitiva
    ou decisao de cancelamento. O expediente permanece regular, aguardando
    programacao orcamentaria.
    """

    parsed = parse_document_text(text)

    assert parsed.status == StatusPrecatorio.REVISAO_NECESSARIA
    assert "ambiguidade" in parsed.status_motivo


def test_classifica_perda_de_efeito_indireta_como_revisao_necessaria() -> None:
    text = """
    PRECATORIO N. 0099999-12.2024.8.16.0000
    Em revisao administrativa posterior, constatou-se duplicidade material.
    Em razao disso, a Presidencia determinou a perda de efeito da presente
    requisicao, com retirada do expediente da relacao de pagamentos pendentes.
    Fica certificado que nao subsiste obrigacao de pagamento por meio deste
    expediente especifico.
    """

    parsed = parse_document_text(text)

    assert parsed.status == StatusPrecatorio.REVISAO_NECESSARIA


def test_extrai_status_pago_com_data_de_quitacao_por_extenso() -> None:
    text = (DOCUMENTS / "0028934-17.2017.8.16.0000.txt").read_text(encoding="utf-8")

    parsed = parse_document_text(text)
    status_events = [event for event in parsed.eventos if event.tipo == "STATUS_IDENTIFICADO"]

    assert parsed.status == StatusPrecatorio.PAGO
    assert status_events[0].data_evento.isoformat() == "2023-10-03"


def test_ignora_data_invalida_de_ocr_sem_quebrar_parser() -> None:
    text = """
    PRECATORIO N. 0067842-91.2022.8.16.0000
    Oficio requisitorio expedido em: 31/02/2020
    Situacao: AGUARDANDO ORDEM CRONOLOGICA
    """

    parsed = parse_document_text(text)

    assert parsed.numero == "0067842-91.2022.8.16.0000"
    assert parsed.status == StatusPrecatorio.AGUARDANDO_PAGAMENTO
    assert "Data invalida ignorada no OCR: 31/02/2020." in parsed.warnings
