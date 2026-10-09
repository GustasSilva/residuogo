"""Endereco a partir do CEP, pelo ViaCEP.

Serve ao cadastro de organizacoes: o usuario digita o CEP e os campos de
logradouro, bairro e municipio chegam preenchidos. Alem de poupar digitacao,
isso padroniza o endereco - inclusive o codigo IBGE do municipio, que o
ViaCEP devolve junto e que e exatamente o identificador que o sistema guarda.

O ViaCEP e um servico publico, sem cadastro nem chave de acesso, o que o torna
adequado a um projeto academico.
"""

from app.config import config
from app.errors import RecursoNaoEncontrado
from app.integrations.cache import CacheComValidade
from app.integrations.externo import (
    FalhaDeComunicacao,
    Fonte,
    obter_com_cache,
    obter_json,
)
from app.validacoes import apenas_digitos, formatar_cep

SERVICO = "ViaCEP"

# O CEP entra na URL somente com digitos; quem chama ja o normalizou.
URL_CONSULTA = "https://viacep.com.br/ws/{cep}/json/"

cache = CacheComValidade("CEP")


def endereco_por_cep(cep: str) -> tuple[dict[str, str], Fonte]:
    """Busca o endereco de um CEP, do cache ou do ViaCEP.

    Espera o CEP com 8 digitos, sem mascara - a validacao do formato e da
    rota, nao daqui. Cada CEP e uma chave de cache propria.
    """
    return obter_com_cache(
        cache=cache,
        chave=cep,
        ttl_segundos=config.cache_cep_ttl,
        servico=SERVICO,
        consultar=lambda: _consultar(cep),
    )


def _consultar(cep: str) -> dict[str, str]:
    """Chama o ViaCEP e traduz a resposta para os campos do nosso cadastro.

    Os nomes dos campos sao convertidos de proposito: o ViaCEP chama o
    municipio de `localidade` e o codigo IBGE de `ibge`. Traduzir aqui faz com
    que a resposta da nossa API use os mesmos nomes do cadastro de
    organizacoes, e a tela possa aproveitar o retorno campo a campo.
    """
    bruto = obter_json(URL_CONSULTA.format(cep=cep), servico=SERVICO)

    if not isinstance(bruto, dict):
        raise FalhaDeComunicacao(f"{SERVICO} devolveu uma resposta inesperada.")

    # Particularidade do servico: um CEP que nao existe nao devolve 404, e sim
    # HTTP 200 com o corpo {"erro": "true"}. Sem este tratamento, o endereco
    # viria vazio e o usuario nao saberia por que.
    if bruto.get("erro"):
        raise RecursoNaoEncontrado(
            f"CEP {formatar_cep(cep)} não encontrado na base dos Correios."
        )

    return {
        # O ViaCEP devolve o CEP com mascara ("74130-010"); a convencao do
        # projeto e guardar documentos somente com digitos.
        "cep": apenas_digitos(str(bruto.get("cep") or cep)),
        "logradouro": str(bruto.get("logradouro") or ""),
        "bairro": str(bruto.get("bairro") or ""),
        "municipio_nome": str(bruto.get("localidade") or ""),
        "municipio_ibge_codigo": str(bruto.get("ibge") or ""),
        "uf": str(bruto.get("uf") or ""),
    }
