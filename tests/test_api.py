from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import src.services as services
import src.routers.rpa as rpa_router
from src import models  # noqa: F401
from src.database import Base, get_db
from src.main import app
from src.rpa import RpaNoCollectableNumbers


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

    assert response.status_code == 201
    body = response.json()
    assert body["precatorio"]["status"] == "AGUARDANDO_PAGAMENTO"
    assert body["precatorio"]["extraction_method"] == "rule_based"
    assert body["precatorio"]["llm_recommended"] is False
    assert body["precatorio"]["extraction_confidence"] >= 0.8
    assert body["tarefa"]["acao"] == "MONITORAR_PAGAMENTO"
    assert body["eventos_criados"] >= 2

    timeline = client.get("/precatorios/0023456-81.2018.8.16.0000/timeline")

    assert timeline.status_code == 200
    tipos = [event["tipo"] for event in timeline.json()]
    assert "OFICIO_REQUISITORIO" in tipos
    assert "PROCESSAMENTO_SISTEMA" in tipos


def test_raiz_redireciona_para_docs(client: TestClient) -> None:
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/docs"


def test_rpa_coleta_oficio_com_aviso_quando_cnj_esta_mascarado(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(rpa_router, "coletar_precatorios_tjpr", lambda ente, timeout: ["2024/906061"])

    response = client.post("/rpa/coletar", json={"ente_devedor": "CURITIBA", "timeout_segundos": 30})

    assert response.status_code == 200
    body = response.json()
    assert body["numeros"] == ["2024/906061"]
    assert body["avisos"]


def test_rpa_registra_evento_de_coleta_na_timeline_para_cnj(client: TestClient, monkeypatch) -> None:
    numero = "0023456-81.2018.8.16.0000"
    monkeypatch.setattr(rpa_router, "coletar_precatorios_tjpr", lambda ente, timeout: [numero])

    response = client.post("/rpa/coletar", json={"ente_devedor": "CURITIBA", "timeout_segundos": 30})

    assert response.status_code == 200
    timeline = client.get(f"/precatorios/{numero}/timeline")
    assert timeline.status_code == 200
    eventos = timeline.json()
    assert eventos[0]["tipo"] == "COLETA_RPA"
    assert eventos[0]["origem"] == "rpa"
    assert "posicao 1" in eventos[0]["descricao"]
    assert "CURITIBA" in eventos[0]["descricao"]


def test_rpa_retorna_422_quando_tabela_nao_tem_identificador_coletavel(client: TestClient, monkeypatch) -> None:
    def fail(_ente, _timeout):
        raise RpaNoCollectableNumbers("Tabela carregada, mas nenhum identificador foi encontrado.")

    monkeypatch.setattr(rpa_router, "coletar_precatorios_tjpr", fail)

    response = client.post("/rpa/coletar", json={"ente_devedor": "CURITIBA", "timeout_segundos": 30})

    assert response.status_code == 422


def test_fila_ordena_por_prioridade_e_chegada(client: TestClient) -> None:
    client.post("/precatorios/0023456-81.2018.8.16.0000/processar")
    client.post("/precatorios/0041872-33.2020.8.16.0000/processar")

    response = client.get("/fila")

    assert response.status_code == 200
    fila = response.json()
    assert [task["prioridade"] for task in fila] == [2, 3]
    assert fila[0]["precatorio_numero"] == "0041872-33.2020.8.16.0000"


def test_cria_tarefa_manual_na_fila_com_status_201(client: TestClient) -> None:
    payload = {
        "precatorio_numero": "0023456-81.2018.8.16.0000",
        "acao": "MONITORAR_PAGAMENTO",
        "prioridade": 3,
        "motivo": "Monitoramento manual solicitado.",
    }

    response = client.post("/fila", json=payload)

    assert response.status_code == 201
    assert response.json()["acao"] == "MONITORAR_PAGAMENTO"


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


def test_marca_recomendacao_de_ia_quando_extracao_tem_baixa_confianca(client: TestClient, tmp_path, monkeypatch) -> None:
    numero = "0067842-91.2022.8.16.0000"
    document_path = tmp_path / f"{numero}.txt"
    document_path.write_text(
        """
        PRECATORIO N. 0067842-91.2022.8.16.0000
        Documento recebido sem campos estruturados claros.
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(services, "DOCUMENTS_DIR", tmp_path)

    response = client.post(f"/precatorios/{numero}/processar")

    assert response.status_code == 201
    precatorio = response.json()["precatorio"]
    assert precatorio["llm_recommended"] is True
    assert precatorio["extraction_confidence"] < 0.75
    assert precatorio["status"] == "REVISAO_NECESSARIA"
    assert response.json()["tarefa"]["acao"] == "REVISAR_CLASSIFICACAO"
    assert response.json()["tarefa"]["prioridade"] == 1
    assert "Status nao explicito; enviado para revisao por fallback conservador." in precatorio["extraction_warnings"]


def test_documento_ambiguo_vai_para_revisao_e_recomenda_ia(client: TestClient, tmp_path, monkeypatch) -> None:
    numero = "0088888-44.2024.8.16.0000"
    document_path = tmp_path / f"{numero}.txt"
    document_path.write_text(
        """
        PRECATORIO N. 0088888-44.2024.8.16.0000
        Credor: MARIA APARECIDA GOMES
        Ente Devedor: MUNICIPIO DE PONTA GROSSA
        Valor inscrito: R$ 212.450,30
        Certifico que nao ha comprovante de deposito integral, baixa definitiva
        ou decisao de cancelamento. O expediente permanece regular.
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(services, "DOCUMENTS_DIR", tmp_path)

    response = client.post(f"/precatorios/{numero}/processar")

    assert response.status_code == 201
    body = response.json()
    assert body["precatorio"]["status"] == "REVISAO_NECESSARIA"
    assert body["precatorio"]["llm_recommended"] is True
    assert body["tarefa"]["acao"] == "REVISAR_CLASSIFICACAO"
    assert body["tarefa"]["prioridade"] == 1


def test_perda_de_efeito_vai_para_revisao_e_nao_para_monitoramento(client: TestClient, tmp_path, monkeypatch) -> None:
    numero = "0099999-12.2024.8.16.0000"
    document_path = tmp_path / f"{numero}.txt"
    document_path.write_text(
        """
        PRECATORIO N. 0099999-12.2024.8.16.0000
        Credor: ROBERTO ALMEIDA COSTA
        Ente Devedor: MUNICIPIO DE GUARAPUAVA
        Valor inscrito: R$ 76.900,00
        A Presidencia determinou a perda de efeito da presente requisicao,
        com retirada do expediente da relacao de pagamentos pendentes.
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(services, "DOCUMENTS_DIR", tmp_path)

    response = client.post(f"/precatorios/{numero}/processar")

    assert response.status_code == 201
    body = response.json()
    assert body["precatorio"]["status"] == "REVISAO_NECESSARIA"
    assert body["precatorio"]["llm_recommended"] is True
    assert body["tarefa"]["acao"] == "REVISAR_CLASSIFICACAO"
