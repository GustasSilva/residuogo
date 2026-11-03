"""A busca: distancia, limite de Goias, duplicatas e filtro de material."""

import pytest

from app.localizacao import dentro_de_goias
from app.pontos import _remover_duplicatas, buscar, distancia_km
from tests.conftest import elemento, responder_overpass


def test_distancia_entre_goiania_e_anapolis():
    assert distancia_km(-16.6869, -49.2648, -16.3281, -48.9534) == pytest.approx(52, abs=2)


@pytest.mark.parametrize(
    ("latitude", "longitude", "esperado"),
    [
        (-16.68, -49.25, True),  # Goiania
        (-16.07, -47.98, True),  # Valparaiso de Goias, colado no DF
        (-15.54, -47.33, True),  # Formosa
        (-15.79, -47.88, False),  # Brasilia, DF
        (-18.65, -48.19, False),  # Araguari, MG
        (-10.20, -48.33, False),  # Palmas, TO
    ],
)
def test_limite_de_goias(latitude, longitude, esperado):
    assert dentro_de_goias(latitude, longitude) is esperado


def test_ponto_fora_de_goias_nao_aparece(apis):
    responder_overpass(apis, [
        elemento(-16.07, -47.98, 1, name="Em Valparaíso"),
        elemento(-15.79, -47.88, 2, name="Em Brasília"),
    ])
    encontrados, _ = buscar(-16.07, -47.98, 50, None)
    assert [ponto["nome"] for ponto in encontrados] == ["Em Valparaíso"]


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
    assert encontrados[0]["nome"] == "Ecoponto Campos Dourados"
    assert {"chave": "pneus", "rotulo": "Pneus"} in encontrados[0]["materiais"]


def test_ecoponto_da_lista_tem_preferencia_sobre_o_do_mapa(apis):
    responder_overpass(apis, [elemento(-16.80056, -49.36891, 1, name="Ecoponto Campos Dourados", amenity="waste_transfer_station")])
    encontrados, _ = buscar(-16.80, -49.37, 2, None)
    assert [ponto["fonte"] for ponto in encontrados] == ["Prefeitura de Goiânia e imprensa"]
