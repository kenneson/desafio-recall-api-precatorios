from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src import models  # noqa: F401
from src.database import Base, get_db
from src.main import app


@pytest.fixture()
def client(tmp_path) -> Generator[TestClient, None, None]:
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_processa_precatorio_e_consulta_timeline(client: TestClient) -> None:
    response = client.post("/precatorios/0023456-81.2018.8.16.0000/processar")

    assert response.status_code == 200
    body = response.json()
    assert body["precatorio"]["status"] == "AGUARDANDO_PAGAMENTO"
    assert body["tarefa"]["acao"] == "MONITORAR_PAGAMENTO"
    assert body["eventos_criados"] >= 2

    timeline = client.get("/precatorios/0023456-81.2018.8.16.0000/timeline")

    assert timeline.status_code == 200
    tipos = [event["tipo"] for event in timeline.json()]
    assert "OFICIO_REQUISITORIO" in tipos
    assert "PROCESSAMENTO_SISTEMA" in tipos


def test_fila_ordena_por_prioridade_e_chegada(client: TestClient) -> None:
    client.post("/precatorios/0023456-81.2018.8.16.0000/processar")
    client.post("/precatorios/0041872-33.2020.8.16.0000/processar")

    response = client.get("/fila")

    assert response.status_code == 200
    fila = response.json()
    assert [task["prioridade"] for task in fila] == [1, 2]
    assert fila[0]["precatorio_numero"] == "0041872-33.2020.8.16.0000"


def test_permite_evento_manual_na_timeline(client: TestClient) -> None:
    payload = {
        "tipo": "ATUALIZACAO_MANUAL",
        "titulo": "Contato com cartorio",
        "descricao": "Cartorio informou previsao de nova certidao.",
        "data_evento": "2026-05-09",
        "precisao": "dia",
    }

    response = client.post("/precatorios/0051203-09.2021.8.16.0000/eventos", json=payload)

    assert response.status_code == 201
    assert response.json()["origem"] == "api"

