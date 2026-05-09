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


def test_extrai_status_pago_com_data_de_quitacao_por_extenso() -> None:
    text = (DOCUMENTS / "0028934-17.2017.8.16.0000.txt").read_text(encoding="utf-8")

    parsed = parse_document_text(text)
    status_events = [event for event in parsed.eventos if event.tipo == "STATUS_IDENTIFICADO"]

    assert parsed.status == StatusPrecatorio.PAGO
    assert status_events[0].data_evento.isoformat() == "2023-10-03"

