"""Cache das respostas externas em um arquivo SQLite.

Fica em arquivo para sobreviver ao reinicio do servidor: o que foi consultado
uma vez continua disponivel se a API externa cair depois.
"""

import json
import sqlite3
import time
from contextlib import closing
from typing import Any

from app import config


def _conectar() -> sqlite3.Connection:
    conexao = sqlite3.connect(config.ARQUIVO_CACHE)
    conexao.execute(
        "CREATE TABLE IF NOT EXISTS cache ("
        "chave TEXT PRIMARY KEY, valor TEXT NOT NULL, guardado_em REAL NOT NULL)"
    )
    return conexao


def guardar(chave: str, valor: Any) -> None:
    with closing(_conectar()) as conexao, conexao:
        conexao.execute(
            "INSERT OR REPLACE INTO cache (chave, valor, guardado_em) VALUES (?, ?, ?)",
            (chave, json.dumps(valor, ensure_ascii=False), time.time()),
        )


def obter(chave: str) -> tuple[Any, float] | None:
    """Devolve (valor, momento em que foi guardado), mesmo que ja esteja vencido."""
    with closing(_conectar()) as conexao:
        linha = conexao.execute(
            "SELECT valor, guardado_em FROM cache WHERE chave = ?", (chave,)
        ).fetchone()
    if linha is None:
        return None
    return json.loads(linha[0]), linha[1]
