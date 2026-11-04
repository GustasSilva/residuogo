"""API do IBGE: municípios de Goiás e contorno oficial do estado."""

from app import config
from app.apis.cache import FalhaExterna, com_cache, obter_json


def municipios() -> list[dict[str, str]]:
    """Municípios de Goiás com o código e a região intermediária do IBGE."""
    return com_cache("municipios-go", config.VALIDADE_ENDERECOS, "IBGE", _consultar_municipios)


def _consultar_municipios() -> list[dict[str, str]]:
    bruto = obter_json(config.URL_MUNICIPIOS, "IBGE")
    try:
        lista = [
            {
                "codigo": str(item["id"]),
                "nome": item["nome"],
                "regiao": item["regiao-imediata"]["regiao-intermediaria"]["nome"],
            }
            for item in bruto
        ]
    except (KeyError, TypeError) as erro:
        raise FalhaExterna("IBGE: resposta em formato inesperado") from erro
    if not lista:
        raise FalhaExterna("IBGE: lista de municipios vazia")
    return lista


def contorno_de_goias() -> dict:
    """Contorno oficial do estado, em GeoJSON, para desenhar no mapa."""
    return com_cache(
        "contorno-go",
        config.VALIDADE_ENDERECOS,
        "IBGE",
        lambda: obter_json(
            config.URL_CONTORNO_GOIAS,
            "IBGE",
            {"formato": "application/vnd.geo+json", "qualidade": "intermediaria"},
        ),
    )
