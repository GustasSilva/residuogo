"""As rotas do web service, de ponta a ponta, com as APIs externas simuladas."""

import httpx
import pytest

from app import config
from tests.conftest import BUENO, COORDENADAS_BUENO, MUNICIPIOS, derrubar_overpass, elemento, responder_overpass


def test_pagina_inicial_e_servida(cliente):
    resposta = cliente.get("/")
    assert resposta.status_code == 200
    assert "ResíduoGO" in resposta.text


def test_arquivos_da_pagina_sao_servidos(cliente):
    assert cliente.get("/app.js").status_code == 200
    assert cliente.get("/estilo.css").status_code == 200


def test_documentacao_da_api_existe(cliente):
    assert cliente.get("/docs").status_code == 200
    documentacao = cliente.get("/openapi.json").json()["paths"]
    assert {"/api/pontos", "/api/pontos.csv", "/api/municipios", "/api/materiais"} <= set(documentacao)
    parametros = {item["name"] for item in documentacao["/api/pontos.csv"]["get"]["parameters"]}
    assert parametros == {"local", "lat", "lon", "raio_km", "material"}


def test_busca_por_cep(cliente, apis_ok):
    resposta = cliente.get("/api/pontos", params={"local": "74230-010"})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["origem"] == {
        "descricao": "Avenida T 15, Setor Bueno, Goiânia - GO",
        "latitude": -16.70,
        "longitude": -49.27,
        "precisao": "endereço",
    }
    assert corpo["raio_km"] == 10
    assert corpo["total"] == len(corpo["pontos"])
    assert corpo["fora_do_raio"] is False


def test_busca_por_municipio(cliente, apis_ok):
    resposta = cliente.get("/api/pontos", params={"local": "Goiânia", "raio_km": 25})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["origem"]["descricao"] == "Goiânia - GO"
    assert corpo["origem"]["precisao"] == "município"
    # Os cinco ecopontos de Goiania ficam dentro de 25 km do centro.
    assert sum(ponto["tipo"] == "Ecoponto" for ponto in corpo["pontos"]) == 5


def test_busca_por_ponto_no_mapa(cliente, apis_ok):
    resposta = cliente.get("/api/pontos", params={"lat": -16.80, "lon": -49.37, "raio_km": 5})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["origem"] == {
        "descricao": "Ponto escolhido no mapa",
        "latitude": -16.80,
        "longitude": -49.37,
        "precisao": "mapa",
    }
    assert corpo["pontos"][0]["nome"] == "Ecoponto Campos Dourados"


def test_csv_da_busca_por_ponto_no_mapa(cliente, apis_ok):
    resposta = cliente.get("/api/pontos.csv", params={"lat": -16.80, "lon": -49.37, "raio_km": 5})
    assert resposta.status_code == 200
    assert "Ecoponto Campos Dourados" in resposta.content.decode("utf-8")


def test_contorno_de_goias(cliente):
    resposta = cliente.get("/api/goias")
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("application/geo+json")
    assert resposta.json()["features"][0]["geometry"]["type"] == "Polygon"


def test_nominatim_nao_recebe_q_junto_com_state(cliente, apis):
    """O servico real responde 400 quando os dois vem juntos."""
    apis.get(config.URL_VIACEP.format(cep="74230010")).respond(json=BUENO)
    responder_overpass(apis, [])
    parametros = []

    def simular(request):
        parametros.append(dict(request.url.params))
        if "q" in request.url.params:
            assert "state" not in request.url.params
            return httpx.Response(200, json=[{"lat": "-16.69", "lon": "-49.27"}])
        return httpx.Response(200, json=[])

    apis.get(config.URL_NOMINATIM).mock(side_effect=simular)
    corpo = cliente.get("/api/pontos", params={"local": "74230010"}).json()
    assert corpo["origem"]["precisao"] == "bairro"
    assert parametros[0]["street"] == "Avenida T 15"
    assert parametros[0]["state"] == "Goiás"


def test_sem_rua_nem_bairro_no_mapa_usa_o_municipio(cliente, apis):
    apis.get(config.URL_VIACEP.format(cep="74230010")).respond(json=BUENO)
    apis.get(config.URL_NOMINATIM).mock(
        side_effect=lambda request: httpx.Response(
            200, json=[{"lat": "-16.68", "lon": "-49.25"}] if "city" in request.url.params and "street" not in request.url.params else []
        )
    )
    responder_overpass(apis, [])
    assert cliente.get("/api/pontos", params={"local": "74230010"}).json()["origem"]["precisao"] == "município"


def test_nominatim_fora_do_ar_usa_o_centro_do_ibge(cliente, apis):
    apis.get(config.URL_VIACEP.format(cep="74230010")).respond(json=BUENO)
    apis.get(config.URL_NOMINATIM).respond(status_code=503)
    apis.get(config.URL_METADADOS_MUNICIPIO.format(codigo="5208707")).respond(
        json=[{"centroide": {"latitude": -16.64, "longitude": -49.27}}]
    )
    responder_overpass(apis, [])
    origem = cliente.get("/api/pontos", params={"local": "74230010"}).json()["origem"]
    assert (origem["latitude"], origem["precisao"]) == (-16.64, "município")


def test_coordenada_fora_de_goias_e_ignorada(cliente, apis):
    apis.get(config.URL_VIACEP.format(cep="74230010")).respond(json=BUENO)
    apis.get(config.URL_NOMINATIM).respond(json=[{"lat": "-23.55", "lon": "-46.63"}])
    apis.get(config.URL_METADADOS_MUNICIPIO.format(codigo="5208707")).respond(
        json=[{"centroide": {"latitude": -16.64, "longitude": -49.27}}]
    )
    responder_overpass(apis, [])
    assert cliente.get("/api/pontos", params={"local": "74230010"}).json()["origem"]["latitude"] == -16.64


@pytest.mark.parametrize(
    ("parametros", "trecho"),
    [
        ({}, "um dos dois"),
        ({"local": "   "}, "um dos dois"),
        ({"local": "74230010", "lat": -16.7, "lon": -49.27}, "um dos dois"),
        ({"lat": -16.7}, "latitude e a longitude"),
        ({"lat": -15.79, "lon": -47.88}, "fora de Goiás"),
        ({"lat": "muito", "lon": -47.88}, "lat"),
        ({"local": "123"}, "8 dígitos"),
        ({"local": "74230010", "raio_km": 0}, "entre 1 e 50"),
        ({"local": "74230010", "raio_km": 51}, "entre 1 e 50"),
        ({"local": "74230010", "raio_km": "muito"}, "raio_km"),
        ({"local": "74230010", "material": "uranio"}, "uranio"),
    ],
)
def test_dados_invalidos_respondem_422(cliente, parametros, trecho):
    resposta = cliente.get("/api/pontos", params=parametros)
    assert resposta.status_code == 422
    assert resposta.headers["content-type"] == "application/problem+json"
    assert trecho in resposta.json()["detail"]


def test_cep_inexistente_responde_404(cliente, apis):
    apis.get(config.URL_VIACEP.format(cep="74999999")).respond(json={"erro": "true"})
    resposta = cliente.get("/api/pontos", params={"local": "74999-999"})
    assert resposta.status_code == 404
    assert resposta.json()["detail"] == "O CEP 74999-999 não foi encontrado."


def test_cep_de_outro_estado_e_recusado(cliente, apis):
    apis.get(config.URL_VIACEP.format(cep="01001000")).respond(json={**BUENO, "uf": "SP"})
    resposta = cliente.get("/api/pontos", params={"local": "01001-000"})
    assert resposta.status_code == 422
    assert "não é de Goiás" in resposta.json()["detail"]


def test_municipio_sem_acento_e_reconhecido(cliente, apis_ok):
    origem = cliente.get("/api/pontos", params={"local": "goiania"}).json()["origem"]
    assert (origem["descricao"], origem["precisao"]) == ("Goiânia - GO", "município")


def test_busca_por_bairro_ou_endereco(cliente, apis):
    apis.get(config.URL_MUNICIPIOS).respond(json=MUNICIPIOS)
    nominatim = apis.get(config.URL_NOMINATIM).respond(json=COORDENADAS_BUENO)
    responder_overpass(apis, [])

    resposta = cliente.get("/api/pontos", params={"local": "Setor Bueno, Goiânia"})
    assert resposta.status_code == 200
    assert resposta.json()["origem"] == {
        "descricao": "Setor Bueno, Goiânia - GO",
        "latitude": -16.70,
        "longitude": -49.27,
        "precisao": "lugar",
    }
    pedido = nominatim.calls[0].request.url.params
    assert pedido["q"] == "Setor Bueno, Goiânia"
    assert (pedido["viewbox"], pedido["bounded"]) == (config.CAIXA_DE_GOIAS, "1")


def test_lugar_fora_de_goias_e_ignorado(cliente, apis):
    apis.get(config.URL_MUNICIPIOS).respond(json=MUNICIPIOS)
    apis.get(config.URL_NOMINATIM).respond(json=[
        {"lat": "-15.81", "lon": "-47.90", "display_name": "Asa Sul, Brasília, Distrito Federal, Brasil"},
        {"lat": "-16.70", "lon": "-49.27", "display_name": "Asa Sul, Goiânia, Goiás, Região Centro-Oeste, Brasil"},
    ])
    responder_overpass(apis, [])
    assert cliente.get("/api/pontos", params={"local": "Asa Sul"}).json()["origem"]["descricao"] == "Asa Sul, Goiânia - GO"


def test_lugar_na_cidade_chamada_goias_mantem_o_nome(cliente, apis):
    apis.get(config.URL_MUNICIPIOS).respond(json=MUNICIPIOS)
    apis.get(config.URL_NOMINATIM).respond(json=[
        {"lat": "-15.93", "lon": "-50.14", "display_name": "Centro, Goiás, Goiás, Região Centro-Oeste, Brasil"},
    ])
    responder_overpass(apis, [])
    assert cliente.get("/api/pontos", params={"local": "Centro"}).json()["origem"]["descricao"] == "Centro, Goiás - GO"


def test_lugar_nao_encontrado_responde_404_e_explica(cliente, apis):
    apis.get(config.URL_MUNICIPIOS).respond(json=MUNICIPIOS)
    apis.get(config.URL_NOMINATIM).respond(json=[])
    resposta = cliente.get("/api/pontos", params={"local": "Lugar que nao existe"})
    assert resposta.status_code == 404
    assert 'Não encontramos "Lugar que nao existe" em Goiás' in resposta.json()["detail"]


def test_sem_ibge_o_nominatim_ainda_acha_o_lugar(cliente, apis):
    apis.get(config.URL_MUNICIPIOS).respond(status_code=503)
    apis.get(config.URL_NOMINATIM).respond(json=COORDENADAS_BUENO)
    responder_overpass(apis, [])
    assert cliente.get("/api/pontos", params={"local": "Setor Bueno"}).status_code == 200


def test_nominatim_fora_do_ar_na_busca_por_lugar_responde_503(cliente, apis):
    apis.get(config.URL_MUNICIPIOS).respond(json=MUNICIPIOS)
    apis.get(config.URL_NOMINATIM).respond(status_code=503)
    resposta = cliente.get("/api/pontos", params={"local": "Setor Bueno"})
    assert resposta.status_code == 503
    assert "Nominatim" in resposta.json()["detail"]


def test_viacep_fora_do_ar_responde_503(cliente, apis):
    apis.get(config.URL_VIACEP.format(cep="74230010")).mock(side_effect=httpx.ConnectTimeout)
    resposta = cliente.get("/api/pontos", params={"local": "74230010"})
    assert resposta.status_code == 503
    assert "ViaCEP" in resposta.json()["detail"]


def test_viacep_fora_do_ar_usa_o_cep_ja_consultado(cliente, apis_ok, monkeypatch):
    assert cliente.get("/api/pontos", params={"local": "74230010"}).status_code == 200

    monkeypatch.setattr(config, "VALIDADE_ENDERECOS", -1)
    apis_ok.get(config.URL_VIACEP.format(cep="74230010")).respond(status_code=500)
    assert cliente.get("/api/pontos", params={"local": "74230010"}).status_code == 200


def test_overpass_fora_do_ar_nao_derruba_a_busca(cliente, apis):
    apis.get(config.URL_VIACEP.format(cep="74230010")).respond(json=BUENO)
    apis.get(config.URL_NOMINATIM).respond(json=[{"lat": "-16.70", "lon": "-49.27"}])
    derrubar_overpass(apis)
    resposta = cliente.get("/api/pontos", params={"local": "74230010", "raio_km": 25})
    corpo = resposta.json()
    assert resposta.status_code == 200
    assert "não respondeu" in corpo["avisos"][0]
    assert sum(ponto["tipo"] == "Ecoponto" for ponto in corpo["pontos"]) >= 5


def test_municipios_em_ordem_alfabetica_com_regiao(cliente, apis_ok):
    corpo = cliente.get("/api/municipios").json()
    assert [municipio["nome"] for municipio in corpo] == ["Abadia de Goiás", "Água Limpa", "Goiânia"]
    assert corpo[1] == {"codigo": "5200100", "nome": "Água Limpa", "regiao": "Itumbiara"}


def test_ibge_com_formato_estranho_responde_503(cliente, apis):
    apis.get(config.URL_MUNICIPIOS).respond(json=[{"id": 1}])
    assert cliente.get("/api/municipios").status_code == 503


def test_materiais(cliente):
    corpo = cliente.get("/api/materiais").json()
    assert {"chave": "papel", "rotulo": "Papel e papelão"} in corpo
    assert len(corpo) == 12


def test_csv_abre_no_excel_com_acentos(cliente, apis_ok):
    responder_overpass(apis_ok, [elemento(-16.70, -49.27, 1, name="=CMD()", **{"recycling:paper": "yes"})])
    resposta = cliente.get("/api/pontos.csv", params={"local": "74230010", "raio_km": 5})
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/csv")
    assert "pontos-de-coleta.csv" in resposta.headers["content-disposition"]

    texto = resposta.content.decode("utf-8")
    assert texto.startswith("﻿Nome;Tipo;Endereço;Materiais")
    # Um nome que parece formula nao pode ser executado pelo Excel.
    assert "'=CMD();Centro de reciclagem;;Papel e papelão;0,0;" in texto


def test_csv_com_erro_responde_no_formato_da_api(cliente):
    resposta = cliente.get("/api/pontos.csv", params={"local": "123"})
    assert resposta.status_code == 422
    assert resposta.headers["content-type"] == "application/problem+json"


def test_rota_inexistente_responde_no_formato_da_api(cliente):
    resposta = cliente.get("/api/nao-existe")
    assert resposta.status_code == 404
    assert resposta.json()["title"] == "Não encontrado"


def test_falha_inesperada_nao_vaza_detalhes(cliente, monkeypatch):
    def quebrar():
        raise RuntimeError("segredo interno")

    monkeypatch.setattr("app.localizacao.municipios", quebrar)
    resposta = cliente.get("/api/municipios")
    assert resposta.status_code == 500
    assert "segredo" not in resposta.text
