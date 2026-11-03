"""Como o projeto fala com as APIs externas: HTTP com tempo limite e cache em arquivo.

Todas as consultas desta pasta passam por aqui.
"""

import json
import logging
import sqlite3
import time
from collections.abc import Callable
from contextlib import closing
from typing import Any

import httpx

from app import config
from app.erros import ServicoIndisponivel

logger = logging.getLogger("residuogo")

_cliente = httpx.Client(headers={"User-Agent": config.USER_AGENT}, follow_redirects=True)


class FalhaExterna(Exception):
    """A API externa nao respondeu, ou respondeu algo que nao da para usar."""


# --- HTTP ---


def obter_json(url: str, servico: str, params: dict | None = None) -> Any:
    try:
        resposta = _cliente.get(url, params=params, timeout=config.TEMPO_LIMITE_HTTP)
        resposta.raise_for_status()
        return resposta.json()
    except (httpx.HTTPError, ValueError) as erro:
        raise FalhaExterna(f"{servico}: {type(erro).__name__}") from erro


# --- Cache ---
# Fica em arquivo para sobreviver ao reinicio do servidor.


def _conectar() -> sqlite3.Connection:
    conexao = sqlite3.connect(config.ARQUIVO_CACHE)
    conexao.execute(
        "CREATE TABLE IF NOT EXISTS cache ("
        "chave TEXT PRIMARY KEY, valor TEXT NOT NULL, guardado_em REAL NOT NULL)"
    )
    return conexao


def _guardar(chave: str, valor: Any) -> None:
    with closing(_conectar()) as conexao, conexao:
        conexao.execute(
            "INSERT OR REPLACE INTO cache (chave, valor, guardado_em) VALUES (?, ?, ?)",
            (chave, json.dumps(valor, ensure_ascii=False), time.time()),
        )


def _ler(chave: str) -> tuple[Any, float] | None:
    """Devolve (valor, momento em que foi guardado), mesmo que ja esteja vencido."""
    with closing(_conectar()) as conexao:
        linha = conexao.execute(
            "SELECT valor, guardado_em FROM cache WHERE chave = ?", (chave,)
        ).fetchone()
    return (json.loads(linha[0]), linha[1]) if linha else None


# APS-TRECHO 6: Consulta externa com cache e tratamento de queda
def com_cache(chave: str, validade: int, servico: str, consultar: Callable[[], Any]) -> Any:
    """Devolve o dado do cache ou da API; se a API falhar, usa o cache vencido.

    Sem API e sem cache, a busca nao tem como continuar e o cliente recebe 503.
    """
    guardado = _ler(chave)
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

    _guardar(chave, dado)
    return dado
# APS-FIM
