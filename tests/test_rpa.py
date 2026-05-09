from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src import models  # noqa: F401
from src.database import Base
from src.models import ColetaPrecatorio
from src.rpa import choose_debtor_option, extract_precatorio_numbers
from src.services import persist_collected_numbers


def test_extrai_oficios_precatorios_da_tabela_do_tjpr() -> None:
    text = """
    Oficio Precatorio
    2024/906061
    2024/913435
    2024/906061
    Autos do Precatorio 001xxxx-04.xxxx.8.16.7000
    """

    numbers = extract_precatorio_numbers(text)

    assert numbers == ["2024/906061", "2024/913435"]


def test_persiste_numeros_coletados_no_formato_oficio_precatorio(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        persist_collected_numbers(["2024/906061", "2024/913435"], db)
        rows = db.execute(select(ColetaPrecatorio).order_by(ColetaPrecatorio.ordem)).scalars().all()

    assert [row.numero for row in rows] == ["2024/906061", "2024/913435"]
    assert [row.ordem for row in rows] == [1, 2]


def test_escolhe_orgao_devedor_por_texto_parcial() -> None:
    options = [
        {"label": "Selecione o Orgao Devedor para pesquisar os Precatorios...", "value": ""},
        {"label": "CORBELIA - Regime geral (Art. 100 CF)", "value": "123"},
        {"label": "CURITIBA - Regime geral (Art. 100 CF)", "value": "456"},
    ]

    selected = choose_debtor_option(options, "CURITIBA")

    assert selected == {"label": "CURITIBA - Regime geral (Art. 100 CF)", "value": "456"}


def test_escolhe_orgao_devedor_ignorando_acentos() -> None:
    options = [
        {"label": "ESTADO DO PARANA - Regime geral (Art. 100 CF)", "value": "789"},
    ]

    selected = choose_debtor_option(options, "Estado do Paraná")

    assert selected == {"label": "ESTADO DO PARANA - Regime geral (Art. 100 CF)", "value": "789"}
