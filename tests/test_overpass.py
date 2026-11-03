"""Conversao dos dados do OpenStreetMap e o que acontece quando o Overpass cai."""

import pytest

from app import config, externo, overpass
from app.overpass import elementos_perto, ponto_do_elemento
from tests.conftest import derrubar_overpass, elemento, responder_overpass

COPIA = {"gerado_em": "2026-11-02", "elementos": [elemento(-17.79, -50.92, 1, name="Da cópia")]}


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


def test_consulta_repetida_nao_chama_o_overpass_de_novo(apis):
    responder_overpass(apis, [])
    elementos_perto(-17.79, -50.92, 10)
    chamadas = apis.calls.call_count
    elementos_perto(-17.79, -50.92, 10)
    assert apis.calls.call_count == chamadas


def test_consulta_vencida_pergunta_de_novo(apis, monkeypatch):
    responder_overpass(apis, [])
    elementos_perto(-17.79, -50.92, 10)
    chamadas = apis.calls.call_count
    monkeypatch.setattr(config, "VALIDADE_PONTOS", -1)
    elementos_perto(-17.79, -50.92, 10)
    assert apis.calls.call_count > chamadas


def test_overpass_fora_do_ar_usa_a_copia_de_reserva(apis, monkeypatch):
    derrubar_overpass(apis)
    monkeypatch.setattr(overpass, "_copia_de_reserva", lambda: COPIA)
    elementos, aviso = elementos_perto(-17.79, -50.92, 10)
    assert elementos == COPIA["elementos"]
    assert aviso == "O OpenStreetMap não respondeu. Estes pontos são da cópia de 02/11/2026."


def test_copia_do_projeto_so_tem_pontos_de_goias():
    from app.localizacao import dentro_de_goias

    copia = overpass._copia_de_reserva()
    assert copia["elementos"]
    assert all(dentro_de_goias(item["lat"], item["lon"]) for item in copia["elementos"])


def test_resposta_pela_metade_nao_vai_para_o_cache(apis, monkeypatch):
    """O Overpass responde 200 quando estoura o tempo no meio da consulta."""
    pela_metade = {"elements": [elemento(name="Parcial")], "remark": "runtime error: Query timed out"}
    for servidor in config.SERVIDORES_OVERPASS:
        apis.post(servidor).respond(json=pela_metade)
    monkeypatch.setattr(overpass, "_copia_de_reserva", lambda: COPIA)

    elementos, aviso = elementos_perto(-17.79, -50.92, 10)
    assert elementos == COPIA["elementos"]
    assert "não respondeu" in aviso
    assert externo.ler_do_cache("overpass:-17.790,-50.920,10") is None


def test_um_servidor_fora_do_ar_nao_derruba_a_busca(apis):
    respondeu = elemento(name="Respondeu")
    apis.post(config.SERVIDORES_OVERPASS[0]).respond(status_code=504)
    apis.post(config.SERVIDORES_OVERPASS[1]).respond(text="<html>sobrecarregado</html>")
    apis.post(config.SERVIDORES_OVERPASS[2]).respond(json={"elements": [respondeu]})
    assert elementos_perto(-17.79, -50.92, 10) == ([respondeu], "")


def test_depois_de_uma_falha_nao_espera_o_overpass_de_novo(apis, monkeypatch):
    derrubar_overpass(apis)
    monkeypatch.setattr(overpass, "_copia_de_reserva", lambda: COPIA)
    elementos_perto(-17.79, -50.92, 10)
    chamadas = apis.calls.call_count
    elementos_perto(-17.00, -50.00, 10)
    assert apis.calls.call_count == chamadas
