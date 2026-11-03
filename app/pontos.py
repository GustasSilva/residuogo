"""A busca: junta os pontos das duas fontes, filtra e ordena."""

import json
import math
from functools import lru_cache

from app import config, overpass
from app.localizacao import dentro_de_goias, sem_acentos
from app.materiais import para_saida

DISTANCIA_DE_DUPLICATA_KM = 0.15


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia em linha reta (formula de Haversine)."""
    fi1, fi2 = math.radians(lat1), math.radians(lat2)
    delta_fi = fi2 - fi1
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_fi / 2) ** 2 + math.cos(fi1) * math.cos(fi2) * math.sin(delta_lambda / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


@lru_cache(maxsize=1)
def _ecopontos() -> tuple[dict, ...]:
    return tuple(json.loads(config.ARQUIVO_ECOPONTOS.read_text("utf-8")))


def _e_duplicata(ponto: dict, outro: dict) -> bool:
    distancia = distancia_km(ponto["latitude"], ponto["longitude"], outro["latitude"], outro["longitude"])
    if distancia >= DISTANCIA_DE_DUPLICATA_KM:
        return False
    return "sem nome" in ponto["nome"] or sem_acentos(ponto["nome"]) == sem_acentos(outro["nome"])


def _remover_duplicatas(pontos: list[dict]) -> list[dict]:
    """Junta o mesmo lugar repetido. Quem vem antes na lista tem preferencia."""
    unicos: list[dict] = []
    for ponto in pontos:
        if not any(_e_duplicata(ponto, outro) for outro in unicos):
            unicos.append(ponto)
    return unicos


# APS-TRECHO 2: A busca dos pontos de coleta
def buscar(latitude: float, longitude: float, raio_km: int, material: str | None) -> tuple[list[dict], list[str]]:
    """Pontos de Goias dentro do raio, do mais perto para o mais longe, e os avisos da consulta.

    Com um material escolhido, tambem entram os pontos que nao informam o que
    aceitam: a tela avisa a pessoa para confirmar antes de ir.
    """
    elementos, aviso = overpass.elementos_perto(latitude, longitude, raio_km)
    do_mapa = [ponto for ponto in map(overpass.ponto_do_elemento, elementos) if ponto]

    # Os ecopontos vem primeiro para terem preferencia sobre o mesmo lugar no mapa.
    perto = []
    for ponto in [*_ecopontos(), *do_mapa]:
        distancia = distancia_km(latitude, longitude, ponto["latitude"], ponto["longitude"])
        if distancia <= raio_km and dentro_de_goias(ponto["latitude"], ponto["longitude"]):
            perto.append({**ponto, "distancia_km": round(distancia, 1)})

    resultado = [
        {**ponto, "materiais": para_saida(ponto["materiais"])}
        for ponto in _remover_duplicatas(perto)
        if not material or not ponto["materiais"] or material in ponto["materiais"]
    ]
    resultado.sort(key=lambda ponto: ponto["distancia_km"])
    return resultado, [aviso] if aviso else []
# APS-FIM
