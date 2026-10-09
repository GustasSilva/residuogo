"""Politica de acesso as APIs externas: tempo limite, nova tentativa e cache.

O risco que este modulo trata: o IBGE e o ViaCEP sao servicos de terceiros,
fora do nosso controle. Se uma chamada a eles ficasse pendurada sem tempo
limite, a requisicao do usuario ficaria pendurada junto; se uma indisponibilidade
deles virasse erro aqui, uma tela nossa pararia de funcionar por causa de um
problema que nao e nosso.

A politica, aplicada igual aos dois servicos:

1. toda chamada tem tempo limite (`http_timeout_segundos`);
2. falhas que valem repetir sao repetidas (`http_tentativas`);
3. a resposta boa vai para o cache;
4. se a API falhar, serve-se o ultimo cache, avisando no cabecalho `X-Fonte`;
5. sem nada em cache, a resposta e 503 - a unica situacao em que a falha do
   terceiro chega ao usuario.

Escrita uma vez aqui e usada por `ibge.py` e `viacep.py`, para que as duas
integracoes nao possam divergir no tratamento de falha.
"""

import logging
from collections.abc import Callable
from enum import Enum
from typing import Any, TypeVar

import httpx

from app.config import config
from app.errors import ServicoExternoIndisponivel
from app.integrations.cache import CacheComValidade

logger = logging.getLogger("residuogo")

# Nome do cabecalho que informa a procedencia do dado. Definido aqui porque e
# usado em dois lugares: nas rotas, que o preenchem, e no CORS, que precisa
# autoriza-lo para que o navegador deixe o front-end le-lo.
CABECALHO_FONTE = "X-Fonte"

# Tipo do dado devolvido pela consulta - mantem a anotacao de tipo fiel ao que
# cada integracao devolve (lista de municipios, dicionario de endereco).
Dado = TypeVar("Dado")

# Um unico cliente HTTP para todo o processo. O ganho nao e apenas reaproveitar
# a conexao: cada cliente novo monta um contexto TLS e carrega a lista de
# autoridades certificadoras do sistema. Medido neste ambiente, criar o cliente
# custa cerca de 0,25 s e repetir o aperto de mao TLS leva uma consulta de
# 0,14 s para 0,65 s - tempo que apareceria em toda consulta nao servida pelo
# cache. O tempo limite nao e fixado aqui, e sim em cada chamada, para que
# continue vindo da configuracao. `follow_redirects` evita que uma mudanca
# de endereco do lado do terceiro seja lida aqui como erro.
_cliente = httpx.Client(follow_redirects=True)


def encerrar_cliente() -> None:
    """Fecha o cliente compartilhado. Chamada no encerramento da aplicacao."""
    _cliente.close()


class Fonte(str, Enum):
    """De onde veio o dado, informado no cabecalho `X-Fonte`.

    Distinguir `cache` de `cache-expirado` importa: o primeiro e a operacao
    normal, o segundo e um aviso de que a API externa esta fora do ar e o
    dado pode estar desatualizado.
    """

    API = "api"
    CACHE = "cache"
    CACHE_EXPIRADO = "cache-expirado"


class FalhaDeComunicacao(Exception):
    """A API externa nao respondeu, ou respondeu algo inutilizavel.

    E uma excecao interna deste pacote: nunca chega ao cliente. Quem a captura
    e `obter_com_cache`, que decide entre servir cache vencido ou devolver 503.
    """


def obter_json(url: str, *, servico: str) -> Any:
    """Faz um GET e devolve o JSON da resposta.

    Repete apenas o que vale repetir - falha de rede e erro 5xx, que sao do
    outro lado e geralmente passageiros. Um 4xx significa que a requisicao
    esta errada: repetir produziria exatamente o mesmo resultado, so gastando
    o tempo do usuario.

    Usa o cliente HTTP compartilhado do modulo, pelo motivo explicado na
    declaracao dele.

    O numero de tentativas e deliberadamente baixo: com tempo limite de 5 s,
    duas tentativas ja podem fazer a rota levar 10 s para responder. Insistir
    mais seria piorar a espera de quem esta na tela em troca de uma chance
    pequena de a terceira tentativa dar certo - o cache cobre melhor esse caso.
    """
    ultima_falha = "sem resposta"

    for tentativa in range(1, config.http_tentativas + 1):
        try:
            resposta = _cliente.get(url, timeout=config.http_timeout_segundos)
        except httpx.RequestError as erro:
            # Tempo limite, DNS, conexao recusada: nada chegou ao servidor.
            ultima_falha = type(erro).__name__
            logger.warning("%s: tentativa %d falhou (%s)", servico, tentativa, ultima_falha)
            continue

        if resposta.is_success:
            try:
                return resposta.json()
            except ValueError:
                # Resposta que nao e JSON (uma pagina de erro em HTML, por
                # exemplo). Repetir nao resolveria.
                raise FalhaDeComunicacao(
                    f"{servico} respondeu em um formato que não é JSON."
                ) from None

        if resposta.status_code < 500:
            raise FalhaDeComunicacao(
                f"{servico} recusou a consulta (HTTP {resposta.status_code})."
            )

        ultima_falha = f"HTTP {resposta.status_code}"
        logger.warning("%s: tentativa %d falhou (%s)", servico, tentativa, ultima_falha)

    raise FalhaDeComunicacao(f"{servico} não respondeu ({ultima_falha}).")


def obter_com_cache(
    *,
    cache: CacheComValidade,
    chave: str,
    ttl_segundos: int,
    servico: str,
    consultar: Callable[[], Dado],
) -> tuple[Dado, Fonte]:
    """Devolve o dado e a sua procedencia, nesta ordem de preferencia:

    1. cache dentro da validade, sem chamar a API;
    2. resposta nova da API, que passa a ser o cache;
    3. ultimo cache guardado, mesmo vencido, quando a API falha;
    4. erro 503, quando a API falha e nao ha nada guardado.

    `consultar` e a funcao que faz a chamada e converte a resposta para o
    formato do sistema - e esse formato convertido que vai para o cache, nao o
    JSON cru do terceiro.

    Erros de dominio levantados por `consultar` atravessam esta funcao sem
    tratamento. Um CEP inexistente, por exemplo, nao e falha de comunicacao: a
    API respondeu, e a resposta correta foi "nao existe". Servir cache naquele
    caso esconderia uma informacao verdadeira.
    """
    guardado = cache.obter(chave)
    if guardado is not None:
        return guardado, Fonte.CACHE

    try:
        dado = consultar()
    except FalhaDeComunicacao as falha:
        reserva = cache.obter_ultimo(chave)
        if reserva is None:
            raise ServicoExternoIndisponivel(
                f"{servico} está indisponível e não há dado guardado em cache "
                "para responder. Tente novamente em alguns instantes."
            ) from falha

        logger.warning("%s indisponível (%s); servindo cache vencido.", servico, falha)
        return reserva, Fonte.CACHE_EXPIRADO

    cache.guardar(chave, dado, ttl_segundos)
    return dado, Fonte.API
