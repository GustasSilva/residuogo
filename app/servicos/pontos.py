"""Os pontos de coleta: pede ao Nominatim, converte, filtra e ordena."""

import re

from app import config
from app.apis import nominatim
from app.servicos.geo import caixa_em_volta, distancia_km
from app.servicos.materiais import materiais_das_etiquetas, para_saida

QUANTOS_MAIS_PROXIMOS = 3
# Sem nada no raio escolhido, a busca aumenta a área até achar os mais próximos. As áreas
# menores vêm primeiro: numa área grande, os muitos pontos do DF tomam o limite de
# resultados do Nominatim e pontos de Goiás, mesmo perto, podem ficar de fora.
RAIOS_DOS_MAIS_PROXIMOS_KM = (50, 100, 250)

# Entidades que recebem embalagens de agrotóxicos: o OpenStreetMap não informa o
# material, mas sem isso alguem procurando onde levar papel seria mandado para la.
NOMES_DE_AGROTOXICOS = re.compile(
    r"inpev|insumos|agrot[oó]xic|defensivos|produtos agr|agropecu|adiago|adirv|arrpa|agerpa|ariara",
    re.IGNORECASE,
)
# Aterros e lixões aparecem no mapa, mas não recebem entrega de quem procura um ponto.
NOMES_EXCLUIDOS = re.compile(r"aterro|lix[aã]o", re.IGNORECASE)


# --- Conversão ---


# APS-TRECHO 2: A localização e a busca dos pontos de coleta
def ponto_do_lugar(lugar: dict) -> dict | None:
    """Converte um lugar do mapa, ou devolve None se ele não recebe entregas."""
    etiquetas = lugar.get("extratags") or {}
    nome = lugar.get("name") or etiquetas.get("operator") or ""

    if not nominatim.em_goias(lugar) or lugar.get("category") != "amenity":
        return None
    if etiquetas.get("access") in ("private", "no") or NOMES_EXCLUIDOS.search(nome):
        return None
    # Só entram pontos de reciclagem e ecopontos, não estações de transbordo.
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


# APS-TRECHO 2: A localização e a busca dos pontos de coleta
def _lugares(caixa: str) -> list[dict]:
    """Pontos de reciclagem da área e ecopontos do estado, sem repetir o mesmo lugar."""
    encontrados = [
        *nominatim.procurar("[amenity=recycling]", caixa),
        # Os ecopontos são poucos e nem sempre têm a etiqueta de reciclagem: vêm pelo nome.
        *nominatim.procurar("ecoponto", config.CAIXA_DE_GOIAS),
    ]
    return list({(lugar["osm_type"], lugar["osm_id"]): lugar for lugar in encontrados}.values())


def _pontos_na_area(latitude: float, longitude: float, raio_km: float, material: str | None) -> list[dict]:
    """Pontos do retângulo em volta do raio que servem para o material, do mais perto para o mais longe.

    Com um material escolhido, também entram os pontos que não informam o que
    aceitam: a tela avisa a pessoa para confirmar antes de ir.
    """
    resultado = []
    for ponto in map(ponto_do_lugar, _lugares(caixa_em_volta(latitude, longitude, raio_km))):
        if not ponto or (material and ponto["materiais"] and material not in ponto["materiais"]):
            continue
        distancia = round(distancia_km(latitude, longitude, ponto["latitude"], ponto["longitude"]), 1)
        resultado.append({**ponto, "distancia_km": distancia, "materiais": para_saida(ponto["materiais"])})
    return sorted(resultado, key=lambda ponto: ponto["distancia_km"])


def buscar(latitude: float, longitude: float, raio_km: int, material: str | None) -> dict:
    """Pontos dentro do raio. Sem nenhum, os mais próximos, aumentando a área aos poucos."""
    no_raio = [ponto for ponto in _pontos_na_area(latitude, longitude, raio_km, material) if ponto["distancia_km"] <= raio_km]
    if no_raio:
        return {"pontos": no_raio, "fora_do_raio": False}

    # Goiás tem poucos pontos mapeados, então um raio vazio é comum. Junta tudo o que cada
    # área achou, para um ponto perto encontrado na área pequena não se perder na grande.
    encontrados = {}
    for raio in RAIOS_DOS_MAIS_PROXIMOS_KM:
        for ponto in _pontos_na_area(latitude, longitude, raio, material):
            encontrados[(ponto["latitude"], ponto["longitude"])] = ponto
        mais_proximos = sorted(encontrados.values(), key=lambda ponto: ponto["distancia_km"])
        # Para quando os mais próximos já estão dentro do raio desta área, que foi toda procurada.
        if len(mais_proximos) >= QUANTOS_MAIS_PROXIMOS and mais_proximos[QUANTOS_MAIS_PROXIMOS - 1]["distancia_km"] <= raio:
            break
    return {"pontos": mais_proximos[:QUANTOS_MAIS_PROXIMOS], "fora_do_raio": True}
# APS-FIM
