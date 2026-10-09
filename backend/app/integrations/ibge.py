"""Municipios de Goias, pela API de Localidades do IBGE.

A lista alimenta o campo de municipio no cadastro de organizacoes. Usar a
lista oficial evita o problema classico de campo de texto livre: "Goiania",
"Goiânia" e "GOIANIA" viram tres municipios diferentes nos relatorios.

Junto do nome vem o codigo IBGE de 7 digitos, que e o identificador oficial do
municipio e o que o sistema guarda (`Organizacao.municipio_ibge_codigo`).
"""

import unicodedata

from app.config import config
from app.integrations.cache import CacheComValidade
from app.integrations.externo import (
    FalhaDeComunicacao,
    Fonte,
    obter_com_cache,
    obter_json,
)

SERVICO = "IBGE Localidades"

# A URL ja restringe a consulta a Goias (sigla GO, UF 52).
URL_MUNICIPIOS = (
    "https://servicodados.ibge.gov.br/api/v1/localidades/estados/GO/municipios"
)

# A consulta e sempre a mesma, entao o cache tem uma unica chave.
CHAVE = "municipios-go"

cache = CacheComValidade("municípios")


def municipios_de_goias() -> tuple[list[dict[str, str]], Fonte]:
    """Lista os municipios de Goias, do cache ou da API do IBGE.

    Devolve pares `{codigo, nome}` em ordem alfabetica, junto da procedencia
    do dado (ver `Fonte`).
    """
    return obter_com_cache(
        cache=cache,
        chave=CHAVE,
        ttl_segundos=config.cache_municipios_ttl,
        servico=SERVICO,
        consultar=_consultar,
    )


def _consultar() -> list[dict[str, str]]:
    """Chama a API do IBGE e reduz a resposta ao que o sistema usa.

    A resposta do IBGE traz, para cada municipio, a microrregiao, a
    mesorregiao e a regiao aninhadas - algumas centenas de kilobytes que nao
    temos onde usar. Guardar no cache so o codigo e o nome mantem a resposta
    da nossa API pequena e o cache enxuto.
    """
    bruto = obter_json(URL_MUNICIPIOS, servico=SERVICO)

    # Formato diferente do esperado e tratado como falha de comunicacao: assim
    # a resposta estranha nao vai para o cache e, se houver cache anterior, o
    # sistema continua respondendo com ele.
    if not isinstance(bruto, list) or not bruto:
        raise FalhaDeComunicacao(f"{SERVICO} devolveu uma lista de municípios vazia.")

    try:
        municipios = [
            {"codigo": str(municipio["id"]), "nome": str(municipio["nome"])}
            for municipio in bruto
        ]
    except (TypeError, KeyError):
        raise FalhaDeComunicacao(
            f"{SERVICO} mudou o formato da resposta: faltam os campos id e nome."
        ) from None

    return sorted(municipios, key=lambda municipio: _chave_alfabetica(municipio["nome"]))


def _chave_alfabetica(nome: str) -> str:
    """Chave de ordenacao que ignora acentos e caixa.

    Ordenar pelo nome puro usaria a ordem dos codigos dos caracteres, em que
    todo acento vem depois do alfabeto: "Água Fria de Goiás" cairia no fim da
    lista, depois de "Vila Propício". A decomposicao NFKD separa a letra do
    acento, e descartar os acentos devolve a ordem que uma pessoa espera.
    """
    decomposto = unicodedata.normalize("NFKD", nome)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).casefold()
