"""Conversao dos dados do OpenStreetMap, distancia e filtro de material."""

import pytest

from app import config
from app.pontos import _remover_duplicatas, buscar, distancia_km, ponto_do_elemento
from tests.conftest import derrubar_overpass, elemento, responder_overpass


def test_distancia_entre_goiania_e_anapolis():
    assert distancia_km(-16.6869, -49.2648, -16.3281, -48.9534) == pytest.approx(52, abs=2)


def test_materiais_vem_das_etiquetas():
    ponto = ponto_do_elemento(elemento(**{"name": "Cooperativa", "recycling:paper": "yes", "recycling:cans": "yes"}))
    assert ponto["materiais"] == ["papel", "metal"]


def test_ponto_sem_etiqueta_de_material_fica_sem_materiais():
    assert ponto_do_elemento(elemento(name="Cooperativa"))["materiais"] == []


@pytest.mark.parametrize(
    "nome",
    ["inpEV Mineiros", "ADIAGO - Piracanjuba", "Associação de Defensivos Agrícolas", "Associação dos Revendedores de Agrotóxicos"],
)
def test_central_de_agrotoxicos_e_reconhecida_pelo_nome(nome):
    ponto = ponto_do_elemento(elemento(name=nome, recycling_type="centre"))
    assert ponto["materiais"] == ["agrotoxicos"]
    assert ponto["tipo"] == "Central de embalagens de agrotóxicos"


@pytest.mark.parametrize(
    "etiquetas",
    [
        {"name": "ATERRO SANITÁRIO", "amenity": "waste_transfer_station"},
        {"name": "Lixão de Goiandira"},
        {"amenity": "waste_transfer_station"},
        {"name": "Usina Coruripe", "amenity": "waste_transfer_station"},
        {"name": "Centro privado", "access": "private"},
    ],
)
def test_lugares_que_nao_recebem_entrega_ficam_de_fora(etiquetas):
    assert ponto_do_elemento(elemento(**etiquetas)) is None


def test_estacao_com_nome_de_ecoponto_e_ecoponto():
    ponto = ponto_do_elemento(elemento(name="Ecoponto Vila Nova", amenity="waste_transfer_station"))
    assert ponto["tipo"] == "Ecoponto"


def test_ponto_sem_nome_usa_o_tipo():
    ponto = ponto_do_elemento(elemento(recycling_type="container"))
    assert ponto["nome"] == "Contêiner de coleta (sem nome no mapa)"


def test_area_do_mapa_usa_o_centro():
    area = {"type": "way", "id": 1, "center": {"lat": -16.7, "lon": -49.2}, "tags": {"amenity": "recycling"}}
    assert ponto_do_elemento(area)["latitude"] == -16.7


def test_endereco_e_montado_das_etiquetas():
    ponto = ponto_do_elemento(elemento(**{"addr:street": "Rua 10", "addr:housenumber": "5", "addr:city": "Goiânia"}))
    assert ponto["endereco"] == "Rua 10, 5, Goiânia"


def test_mesmo_lugar_repetido_aparece_uma_vez():
    primeiro = {"nome": "Ecoponto São José", "latitude": -16.7, "longitude": -49.3}
    repetido = {"nome": "ECOPONTO SAO JOSE", "latitude": -16.7001, "longitude": -49.3001}
    sem_nome = {"nome": "Centro de reciclagem (sem nome no mapa)", "latitude": -16.7002, "longitude": -49.3}
    outro_vizinho = {"nome": "Sucataria do João", "latitude": -16.7001, "longitude": -49.3}
    assert _remover_duplicatas([primeiro, repetido, sem_nome, outro_vizinho]) == [primeiro, outro_vizinho]


def test_resultado_vem_do_mais_perto_para_o_mais_longe(apis):
    # Longe da lista de ecopontos, para o teste enxergar so o que o Overpass devolveu.
    responder_overpass(apis, [
        elemento(-17.80, -50.95, 1, name="Mais longe"),
        elemento(-17.791, -50.92, 2, name="Mais perto"),
        elemento(-18.50, -50.92, 3, name="Fora do raio"),
    ])
    encontrados, avisos = buscar(-17.79, -50.92, 10, None)
    assert [ponto["nome"] for ponto in encontrados] == ["Mais perto", "Mais longe"]
    assert avisos == []


def test_filtro_mantem_quem_aceita_e_quem_nao_informa(apis):
    responder_overpass(apis, [
        elemento(-17.79, -50.92, 1, **{"name": "Aceita papel", "recycling:paper": "yes"}),
        elemento(-17.79, -50.93, 2, **{"name": "Só vidro", "recycling:glass": "yes"}),
        elemento(-17.79, -50.94, 3, name="Não informa"),
        elemento(-17.79, -50.95, 4, name="inpEV Rio Verde"),
    ])
    encontrados, _ = buscar(-17.79, -50.92, 10, "papel")
    assert [ponto["nome"] for ponto in encontrados] == ["Aceita papel", "Não informa"]


def test_ecopontos_da_lista_aparecem_com_os_materiais(apis):
    responder_overpass(apis, [])
    encontrados, _ = buscar(-16.80, -49.37, 5, "pneus")
    campos_dourados = encontrados[0]
    assert campos_dourados["nome"] == "Ecoponto Campos Dourados"
    assert {"chave": "pneus", "rotulo": "Pneus"} in campos_dourados["materiais"]


def test_ecoponto_da_lista_tem_preferencia_sobre_o_do_mapa(apis):
    responder_overpass(apis, [elemento(-16.80056, -49.36891, 1, name="Ecoponto Campos Dourados", amenity="waste_transfer_station")])
    encontrados, _ = buscar(-16.80, -49.37, 2, None)
    assert [ponto["fonte"] for ponto in encontrados] == ["Prefeitura de Goiânia e imprensa"]


def test_consulta_repetida_nao_chama_o_overpass_de_novo(apis):
    responder_overpass(apis, [])
    buscar(-17.79, -50.92, 10, None)
    chamadas = apis.calls.call_count
    buscar(-17.79, -50.92, 10, "papel")
    assert apis.calls.call_count == chamadas


def test_overpass_fora_do_ar_usa_a_copia_de_reserva(apis, monkeypatch):
    derrubar_overpass(apis)
    copia = {"gerado_em": "2026-11-02", "elementos": [elemento(-17.79, -50.92, 1, name="Da cópia")]}
    monkeypatch.setattr("app.pontos._copia_de_reserva", lambda: copia)
    encontrados, avisos = buscar(-17.79, -50.92, 10, None)
    assert [ponto["nome"] for ponto in encontrados] == ["Da cópia"]
    assert avisos == ["O OpenStreetMap não respondeu. Estes pontos são da cópia de 02/11/2026."]


def test_sem_copia_de_reserva_avisa_que_so_tem_a_lista_do_projeto(apis, monkeypatch):
    derrubar_overpass(apis)
    monkeypatch.setattr("app.pontos._copia_de_reserva", lambda: None)
    encontrados, avisos = buscar(-16.80, -49.37, 2, None)
    assert [ponto["nome"] for ponto in encontrados] == ["Ecoponto Campos Dourados"]
    assert "lista do projeto" in avisos[0]


def test_overpass_fora_do_ar_prefere_a_ultima_consulta_guardada(apis, monkeypatch):
    responder_overpass(apis, [elemento(-17.79, -50.92, 1, name="Guardado")])
    buscar(-17.79, -50.92, 10, None)

    # Forca o cache a vencer e derruba o servidor.
    monkeypatch.setattr("app.config.VALIDADE_PONTOS", -1)
    apis.reset()
    derrubar_overpass(apis)
    encontrados, avisos = buscar(-17.79, -50.92, 10, None)
    assert [ponto["nome"] for ponto in encontrados] == ["Guardado"]
    assert "Estes pontos são da consulta de" in avisos[0]


def test_resposta_pela_metade_nao_vai_para_o_cache(apis, monkeypatch):
    """O Overpass responde 200 quando estoura o tempo no meio da consulta."""
    from app import cache

    pela_metade = {"elements": [elemento(-17.79, -50.92, 1, name="Parcial")], "remark": "runtime error: Query timed out"}
    for servidor in config.SERVIDORES_OVERPASS:
        apis.post(servidor).respond(json=pela_metade)
    monkeypatch.setattr("app.pontos._copia_de_reserva", lambda: {"gerado_em": "2026-11-02", "elementos": []})

    encontrados, avisos = buscar(-17.79, -50.92, 10, None)
    assert encontrados == []
    assert "não respondeu" in avisos[0]
    assert cache.obter("overpass:-17.790,-50.920,10") is None


def test_um_servidor_fora_do_ar_nao_derruba_a_busca(apis):
    apis.post(config.SERVIDORES_OVERPASS[0]).respond(status_code=504)
    apis.post(config.SERVIDORES_OVERPASS[1]).respond(text="<html>sobrecarregado</html>")
    apis.post(config.SERVIDORES_OVERPASS[2]).respond(json={"elements": [elemento(-17.79, -50.92, 1, name="Respondeu")]})
    encontrados, avisos = buscar(-17.79, -50.92, 10, None)
    assert [ponto["nome"] for ponto in encontrados] == ["Respondeu"]
    assert avisos == []


def test_depois_de_uma_falha_nao_espera_o_overpass_de_novo(apis, monkeypatch):
    derrubar_overpass(apis)
    monkeypatch.setattr("app.pontos._copia_de_reserva", lambda: {"gerado_em": "2026-11-02", "elementos": []})
    buscar(-17.79, -50.92, 10, None)
    chamadas = apis.calls.call_count
    buscar(-17.00, -50.00, 10, None)
    assert apis.calls.call_count == chamadas
