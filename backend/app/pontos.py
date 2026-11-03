"""Busca os pontos de coleta perto de uma coordenada.

Os pontos vem de duas fontes: a lista de ecopontos de Goiania, guardada no
projeto, e o OpenStreetMap, consultado pela API Overpass. Se o Overpass nao
responder, a busca usa o ultimo resultado guardado ou a copia de reserva.
"""

import json
import math
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as TempoEsgotado
from datetime import date, datetime
from functools import lru_cache

from app import cache, config
from app.externo import FalhaExterna, elementos_do_overpass, enviar_consulta
from app.materiais import materiais_das_etiquetas, para_saida

# Entidades que recebem embalagens de agrotoxicos: o OpenStreetMap nao informa o
# material, mas sem isso alguem procurando onde levar papel seria mandado para la.
NOMES_DE_AGROTOXICOS = re.compile(
    r"inpev|insumos agr|agrot[oó]xic|defensivos|produtos agr|agropecu|adiago|adirv|arrpa|agerpa|ariara",
    re.IGNORECASE,
)
# Aterros e lixoes aparecem no mapa, mas nao recebem entrega de quem procura um ponto.
NOMES_EXCLUIDOS = re.compile(r"aterro|lix[aã]o", re.IGNORECASE)
DISTANCIA_DE_DUPLICATA_KM = 0.15

_ultima_falha_overpass = -math.inf


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia em linha reta (formula de Haversine)."""
    fi1, fi2 = math.radians(lat1), math.radians(lat2)
    delta_fi = fi2 - fi1
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_fi / 2) ** 2 + math.cos(fi1) * math.cos(fi2) * math.sin(delta_lambda / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


# APS-TRECHO 4: Do dado cru do OpenStreetMap para um ponto de coleta
def ponto_do_elemento(elemento: dict) -> dict | None:
    """Converte um elemento do OpenStreetMap, ou devolve None se ele nao serve."""
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

    materiais = materiais_das_etiquetas(etiquetas)
    agrotoxico = bool(NOMES_DE_AGROTOXICOS.search(nome))
    if agrotoxico:
        materiais = ["agrotoxicos"]

    tipo = _tipo(nome, etiquetas, agrotoxico)
    return {
        "nome": nome or f"{tipo} (sem nome no mapa)",
        "tipo": tipo,
        "endereco": _endereco(etiquetas),
        "latitude": latitude,
        "longitude": longitude,
        "materiais": materiais,
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


@lru_cache(maxsize=1)
def _ecopontos() -> tuple[dict, ...]:
    return tuple(json.loads(config.ARQUIVO_ECOPONTOS.read_text("utf-8")))


@lru_cache(maxsize=1)
def _copia_de_reserva() -> dict | None:
    if not config.ARQUIVO_COPIA_OSM.exists():
        return None
    return json.loads(config.ARQUIVO_COPIA_OSM.read_text("utf-8"))


def _perguntar_ao_overpass(latitude: float, longitude: float, raio_km: int) -> list[dict]:
    """Pergunta a todos os servidores ao mesmo tempo e fica com o primeiro que responder.

    Perguntar a um de cada vez deixaria a pessoa esperando pela soma dos tempos limite.
    """
    limite = config.TEMPO_LIMITE_OVERPASS
    alvo = f"around:{raio_km * 1000},{latitude:.5f},{longitude:.5f}"
    consulta = (
        f"[out:json][timeout:{limite}];("
        f'nwr["amenity"="recycling"]({alvo});'
        f'nwr["amenity"="waste_transfer_station"]({alvo});'
        ");out tags center;"
    )

    executor = ThreadPoolExecutor(max_workers=len(config.SERVIDORES_OVERPASS))
    futuros = [
        executor.submit(enviar_consulta, servidor, "Overpass", {"data": consulta}, limite)
        for servidor in config.SERVIDORES_OVERPASS
    ]
    try:
        for futuro in as_completed(futuros, timeout=limite):
            try:
                return elementos_do_overpass(futuro.result())
            except FalhaExterna:
                continue
    except TempoEsgotado:
        pass
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
    raise FalhaExterna("Overpass: nenhum servidor respondeu")


# APS-TRECHO 1: De onde vem os pontos, e o que acontece quando o Overpass cai
def _elementos_do_osm(latitude: float, longitude: float, raio_km: int) -> tuple[list[dict], str]:
    """Devolve os elementos do OpenStreetMap e um aviso, se o dado nao for atual."""
    global _ultima_falha_overpass
    chave = f"overpass:{latitude:.3f},{longitude:.3f},{raio_km}"
    guardado = cache.obter(chave)
    if guardado and time.time() - guardado[1] < config.VALIDADE_PONTOS:
        return guardado[0], ""

    # Logo depois de uma falha nao adianta esperar o tempo limite de novo.
    if time.monotonic() - _ultima_falha_overpass >= config.ESPERA_APOS_FALHA_OVERPASS:
        try:
            elementos = _perguntar_ao_overpass(latitude, longitude, raio_km)
            cache.guardar(chave, elementos)
            return elementos, ""
        except FalhaExterna:
            _ultima_falha_overpass = time.monotonic()

    if guardado:
        data = datetime.fromtimestamp(guardado[1]).strftime("%d/%m/%Y")
        return guardado[0], f"O OpenStreetMap não respondeu. Estes pontos são da consulta de {data}."

    copia = _copia_de_reserva()
    if copia is None:
        return [], "O OpenStreetMap não respondeu. Só os pontos da lista do projeto aparecem aqui."

    data = date.fromisoformat(copia["gerado_em"]).strftime("%d/%m/%Y")
    return copia["elementos"], f"O OpenStreetMap não respondeu. Estes pontos são da cópia de {data}."
# APS-FIM


def _normalizar(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome)
    return "".join(c for c in sem_acento if c.isalnum()).casefold()


def _remover_duplicatas(pontos: list[dict]) -> list[dict]:
    """Junta o mesmo lugar repetido. Quem vem antes na lista tem preferencia."""
    unicos: list[dict] = []
    for ponto in pontos:
        repetido = any(
            distancia_km(ponto["latitude"], ponto["longitude"], outro["latitude"], outro["longitude"])
            < DISTANCIA_DE_DUPLICATA_KM
            and (_normalizar(ponto["nome"]) == _normalizar(outro["nome"]) or "sem nome" in ponto["nome"])
            for outro in unicos
        )
        if not repetido:
            unicos.append(ponto)
    return unicos


def buscar(latitude: float, longitude: float, raio_km: int, material: str | None) -> tuple[list[dict], list[str]]:
    """Pontos dentro do raio, do mais perto para o mais longe, e os avisos da consulta.

    Com um material escolhido, tambem entram os pontos que nao informam o que
    aceitam: a tela mostra "não informado" para a pessoa confirmar antes de ir.
    """
    elementos, aviso = _elementos_do_osm(latitude, longitude, raio_km)
    do_osm = [ponto for ponto in map(ponto_do_elemento, elementos) if ponto]

    # Os ecopontos vem primeiro para terem preferencia sobre o mesmo lugar no mapa.
    perto = []
    for ponto in [*_ecopontos(), *do_osm]:
        distancia = distancia_km(latitude, longitude, ponto["latitude"], ponto["longitude"])
        if distancia <= raio_km:
            perto.append({**ponto, "distancia_km": round(distancia, 1)})

    resultado = [
        {**ponto, "materiais": para_saida(ponto["materiais"])}
        for ponto in _remover_duplicatas(perto)
        if not material or not ponto["materiais"] or material in ponto["materiais"]
    ]
    resultado.sort(key=lambda ponto: ponto["distancia_km"])
    return resultado, [aviso] if aviso else []
