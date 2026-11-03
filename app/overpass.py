"""Pontos de coleta do OpenStreetMap, pela API Overpass.

Os servidores publicos ficam sobrecarregados com frequencia. Quando nenhum
responde, a busca usa a copia dos dados de Goias guardada em `dados/`.
"""

import json
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as TempoEsgotado
from datetime import date
from functools import lru_cache
from typing import Any

from app import config
from app.externo import FalhaExterna, enviar_consulta, guardar_no_cache, ler_do_cache
from app.materiais import materiais_das_etiquetas

# Entidades que recebem embalagens de agrotoxicos: o OpenStreetMap nao informa o
# material, mas sem isso alguem procurando onde levar papel seria mandado para la.
NOMES_DE_AGROTOXICOS = re.compile(
    r"inpev|insumos|agrot[oó]xic|defensivos|produtos agr|agropecu|adiago|adirv|arrpa|agerpa|ariara",
    re.IGNORECASE,
)
# Aterros e lixoes aparecem no mapa, mas nao recebem entrega de quem procura um ponto.
NOMES_EXCLUIDOS = re.compile(r"aterro|lix[aã]o", re.IGNORECASE)

# Consultas em celulas de 0,1 grau (cerca de 11 km), com folga no raio. Assim buscas e
# cliques proximos aproveitam o mesmo resultado, e pontos.py calcula a distancia exata.
FOLGA_DA_CELULA_KM = 8

_ultima_falha = -math.inf


# --- Consulta ---


# APS-TRECHO 4: De onde vem os pontos, e o que acontece quando o Overpass cai
def elementos_perto(latitude: float, longitude: float, raio_km: int) -> tuple[list[dict], str]:
    """Devolve os elementos do mapa e um aviso, quando eles vierem da copia."""
    global _ultima_falha
    celula = round(latitude, 1), round(longitude, 1)
    chave = f"overpass:{celula[0]},{celula[1]},{raio_km}"
    guardado = ler_do_cache(chave)
    if guardado and time.time() - guardado[1] < config.VALIDADE_PONTOS:
        return guardado[0], ""

    # Logo depois de uma falha nao adianta esperar o tempo limite de novo.
    if time.monotonic() - _ultima_falha >= config.ESPERA_APOS_FALHA_OVERPASS:
        try:
            return _perguntar_aos_servidores(chave, *celula, raio_km + FOLGA_DA_CELULA_KM), ""
        except FalhaExterna:
            _ultima_falha = time.monotonic()

    copia = _copia_de_reserva()
    data = date.fromisoformat(copia["gerado_em"]).strftime("%d/%m/%Y")
    return copia["elementos"], f"O OpenStreetMap não respondeu. Estes pontos são da cópia de {data}."
# APS-FIM


def _perguntar_aos_servidores(chave: str, latitude: float, longitude: float, raio_km: int) -> list[dict]:
    """Pergunta a todos ao mesmo tempo e fica com o primeiro que responder."""
    alvo = f"around:{raio_km * 1000},{latitude},{longitude}"
    consulta = (
        f"[out:json][timeout:{config.TEMPO_LIMITE_OVERPASS}];("
        f'nwr["amenity"="recycling"]({alvo});'
        f'nwr["amenity"="waste_transfer_station"]({alvo});'
        ");out tags center;"
    )

    executor = ThreadPoolExecutor(max_workers=len(config.SERVIDORES_OVERPASS), thread_name_prefix="overpass")
    futuros = [executor.submit(_perguntar, servidor, consulta, chave) for servidor in config.SERVIDORES_OVERPASS]
    try:
        for futuro in as_completed(futuros, timeout=config.ESPERA_OVERPASS):
            try:
                return futuro.result()
            except FalhaExterna:
                continue
    except TempoEsgotado:
        pass
    finally:
        executor.shutdown(wait=False)
    raise FalhaExterna("Overpass: nenhum servidor respondeu")


def _perguntar(servidor: str, consulta: str, chave: str) -> list[dict]:
    """Guarda a resposta aqui: mesmo que a busca ja tenha desistido, a proxima aproveita."""
    resposta = enviar_consulta(servidor, "Overpass", {"data": consulta}, config.TEMPO_LIMITE_OVERPASS)
    elementos = elementos_da_resposta(resposta)
    guardar_no_cache(chave, elementos)
    return elementos


def elementos_da_resposta(resposta: Any) -> list[dict]:
    """O Overpass pode responder 200 com o resultado pela metade e o erro em `remark`."""
    try:
        if "error" in resposta.get("remark", ""):
            raise FalhaExterna(f"Overpass: {resposta['remark']}")
        return resposta["elements"]
    except (AttributeError, KeyError, TypeError) as erro:
        raise FalhaExterna("Overpass: resposta em formato inesperado") from erro


@lru_cache(maxsize=1)
def _copia_de_reserva() -> dict:
    return json.loads(config.ARQUIVO_COPIA_OSM.read_text("utf-8"))


def elementos_de_goias() -> list[dict]:
    return _copia_de_reserva()["elementos"]


# --- Conversao ---


# APS-TRECHO 5: Do dado cru do OpenStreetMap para um ponto de coleta
def ponto_do_elemento(elemento: dict) -> dict | None:
    """Converte um elemento do mapa, ou devolve None se ele nao recebe entregas."""
    etiquetas = elemento.get("tags", {})
    latitude = elemento.get("lat", elemento.get("center", {}).get("lat"))
    longitude = elemento.get("lon", elemento.get("center", {}).get("lon"))
    nome = etiquetas.get("name") or etiquetas.get("operator") or ""

    if latitude is None or longitude is None:
        return None
    if etiquetas.get("access") in ("private", "no") or NOMES_EXCLUIDOS.search(nome):
        return None
    # Estacao de transbordo costuma ser area de aterro ou de empresa, nao ponto de entrega.
    if etiquetas.get("amenity") == "waste_transfer_station" and "ecoponto" not in nome.casefold():
        return None

    agrotoxico = bool(NOMES_DE_AGROTOXICOS.search(nome))
    tipo = _tipo(nome, etiquetas, agrotoxico)
    return {
        "nome": nome or f"{tipo} (sem nome no mapa)",
        "tipo": tipo,
        "endereco": _endereco(etiquetas),
        "latitude": latitude,
        "longitude": longitude,
        "materiais": ["agrotoxicos"] if agrotoxico else materiais_das_etiquetas(etiquetas),
        "telefone": etiquetas.get("phone") or etiquetas.get("contact:phone") or "",
        "horario": etiquetas.get("opening_hours", ""),
        "observacao": "",
        "fonte": "OpenStreetMap",
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


def _endereco(etiquetas: dict) -> str:
    rua = etiquetas.get("addr:street", "")
    numero = etiquetas.get("addr:housenumber", "")
    partes = [
        f"{rua}, {numero}" if rua and numero else rua,
        etiquetas.get("addr:suburb", ""),
        etiquetas.get("addr:city", ""),
    ]
    return ", ".join(parte for parte in partes if parte)
