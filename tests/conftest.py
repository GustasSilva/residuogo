"""Os testes nao chamam a internet: o respx simula cada API externa."""

from types import SimpleNamespace

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app import config
from app.main import app

BUENO = {
    "cep": "74230-010",
    "logradouro": "Avenida T 15",
    "bairro": "Setor Bueno",
    "localidade": "Goiânia",
    "uf": "GO",
    "ibge": "5208707",
}

MUNICIPIOS = [
    {"id": 5208707, "nome": "Goiânia", "regiao-imediata": {"regiao-intermediaria": {"nome": "Goiânia"}}},
    {"id": 5200050, "nome": "Abadia de Goiás", "regiao-imediata": {"regiao-intermediaria": {"nome": "Goiânia"}}},
    {"id": 5200100, "nome": "Água Limpa", "regiao-imediata": {"regiao-intermediaria": {"nome": "Itumbiara"}}},
]

CONTORNO = {"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Polygon", "coordinates": []}}]}


def lugar(lat=-16.70, lon=-49.27, osm_id=1, nome="", tipo="recycling", estado="BR-GO", categoria="amenity",
          endereco=None, nome_completo="Setor Bueno, Goiânia, Goiás, Região Centro-Oeste, 74215-315, Brasil", **etiquetas):
    """Um resultado do Nominatim pedido com `addressdetails` e `extratags`."""
    return {
        "osm_type": "node",
        "osm_id": osm_id,
        "lat": str(lat),
        "lon": str(lon),
        "category": categoria,
        "type": tipo,
        "name": nome,
        "display_name": nome_completo,
        "address": {"ISO3166-2-lvl4": estado, **(endereco or {})},
        "extratags": etiquetas,
    }


@pytest.fixture(autouse=True)
def ambiente_limpo(tmp_path, monkeypatch):
    """Cada teste comeca com o cache vazio e sem a espera de um segundo do Nominatim."""
    monkeypatch.setattr(config, "ARQUIVO_CACHE", tmp_path / "cache.db")
    monkeypatch.setattr("app.externo.time.sleep", lambda _: None)


@pytest.fixture
def cliente():
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def apis():
    with respx.mock(assert_all_called=False) as simulador:
        yield simulador


@pytest.fixture
def nominatim(apis):
    """Simula o Nominatim. Cada teste troca o que cada tipo de busca devolve.

    - `pontos`: resposta de q=[amenity=recycling]
    - `ecopontos`: resposta de q=ecoponto
    - `enderecos`: resposta das outras buscas (rua, bairro, cidade, texto livre)
    - `estado`: o estado devolvido pela busca reversa (clique no mapa)
    - `fora_do_ar`: quando verdadeiro, toda chamada responde 503
    """
    simulado = SimpleNamespace(
        pontos=[], ecopontos=[], enderecos=[lugar(-16.70, -49.27)], estado="BR-GO", fora_do_ar=False, buscas=[]
    )

    def buscar(request):
        if simulado.fora_do_ar:
            return httpx.Response(503)
        parametros = dict(request.url.params)
        simulado.buscas.append(parametros)
        respostas = {"[amenity=recycling]": simulado.pontos, "ecoponto": simulado.ecopontos}
        return httpx.Response(200, json=respostas.get(parametros.get("q"), simulado.enderecos))

    def reverso(request):
        if simulado.fora_do_ar:
            return httpx.Response(503)
        return httpx.Response(200, json={"address": {"ISO3166-2-lvl4": simulado.estado}})

    apis.get(f"{config.URL_NOMINATIM}/search").mock(side_effect=buscar)
    apis.get(f"{config.URL_NOMINATIM}/reverse").mock(side_effect=reverso)
    return simulado


@pytest.fixture
def apis_ok(apis, nominatim):
    """Todas as APIs externas respondendo normalmente."""
    apis.get(config.URL_MUNICIPIOS).respond(json=MUNICIPIOS)
    apis.get(config.URL_VIACEP.format(cep="74230010")).respond(json=BUENO)
    apis.get(config.URL_CONTORNO_GOIAS).respond(json=CONTORNO)
    return nominatim
