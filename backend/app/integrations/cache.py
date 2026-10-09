"""Cache em memoria com prazo de validade.

Por que existe: os dados do IBGE e dos Correios mudam muito pouco - a lista
de municipios de Goias muda quando uma lei cria um municipio. Consultar a API
externa a cada vez que uma tela de cadastro abre e desperdicio, deixa o
cadastro lento e torna o sistema dependente da disponibilidade do terceiro.

Por que em memoria, e nao em tabela: o volume e pequeno (246 municipios e os
CEP consultados no dia) e o dado e descartavel - se o processo reiniciar,
basta consultar de novo. Uma tabela exigiria modelo, migracao e limpeza para
guardar o que nao faz falta. O preco dessa escolha e que o cache nao sobrevive
a um reinicio e nao e compartilhado entre varios processos do servidor.
"""

import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class _Entrada:
    """Um valor guardado e o instante em que ele deixa de valer."""

    valor: Any
    expira_em: float


class CacheComValidade:
    """Dicionario em que cada valor carrega a sua propria data de vencimento.

    O relogio usado e o `time.monotonic()`, que conta segundos desde que o
    processo subiu e so anda para frente. O relogio de parede nao serviria:
    um ajuste de horario pelo sistema operacional faria o cache vencer cedo
    ou tarde demais.

    Nao ha trava de concorrencia: gravar e ler uma chave de dicionario sao
    operacoes atomicas em Python, e o pior que duas requisicoes simultaneas
    podem causar e consultar a API externa duas vezes em vez de uma.
    """

    def __init__(self, nome: str) -> None:
        self.nome = nome
        self._entradas: dict[str, _Entrada] = {}

    def guardar(self, chave: str, valor: Any, ttl_segundos: int) -> None:
        """Guarda o valor, valido pelos proximos `ttl_segundos`."""
        self._entradas[chave] = _Entrada(valor, time.monotonic() + ttl_segundos)

    def obter(self, chave: str) -> Any | None:
        """Devolve o valor se ele ainda estiver na validade; senao, `None`."""
        entrada = self._entradas.get(chave)
        if entrada is None or time.monotonic() >= entrada.expira_em:
            return None
        return entrada.valor

    def obter_ultimo(self, chave: str) -> Any | None:
        """Devolve o ultimo valor guardado, **mesmo vencido**.

        Usado somente quando a API externa falha: um dado antigo e melhor que
        uma tela de erro, desde que o cliente seja avisado de que o dado e
        antigo (e o que faz o cabecalho `X-Fonte`).
        """
        entrada = self._entradas.get(chave)
        return None if entrada is None else entrada.valor

    def tamanho(self) -> int:
        """Quantas entradas estao guardadas. Usado no diagnostico (`/health`)."""
        return len(self._entradas)

    def limpar(self) -> None:
        """Descarta tudo. Usado pelos testes, para um partir de cache vazio."""
        self._entradas.clear()
