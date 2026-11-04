"""Contas de geografia usadas na busca."""

import math


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância em linha reta sobre a superfície da Terra, com raio médio de 6371 km."""
    fi1, fi2 = math.radians(lat1), math.radians(lat2)
    delta_fi = fi2 - fi1
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_fi / 2) ** 2 + math.cos(fi1) * math.cos(fi2) * math.sin(delta_lambda / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def caixa_em_volta(latitude: float, longitude: float, raio_km: float) -> str:
    """Retângulo em volta do círculo da busca (oeste, norte, leste, sul). Um grau de latitude tem 111 km."""
    graus_lat = raio_km / 111
    graus_lon = raio_km / (111 * math.cos(math.radians(latitude)))
    return f"{longitude - graus_lon:.4f},{latitude + graus_lat:.4f},{longitude + graus_lon:.4f},{latitude - graus_lat:.4f}"


def no_retangulo(latitude: float, longitude: float, caixa: str) -> bool:
    """Se o ponto fica dentro do retângulo (oeste, norte, leste, sul). Falso para NaN e infinito."""
    oeste, norte, leste, sul = map(float, caixa.split(","))
    return sul <= latitude <= norte and oeste <= longitude <= leste
