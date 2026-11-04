"""Os pontos de coleta: conversao do que o Nominatim devolve, filtro e ordem."""

import pytest

from app import config
from app.servicos.geo import caixa_em_volta, distancia_km, no_retangulo
from app.servicos.pontos import RAIOS_DOS_MAIS_PROXIMOS_KM, buscar, ponto_do_lugar
from tests.conftest import lugar


def nomes(resultado):
    return [ponto["nome"] for ponto in resultado["pontos"]]


def test_distancia_entre_goiania_e_anapolis():
    assert distancia_km(-16.6869, -49.2648, -16.3281, -48.9534) == pytest.approx(52, abs=2)


def test_caixa_cobre_o_circulo_da_busca():
    oeste, norte, leste, sul = map(float, caixa_em_volta(-16.70, -49.27, 10).split(","))
    assert distancia_km(-16.70, -49.27, norte, -49.27) == pytest.approx(10, abs=0.1)
    assert distancia_km(-16.70, -49.27, -16.70, leste) == pytest.approx(10, abs=0.1)
    assert oeste < leste and sul < norte


@pytest.mark.parametrize(
    ("latitude", "longitude", "esperado"),
    [
        (-16.70, -49.27, True),  # Goiania
        (-10.20, -48.33, False),  # Palmas, TO
        (float("nan"), -49.27, False),
        (float("inf"), -49.27, False),
    ],
)
def test_retangulo_de_goias(latitude, longitude, esperado):
    assert no_retangulo(latitude, longitude, config.CAIXA_DE_GOIAS) is esperado


# --- Conversao ---


def test_materiais_vem_das_etiquetas():
    ponto = ponto_do_lugar(lugar(nome="Cooperativa", **{"recycling:paper": "yes", "recycling:cans": "yes"}))
    assert ponto["materiais"] == ["papel", "metal"]


def test_ponto_sem_etiqueta_de_material_fica_sem_materiais():
    assert ponto_do_lugar(lugar(nome="Cooperativa"))["materiais"] == []


@pytest.mark.parametrize(
    "nome",
    ["inpEV Mineiros", "ADIAGO - Piracanjuba", "Associação de Defensivos Agrícolas", "Associação dos Revendedores de Agrotóxicos"],
)
def test_central_de_agrotoxicos_e_reconhecida_pelo_nome(nome):
    ponto = ponto_do_lugar(lugar(nome=nome, recycling_type="centre"))
    assert ponto["materiais"] == ["agrotoxicos"]
    assert ponto["tipo"] == "Central de embalagens de agrotóxicos"


@pytest.mark.parametrize(
    "dados",
    [
        {"nome": "ATERRO SANITÁRIO", "tipo": "waste_transfer_station"},
        {"nome": "Lixão de Goiandira"},
        {"tipo": "waste_transfer_station"},
        {"nome": "Usina Coruripe", "tipo": "waste_transfer_station"},
        {"nome": "Centro privado", "access": "private"},
        {"nome": "Em Brasília", "estado": "BR-DF"},
        {"nome": "Rua Ecoponto", "categoria": "highway", "tipo": "residential"},
    ],
)
def test_lugares_que_nao_recebem_entrega_ficam_de_fora(dados):
    assert ponto_do_lugar(lugar(**dados)) is None


def test_ecoponto_marcado_como_estacao_de_transbordo_entra():
    ponto = ponto_do_lugar(lugar(nome="Ecoponto Campos Dourados", tipo="waste_transfer_station"))
    assert ponto["tipo"] == "Ecoponto"


def test_ponto_sem_nome_usa_o_tipo():
    assert ponto_do_lugar(lugar(recycling_type="container"))["nome"] == "Contêiner de coleta (sem nome no mapa)"


def test_endereco_horario_e_telefone_vem_do_mapa():
    ponto = ponto_do_lugar(lugar(
        nome="Cooperativa",
        endereco={"road": "Rua 10", "house_number": "5", "suburb": "Setor Oeste", "city": "Goiânia"},
        opening_hours="Mo-Fr 08:00-17:00",
        phone="+55 62 3333-4444",
    ))
    assert ponto["endereco"] == "Rua 10, 5, Setor Oeste, Goiânia"
    assert (ponto["horario"], ponto["telefone"]) == ("Mo-Fr 08:00-17:00", "+55 62 3333-4444")


# --- Busca ---


def test_resultado_vem_do_mais_perto_para_o_mais_longe(nominatim):
    nominatim.pontos = [
        lugar(-16.79, -50.95, 1, nome="Mais longe"),
        lugar(-16.791, -50.92, 2, nome="Mais perto"),
        lugar(-16.86, -50.92, 3, nome="No canto da caixa, fora do raio"),
    ]
    resultado = buscar(-16.79, -50.92, 5, None)
    assert nomes(resultado) == ["Mais perto", "Mais longe"]
    assert resultado["fora_do_raio"] is False


def test_busca_pergunta_pela_caixa_do_raio(nominatim):
    buscar(-16.79, -50.92, 5, None)
    pedido = next(busca for busca in nominatim.buscas if busca["q"] == "[amenity=recycling]")
    assert pedido["viewbox"] == caixa_em_volta(-16.79, -50.92, 5)
    assert (pedido["bounded"], pedido["extratags"], pedido["addressdetails"]) == ("1", "1", "1")


def test_filtro_mantem_quem_aceita_e_quem_nao_informa(nominatim):
    nominatim.pontos = [
        lugar(-16.79, -50.92, 1, nome="Aceita papel", **{"recycling:paper": "yes"}),
        lugar(-16.79, -50.93, 2, nome="Só vidro", **{"recycling:glass": "yes"}),
        lugar(-16.79, -50.94, 3, nome="Não informa"),
        lugar(-16.79, -50.95, 4, nome="inpEV Rio Verde"),
    ]
    assert nomes(buscar(-16.79, -50.92, 10, "papel")) == ["Aceita papel", "Não informa"]


def test_ecoponto_vem_da_busca_pelo_nome(nominatim):
    nominatim.ecopontos = [lugar(-16.80, -49.37, 9, nome="Ecoponto Campos Dourados", tipo="waste_transfer_station")]
    assert nomes(buscar(-16.80, -49.37, 5, None)) == ["Ecoponto Campos Dourados"]
    pedido = next(busca for busca in nominatim.buscas if busca["q"] == "ecoponto")
    assert pedido["viewbox"] == config.CAIXA_DE_GOIAS


def test_mesmo_lugar_nas_duas_buscas_aparece_uma_vez(nominatim):
    ecoponto = lugar(-16.80, -49.37, 9, nome="Ecoponto Vila Nova")
    nominatim.pontos = [ecoponto]
    nominatim.ecopontos = [ecoponto]
    assert nomes(buscar(-16.80, -49.37, 5, None)) == ["Ecoponto Vila Nova"]


def test_sem_ponto_no_raio_mostra_os_mais_proximos_numa_area_maior(nominatim):
    # Pontos a 16, 25, 35, 46 e 57 km: os tres primeiros ja aparecem na area de 50 km.
    nominatim.pontos = [lugar(-13.60 - i / 10, -47.10, i, nome=f"Ponto {i}") for i in range(5)]
    resultado = buscar(-13.50, -47.00, 5, None)
    assert resultado["fora_do_raio"] is True
    assert nomes(resultado) == ["Ponto 0", "Ponto 1", "Ponto 2"]
    caixas = [busca["viewbox"] for busca in nominatim.buscas if busca["q"] == "[amenity=recycling]"]
    assert caixas == [caixa_em_volta(-13.50, -47.00, 5), caixa_em_volta(-13.50, -47.00, 50)]


def test_mais_proximos_juntam_o_que_cada_area_encontrou(nominatim):
    """Caso real perto do DF: na area grande, os pontos do DF tomam o limite do Nominatim."""
    perto = lugar(-13.60, -47.10, 1, nome="Perto")  # a 16 km
    canto = lugar(-14.15, -47.65, 2, nome="No canto")  # a 101 km: dentro do quadrado de 100 km, fora do circulo
    longe = [lugar(-15.00 - i / 10, -47.00, 10 + i, nome=f"Longe {i}") for i in range(3)]  # a mais de 160 km
    nominatim.pontos_por_caixa = {
        caixa_em_volta(-13.50, -47.00, 50): [perto],
        caixa_em_volta(-13.50, -47.00, 100): [perto, canto],
        caixa_em_volta(-13.50, -47.00, 250): longe,  # os dois de cima ficaram de fora
    }
    assert nomes(buscar(-13.50, -47.00, 5, None)) == ["Perto", "No canto", "Longe 0"]
    assert RAIOS_DOS_MAIS_PROXIMOS_KM == (50, 100, 250)


def test_os_mais_proximos_respeitam_o_material(nominatim):
    nominatim.pontos = [lugar(-13.60, -47.10, 1, nome="inpEV Perto")]
    assert nomes(buscar(-13.50, -47.00, 5, "pneus")) == []
    assert nomes(buscar(-13.50, -47.00, 5, "agrotoxicos")) == ["inpEV Perto"]


def test_busca_repetida_usa_o_cache(nominatim):
    buscar(-16.79, -50.92, 10, None)
    chamadas = len(nominatim.buscas)
    buscar(-16.79, -50.92, 10, None)
    assert len(nominatim.buscas) == chamadas
