"""Os testes nao chamam a internet: o respx simula cada API externa."""

import math

import pytest
import respx
from fastapi.testclient import TestClient

from app import config, pontos
from app.main import app

BUENO = {
    "cep": "74230-010",
    "logradouro": "Avenida T 15",
    "bairro": "Setor Bueno",
    "localidade": "Goiânia",
    "uf": "GO",
    "ibge": "5208707",
}
COORDENADAS_BUENO = [{"lat": "-16.70", "lon": "-49.27"}]

MUNICIPIOS = [
    {"id": 5208707, "nome": "Goiânia", "regiao-imediata": {"regiao-intermediaria": {"nome": "Goiânia"}}},
    {"id": 5200050, "nome": "Abadia de Goiás", "regiao-imediata": {"regiao-intermediaria": {"nome": "Goiânia"}}},
    {"id": 5200100, "nome": "Água Limpa", "regiao-imediata": {"regiao-intermediaria": {"nome": "Itumbiara"}}},
]


def elemento(lat=-16.70, lon=-49.27, identificador=1, **etiquetas):
    etiquetas.setdefault("amenity", "recycling")
    return {"type": "node", "id": identificador, "lat": lat, "lon": lon, "tags": etiquetas}


@pytest.fixture(autouse=True)
def ambiente_limpo(tmp_path, monkeypatch):
    """Cada teste comeca com o cache vazio e sem lembrar de falhas do Overpass."""
    monkeypatch.setattr(config, "ARQUIVO_CACHE", tmp_path / "cache.db")
    monkeypatch.setattr(config, "TEMPO_LIMITE_OVERPASS", 1)
    monkeypatch.setattr(pontos, "_ultima_falha_overpass", -math.inf)
    monkeypatch.setattr("app.localizacao._ultima_chamada_nominatim", -math.inf)


@pytest.fixture
def cliente():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def apis():
    with respx.mock(assert_all_called=False) as simulador:
        yield simulador


@pytest.fixture
def apis_ok(apis):
    """Todas as APIs externas respondendo normalmente."""
    apis.get(config.URL_MUNICIPIOS).respond(json=MUNICIPIOS)
    apis.get(config.URL_VIACEP.format(cep="74230010")).respond(json=BUENO)
    apis.get(config.URL_NOMINATIM).respond(json=COORDENADAS_BUENO)
    for servidor in config.SERVIDORES_OVERPASS:
        apis.post(servidor).respond(json={"elements": []})
    return apis


def responder_overpass(apis, elementos):
    for servidor in config.SERVIDORES_OVERPASS:
        apis.post(servidor).respond(json={"elements": elementos})


def derrubar_overpass(apis):
    for servidor in config.SERVIDORES_OVERPASS:
        apis.post(servidor).respond(status_code=504)
