from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src import models  # noqa: F401
from src.database import Base
from src.models import ColetaPrecatorio
from src.rpa import choose_debtor_option, extract_precatorio_numbers, extract_precatorio_numbers_from_tables
from src.services import persist_collected_numbers


def test_extrai_cnjs_da_coluna_autos_do_precatorio() -> None:
    tables = [
        {
            "headers": ["Ord.", "Oficio Precatorio", "Autos do Precatorio"],
            "rows": [
                ["1", "2024/906061", "0023456-81.2018.8.16.0000"],
                ["2", "2024/913435", "0041872-33.2020.8.16.0000"],
                ["3", "2024/906061", "0023456-81.2018.8.16.0000"],
            ],
        }
    ]

    numbers = extract_precatorio_numbers_from_tables(tables)

    assert numbers == ["0023456-81.2018.8.16.0000", "0041872-33.2020.8.16.0000"]


def test_extrai_oficio_precatorio_quando_disponivel() -> None:
    text = "Oficio Precatorio 2024/906061 e 2024/913435"

    numbers = extract_precatorio_numbers(text)

    assert numbers == ["2024/906061", "2024/913435"]


def test_usa_oficio_quando_autos_do_precatorio_vem_mascarado() -> None:
    tables = [
        {
            "headers": ["Ord.", "Oficio Precatorio", "Autos do Precatorio"],
            "rows": [
                ["1", "2024/906061", "000xxxx-95.xxxx.8.16.7000"],
                ["2", "2024/913435", "001xxxx-04.xxxx.8.16.7000"],
            ],
        }
    ]

    numbers = extract_precatorio_numbers_from_tables(tables)

    assert numbers == ["2024/906061", "2024/913435"]


def test_persiste_numeros_coletados_no_formato_cnj(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        persist_collected_numbers(["0023456-81.2018.8.16.0000", "0041872-33.2020.8.16.0000"], db)
        rows = db.execute(select(ColetaPrecatorio).order_by(ColetaPrecatorio.ordem)).scalars().all()

    assert [row.numero for row in rows] == ["0023456-81.2018.8.16.0000", "0041872-33.2020.8.16.0000"]
    assert [row.ordem for row in rows] == [1, 2]


def test_persiste_oficio_precatorio_quando_cnj_publico_vem_mascarado(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as db:
        persist_collected_numbers(["2024/906061"], db)
        rows = db.execute(select(ColetaPrecatorio).order_by(ColetaPrecatorio.ordem)).scalars().all()

    assert [row.numero for row in rows] == ["2024/906061"]


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
