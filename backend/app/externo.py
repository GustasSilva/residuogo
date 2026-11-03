"""Chamadas HTTP as APIs externas, com tempo limite e cache."""

import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from app import cache, config
from app.errors import ServicoIndisponivel

logger = logging.getLogger("residuogo")

_cliente = httpx.Client(headers={"User-Agent": config.USER_AGENT}, follow_redirects=True)


class FalhaExterna(Exception):
    """A API externa nao respondeu, ou respondeu algo que nao da para usar."""


def obter_json(url: str, servico: str, params: dict | None = None) -> Any:
    try:
        resposta = _cliente.get(url, params=params, timeout=config.TEMPO_LIMITE_HTTP)
        resposta.raise_for_status()
        return resposta.json()
    except (httpx.HTTPError, ValueError) as erro:
        raise FalhaExterna(f"{servico}: {type(erro).__name__}") from erro


def enviar_consulta(url: str, servico: str, dados: dict, tempo_limite: float) -> Any:
    try:
        resposta = _cliente.post(url, data=dados, timeout=tempo_limite)
        resposta.raise_for_status()
        return resposta.json()
    except (httpx.HTTPError, ValueError) as erro:
        raise FalhaExterna(f"{servico}: {type(erro).__name__}") from erro


# APS-TRECHO 3: Consulta externa com cache e tratamento de queda
def com_cache(chave: str, validade: int, servico: str, consultar: Callable[[], Any]) -> Any:
    """Devolve o dado do cache ou da API; se a API falhar, usa o cache vencido.

    Sem API e sem cache, a busca nao tem como continuar e o cliente recebe 503.
    """
    guardado = cache.obter(chave)
    if guardado and time.time() - guardado[1] < validade:
        return guardado[0]

    try:
        dado = consultar()
    except FalhaExterna as falha:
        logger.warning("Falha externa: %s", falha)
        if guardado:
            return guardado[0]
        raise ServicoIndisponivel(
            f"O serviço {servico} não respondeu. Tente novamente em alguns instantes."
        ) from falha

    cache.guardar(chave, dado)
    return dado
# APS-FIM
