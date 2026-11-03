"""As rotas do web service, de ponta a ponta, com as APIs externas simuladas."""

import httpx
import pytest

from app import config
from tests.conftest import BUENO, MUNICIPIOS, lugar


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
    assert {"/api/pontos", "/api/pontos.csv", "/api/municipios", "/api/materiais", "/api/goias"} <= set(documentacao)
    parametros = {item["name"] for item in documentacao["/api/pontos.csv"]["get"]["parameters"]}
    assert parametros == {"local", "lat", "lon", "raio_km", "material"}


# --- Busca por CEP, municipio, lugar e mapa ---


def test_busca_por_cep(cliente, apis_ok):
    apis_ok.pontos = [lugar(-16.71, -49.27, 1, nome="Cooperativa")]
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
    assert [ponto["nome"] for ponto in corpo["pontos"]] == ["Cooperativa"]
    assert corpo["total"] == 1
    assert corpo["fora_do_raio"] is False


def test_busca_por_municipio(cliente, apis_ok):
    corpo = cliente.get("/api/pontos", params={"local": "Goiânia"}).json()
    assert corpo["origem"]["descricao"] == "Goiânia - GO"
    assert corpo["origem"]["precisao"] == "município"
    assert {"city": "Goiânia", "state": "Goiás"}.items() <= apis_ok.buscas[0].items()


def test_municipio_sem_acento_e_reconhecido(cliente, apis_ok):
    origem = cliente.get("/api/pontos", params={"local": "goiania"}).json()["origem"]
    assert (origem["descricao"], origem["precisao"]) == ("Goiânia - GO", "município")


def test_busca_por_bairro_ou_endereco(cliente, apis_ok):
    resposta = cliente.get("/api/pontos", params={"local": "Setor Bueno, Goiânia"})
    assert resposta.status_code == 200
    assert resposta.json()["origem"] == {
        "descricao": "Setor Bueno, Goiânia - GO",
        "latitude": -16.70,
        "longitude": -49.27,
        "precisao": "lugar",
    }
    pedido = apis_ok.buscas[0]
    assert pedido["q"] == "Setor Bueno, Goiânia"
    assert (pedido["viewbox"], pedido["bounded"]) == (config.CAIXA_DE_GOIAS, "1")


def test_lugar_fora_de_goias_e_ignorado(cliente, apis_ok):
    apis_ok.enderecos = [
        lugar(-15.81, -47.90, estado="BR-DF", nome_completo="Asa Sul, Brasília, Distrito Federal, Brasil"),
        lugar(-16.70, -49.27, nome_completo="Asa Sul, Goiânia, Goiás, Região Centro-Oeste, Brasil"),
    ]
    assert cliente.get("/api/pontos", params={"local": "Asa Sul"}).json()["origem"]["descricao"] == "Asa Sul, Goiânia - GO"


def test_lugar_na_cidade_chamada_goias_mantem_o_nome(cliente, apis_ok):
    apis_ok.enderecos = [lugar(-15.93, -50.14, nome_completo="Centro, Goiás, Goiás, Região Centro-Oeste, Brasil")]
    assert cliente.get("/api/pontos", params={"local": "Centro"}).json()["origem"]["descricao"] == "Centro, Goiás - GO"


def test_lugar_nao_encontrado_responde_404_e_explica(cliente, apis_ok):
    apis_ok.enderecos = []
    resposta = cliente.get("/api/pontos", params={"local": "Lugar que nao existe"})
    assert resposta.status_code == 404
    assert 'Não encontramos "Lugar que nao existe" em Goiás' in resposta.json()["detail"]


def test_busca_por_ponto_no_mapa(cliente, apis_ok):
    resposta = cliente.get("/api/pontos", params={"lat": -16.80, "lon": -49.37, "raio_km": 5})
    assert resposta.status_code == 200
    assert resposta.json()["origem"] == {
        "descricao": "Ponto escolhido no mapa",
        "latitude": -16.80,
        "longitude": -49.37,
        "precisao": "mapa",
    }


def test_clique_em_outro_estado_e_recusado(cliente, apis_ok):
    apis_ok.estado = "BR-DF"
    resposta = cliente.get("/api/pontos", params={"lat": -15.79, "lon": -47.88})
    assert resposta.status_code == 422
    assert "fora de Goiás" in resposta.json()["detail"]


# --- CEP: da rua ate a cidade ---


def test_nominatim_nao_recebe_q_junto_com_state(cliente, apis_ok):
    """O servico real responde 400 quando os dois vem juntos. Sem a rua no mapa, tenta o bairro."""
    apis_ok.enderecos = []
    cliente.get("/api/pontos", params={"local": "74230010"})
    rua, bairro = apis_ok.buscas[0], apis_ok.buscas[1]
    assert (rua["street"], rua["state"]) == ("Avenida T 15", "Goiás")
    assert bairro["q"] == "Setor Bueno, Goiânia, Goiás" and "state" not in bairro


def test_rua_fora_de_goias_passa_para_o_bairro(cliente, apis):
    apis.get(config.URL_VIACEP.format(cep="74230010")).respond(json=BUENO)

    def responder(request):
        parametros = request.url.params
        if "street" in parametros:
            return httpx.Response(200, json=[lugar(-23.55, -46.63, estado="BR-SP")])
        if parametros.get("q", "").startswith("Setor Bueno"):
            return httpx.Response(200, json=[lugar(-16.71, -49.26)])
        return httpx.Response(200, json=[])

    apis.get(f"{config.URL_NOMINATIM}/search").mock(side_effect=responder)
    origem = cliente.get("/api/pontos", params={"local": "74230010"}).json()["origem"]
    assert (origem["latitude"], origem["precisao"]) == (-16.71, "bairro")


def test_cep_que_o_mapa_nao_acha_responde_404(cliente, apis_ok):
    apis_ok.enderecos = []
    resposta = cliente.get("/api/pontos", params={"local": "74230010"})
    assert resposta.status_code == 404
    assert "Avenida T 15, Setor Bueno, Goiânia - GO" in resposta.json()["detail"]


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


# --- Validacao ---


@pytest.mark.parametrize(
    ("parametros", "trecho"),
    [
        ({}, "um dos dois"),
        ({"local": "   "}, "um dos dois"),
        ({"local": "74230010", "lat": -16.7, "lon": -49.27}, "um dos dois"),
        ({"lat": -16.7}, "latitude e a longitude"),
        ({"lat": -10.20, "lon": -48.33}, "fora de Goiás"),
        ({"lat": "nan", "lon": "nan"}, "fora de Goiás"),
        ({"lat": "muito", "lon": -47.88}, "lat"),
        ({"local": "123"}, "8 dígitos"),
        ({"local": "74230010", "raio_km": 0}, "entre 1 e 50"),
        ({"local": "74230010", "raio_km": 51}, "entre 1 e 50"),
        ({"local": "74230010", "raio_km": "muito"}, "raio_km"),
        ({"local": "74230010", "material": "uranio"}, "uranio"),
    ],
)
def test_dados_invalidos_respondem_422_sem_chamar_as_apis(cliente, apis, parametros, trecho):
    resposta = cliente.get("/api/pontos", params=parametros)
    assert resposta.status_code == 422
    assert resposta.headers["content-type"] == "application/problem+json"
    assert trecho in resposta.json()["detail"]
    assert apis.calls.call_count == 0


# --- APIs fora do ar ---


def test_sem_ibge_o_nominatim_ainda_acha_o_lugar(cliente, apis, nominatim):
    apis.get(config.URL_MUNICIPIOS).respond(status_code=503)
    assert cliente.get("/api/pontos", params={"local": "Setor Bueno"}).status_code == 200


def test_nominatim_fora_do_ar_responde_503(cliente, apis):
    apis.get(config.URL_MUNICIPIOS).respond(json=MUNICIPIOS)
    apis.get(f"{config.URL_NOMINATIM}/search").respond(status_code=503)
    resposta = cliente.get("/api/pontos", params={"local": "Setor Bueno"})
    assert resposta.status_code == 503
    assert "Nominatim" in resposta.json()["detail"]


def test_viacep_fora_do_ar_responde_503(cliente, apis):
    apis.get(config.URL_VIACEP.format(cep="74230010")).mock(side_effect=httpx.ConnectTimeout)
    resposta = cliente.get("/api/pontos", params={"local": "74230010"})
    assert resposta.status_code == 503
    assert "ViaCEP" in resposta.json()["detail"]


def test_api_fora_do_ar_usa_o_que_ja_foi_consultado(cliente, apis_ok, apis, monkeypatch):
    assert cliente.get("/api/pontos", params={"local": "74230010"}).status_code == 200

    # Tudo vencido e tudo fora do ar: as respostas guardadas no cache seguram a busca.
    monkeypatch.setattr(config, "VALIDADE_ENDERECOS", -1)
    monkeypatch.setattr(config, "VALIDADE_PONTOS", -1)
    viacep = apis.get(config.URL_VIACEP.format(cep="74230010")).respond(status_code=500)
    apis_ok.fora_do_ar = True
    assert cliente.get("/api/pontos", params={"local": "74230010"}).status_code == 200
    assert viacep.calls.last.response.status_code == 500  # a API foi chamada e falhou de verdade


# --- Outras rotas ---


def test_municipios_em_ordem_alfabetica_com_regiao(cliente, apis_ok):
    corpo = cliente.get("/api/municipios").json()
    assert [municipio["nome"] for municipio in corpo] == ["Abadia de Goiás", "Água Limpa", "Goiânia"]
    assert corpo[1] == {"codigo": "5200100", "nome": "Água Limpa", "regiao": "Itumbiara"}


def test_ibge_com_formato_estranho_responde_503(cliente, apis):
    apis.get(config.URL_MUNICIPIOS).respond(json=[{"id": 1}])
    assert cliente.get("/api/municipios").status_code == 503


def test_contorno_de_goias_vem_do_ibge(cliente, apis_ok, apis):
    resposta = cliente.get("/api/goias")
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("application/geo+json")
    assert resposta.json()["features"][0]["geometry"]["type"] == "Polygon"
    pedido = next(chamada.request for chamada in apis.calls if chamada.request.url.path.endswith("/estados/52"))
    assert pedido.url.params["formato"] == "application/vnd.geo+json"


def test_materiais(cliente):
    corpo = cliente.get("/api/materiais").json()
    assert {"chave": "papel", "rotulo": "Papel e papelão"} in corpo
    assert len(corpo) == 12


def test_csv_abre_no_excel_com_acentos(cliente, apis_ok):
    apis_ok.pontos = [lugar(-16.70, -49.27, 1, nome="=CMD()", **{"recycling:paper": "yes"})]
    resposta = cliente.get("/api/pontos.csv", params={"local": "74230010", "raio_km": 5})
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/csv")
    assert "pontos-de-coleta.csv" in resposta.headers["content-disposition"]

    texto = resposta.content.decode("utf-8")
    assert texto.startswith("﻿Nome;Tipo;Endereço;Materiais;Distância (km);Latitude;Longitude")
    # Um nome que parece formula nao pode ser executado pelo Excel, e os decimais usam virgula.
    assert "'=CMD();Centro de reciclagem;;Papel e papelão;0,0;-16,7;-49,27" in texto


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

    monkeypatch.setattr("app.servicos.localizacao.municipios", quebrar)
    resposta = cliente.get("/api/municipios")
    assert resposta.status_code == 500
    assert "segredo" not in resposta.text
