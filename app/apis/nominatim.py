"""API do Nominatim (OpenStreetMap): coordenadas, pontos em volta e estado de um lugar.

O Nominatim pede no máximo uma chamada por segundo e um User-Agent que identifique
a aplicação.
"""

import time
from typing import Any

from app import config
from app.apis.cache import com_cache, obter_json

# Código do estado que o Nominatim devolve em `ISO3166-2-lvl4`.
GOIAS = "BR-GO"


def _consultar(rota: str, params: dict) -> Any:
    """`rota` é "search" (texto para lugares) ou "reverse" (coordenadas para lugar)."""
    time.sleep(1)  # no máximo uma chamada por segundo
    return obter_json(f"{config.URL_NOMINATIM}/{rota}", "Nominatim", {**params, "format": "jsonv2"})


def em_goias(lugar: dict) -> bool:
    """Lê o estado em um resultado pedido com `addressdetails`."""
    return lugar.get("address", {}).get("ISO3166-2-lvl4") == GOIAS


def coordenadas(**busca: str) -> list[float] | None:
    """Coordenadas de uma busca por rua, bairro ou cidade, ou None se nada foi achado em Goiás."""
    # O Nominatim recusa `q` junto com campos estruturados como `state`.
    filtros = busca if "q" in busca else {**busca, "state": "Goiás"}
    chave = "endereco:" + "|".join(f"{k}={v}" for k, v in sorted(busca.items()))
    lugares = com_cache(
        chave,
        config.VALIDADE_ENDERECOS,
        "Nominatim",
        lambda: _consultar("search", {**filtros, "limit": 1, "countrycodes": "br", "addressdetails": 1}),
    )
    if lugares and em_goias(lugares[0]):
        return [float(lugares[0]["lat"]), float(lugares[0]["lon"])]
    return None


def lugares(texto: str) -> list[dict]:
    """Lugares dentro do retângulo de Goiás para um texto livre, como bairro ou endereço."""
    return com_cache(
        f"texto:{texto.casefold()}",
        config.VALIDADE_ENDERECOS,
        "Nominatim",
        lambda: _consultar(
            "search",
            {
                "q": texto,
                "viewbox": config.CAIXA_DE_GOIAS,
                "bounded": 1,
                "limit": 5,
                "countrycodes": "br",
                "addressdetails": 1,
            },
        ),
    )


def fica_em_goias(latitude: float, longitude: float) -> bool:
    """Pergunta em que estado fica um ponto do mapa (busca reversa)."""
    lugar = com_cache(
        f"estado:{latitude},{longitude}",
        config.VALIDADE_ENDERECOS,
        "Nominatim",
        lambda: _consultar("reverse", {"lat": latitude, "lon": longitude, "zoom": 5}),
    )
    return em_goias(lugar)


# APS-TRECHO 3: Consulta externa com cache e tratamento de queda
def procurar(termo: str, caixa: str) -> list[dict]:
    """Lugares do OpenStreetMap dentro da caixa. `extratags` traz as etiquetas, como os materiais."""
    return com_cache(
        f"pontos:{termo}:{caixa}",
        config.VALIDADE_PONTOS,
        "Nominatim",
        lambda: _consultar(
            "search",
            {"q": termo, "viewbox": caixa, "bounded": 1, "limit": 50, "addressdetails": 1, "extratags": 1},
        ),
    )
# APS-FIM
