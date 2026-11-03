"""Os pontos de coleta: busca no OpenStreetMap pelo Nominatim, filtra e ordena."""

import math
import re

from app import config
from app.externo import com_cache, consultar_nominatim
from app.localizacao import em_goias
from app.materiais import materiais_das_etiquetas, para_saida

QUANTOS_MAIS_PROXIMOS = 3
# Sem nada no raio escolhido, os mais proximos sao procurados nesta distancia.
RAIO_DOS_MAIS_PROXIMOS_KM = 250

# Entidades que recebem embalagens de agrotoxicos: o OpenStreetMap nao informa o
# material, mas sem isso alguem procurando onde levar papel seria mandado para la.
NOMES_DE_AGROTOXICOS = re.compile(
    r"inpev|insumos|agrot[oó]xic|defensivos|produtos agr|agropecu|adiago|adirv|arrpa|agerpa|ariara",
    re.IGNORECASE,
)
# Aterros e lixoes aparecem no mapa, mas nao recebem entrega de quem procura um ponto.
NOMES_EXCLUIDOS = re.compile(r"aterro|lix[aã]o", re.IGNORECASE)


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia em linha reta (formula de Haversine)."""
    fi1, fi2 = math.radians(lat1), math.radians(lat2)
    delta_fi = fi2 - fi1
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_fi / 2) ** 2 + math.cos(fi1) * math.cos(fi2) * math.sin(delta_lambda / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


# --- Consulta ---


# APS-TRECHO 4: De onde vem os pontos
def _caixa(latitude: float, longitude: float, raio_km: float) -> str:
    """Retangulo em volta do circulo da busca (oeste, norte, leste, sul). Um grau de latitude tem 111 km."""
    graus_lat = raio_km / 111
    graus_lon = raio_km / (111 * math.cos(math.radians(latitude)))
    return f"{longitude - graus_lon:.4f},{latitude + graus_lat:.4f},{longitude + graus_lon:.4f},{latitude - graus_lat:.4f}"


def _procurar(termo: str, caixa: str) -> list[dict]:
    """Lugares do OpenStreetMap dentro da caixa. `extratags` traz as etiquetas, como os materiais."""
    return com_cache(
        f"pontos:{termo}:{caixa}",
        config.VALIDADE_PONTOS,
        "Nominatim",
        lambda: consultar_nominatim(
            "search",
            {"q": termo, "viewbox": caixa, "bounded": 1, "limit": 50, "addressdetails": 1, "extratags": 1},
        ),
    )


def _lugares(caixa: str) -> list[dict]:
    """Pontos de reciclagem da area e ecopontos do estado, sem repetir o mesmo lugar."""
    encontrados = [
        *_procurar("[amenity=recycling]", caixa),
        # Os ecopontos sao poucos e nem sempre tem a etiqueta de reciclagem: vem pelo nome.
        *_procurar("ecoponto", config.CAIXA_DE_GOIAS),
    ]
    return list({(lugar["osm_type"], lugar["osm_id"]): lugar for lugar in encontrados}.values())
# APS-FIM


# --- Conversao ---


# APS-TRECHO 5: Do resultado do Nominatim para um ponto de coleta
def ponto_do_lugar(lugar: dict) -> dict | None:
    """Converte um lugar do mapa, ou devolve None se ele nao recebe entregas."""
    etiquetas = lugar.get("extratags") or {}
    nome = lugar.get("name") or etiquetas.get("operator") or ""

    if not em_goias(lugar) or lugar.get("category") != "amenity":
        return None
    if etiquetas.get("access") in ("private", "no") or NOMES_EXCLUIDOS.search(nome):
        return None
    # Estacao de transbordo costuma ser area de aterro ou de empresa, nao ponto de entrega.
    if lugar.get("type") != "recycling" and "ecoponto" not in nome.casefold():
        return None

    agrotoxico = bool(NOMES_DE_AGROTOXICOS.search(nome))
    tipo = _tipo(nome, etiquetas, agrotoxico)
    return {
        "nome": nome or f"{tipo} (sem nome no mapa)",
        "tipo": tipo,
        "endereco": _endereco(lugar.get("address", {})),
        "latitude": float(lugar["lat"]),
        "longitude": float(lugar["lon"]),
        "materiais": ["agrotoxicos"] if agrotoxico else materiais_das_etiquetas(etiquetas),
        "telefone": etiquetas.get("phone") or etiquetas.get("contact:phone") or "",
        "horario": etiquetas.get("opening_hours", ""),
    }
# APS-FIM


def _tipo(nome: str, etiquetas: dict, agrotoxico: bool) -> str:
    if agrotoxico:
        return "Central de embalagens de agrotóxicos"
    if "ecoponto" in nome.casefold():
        return "Ecoponto"
    if etiquetas.get("recycling_type") == "container":
        return "Contêiner de coleta"
    return "Centro de reciclagem"


def _endereco(endereco: dict) -> str:
    rua = endereco.get("road", "")
    numero = endereco.get("house_number", "")
    partes = [
        f"{rua}, {numero}" if rua and numero else rua,
        endereco.get("suburb") or endereco.get("neighbourhood", ""),
        endereco.get("city") or endereco.get("town") or endereco.get("village", ""),
    ]
    return ", ".join(parte for parte in partes if parte)


# --- Busca ---


# APS-TRECHO 2: A busca dos pontos de coleta
def _pontos_ordenados(latitude: float, longitude: float, raio_km: float, material: str | None) -> list[dict]:
    """Pontos ate raio_km que servem para o material, do mais perto para o mais longe.

    Com um material escolhido, tambem entram os pontos que nao informam o que
    aceitam: a tela avisa a pessoa para confirmar antes de ir.
    """
    resultado = []
    for ponto in map(ponto_do_lugar, _lugares(_caixa(latitude, longitude, raio_km))):
        if not ponto or (material and ponto["materiais"] and material not in ponto["materiais"]):
            continue
        distancia = round(distancia_km(latitude, longitude, ponto["latitude"], ponto["longitude"]), 1)
        if distancia <= raio_km:
            resultado.append({**ponto, "distancia_km": distancia, "materiais": para_saida(ponto["materiais"])})
    return sorted(resultado, key=lambda ponto: ponto["distancia_km"])


def buscar(latitude: float, longitude: float, raio_km: int, material: str | None) -> dict:
    """Pontos dentro do raio. Sem nenhum, os mais proximos numa area maior."""
    no_raio = _pontos_ordenados(latitude, longitude, raio_km, material)
    if no_raio:
        return {"pontos": no_raio, "fora_do_raio": False}

    # Goias tem poucos pontos mapeados, entao um raio vazio e comum.
    mais_proximos = _pontos_ordenados(latitude, longitude, RAIO_DOS_MAIS_PROXIMOS_KM, material)
    return {"pontos": mais_proximos[:QUANTOS_MAIS_PROXIMOS], "fora_do_raio": True}
# APS-FIM
