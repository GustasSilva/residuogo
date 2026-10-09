"""Rotas de apoio ao cadastro: municipios do IBGE e endereco por CEP.

As duas rotas repassam consultas a APIs publicas. O front-end poderia chamar
o IBGE e o ViaCEP diretamente; passar por aqui traz tres ganhos:

* o cache e **compartilhado por todos os usuarios** - o primeiro acesso do dia
  paga a consulta, os demais sao servidos da memoria do servidor;
* a resposta sai com os nomes de campo do nosso cadastro, nao com os do
  terceiro, de modo que a tela nao precisa saber que o ViaCEP chama o
  municipio de "localidade";
* a falha do terceiro e tratada em um unico lugar e chega ao cliente no mesmo
  formato RFC 7807 de todos os outros erros da API.

Toda resposta traz o cabecalho `X-Fonte`, dizendo se o dado veio da API (`api`),
do cache (`cache`) ou do cache vencido porque a API esta fora do ar
(`cache-expirado`).
"""

from typing import Annotated

from fastapi import APIRouter, Path, Response
from pydantic import BeforeValidator

from app.dependencies import UsuarioAtual
from app.integrations import ibge, viacep
from app.integrations.externo import CABECALHO_FONTE, Fonte
from app.schemas import EnderecoCepSaida, MunicipioSaida
from app.validacoes import normalizar_cep

router = APIRouter(prefix="/localidades", tags=["Localidades"])

# O FastAPI documenta sozinho o corpo da resposta, mas nao um cabecalho que a
# rota preenche em codigo. Esta descricao e o que faz o `X-Fonte` aparecer no
# Swagger e no `openapi.json` exportado. Os valores possiveis vem do proprio
# enum, para que a documentacao nao possa divergir do comportamento.
DOCUMENTACAO_DA_FONTE = {
    200: {
        "headers": {
            CABECALHO_FONTE: {
                "description": "De onde veio o dado devolvido.",
                "schema": {"type": "string", "enum": [fonte.value for fonte in Fonte]},
            }
        }
    }
}

# O CEP chega na URL com ou sem mascara e e normalizado antes de a rota rodar.
# `normalizar_cep` levanta `ValueError` quando o formato esta errado, e o
# Pydantic o converte em erro de validacao 422 apontando o campo - o mesmo
# tratamento que um campo do corpo da requisicao receberia.
CepNaUrl = Annotated[
    str,
    BeforeValidator(normalizar_cep),
    Path(description="CEP com ou sem máscara.", examples=["74130010"]),
]


@router.get(
    "/municipios-go",
    response_model=list[MunicipioSaida],
    responses=DOCUMENTACAO_DA_FONTE,
    summary="Municípios de Goiás (IBGE)",
)
def municipios(resposta: Response, _: UsuarioAtual) -> list[dict[str, str]]:
    """Lista os 246 municípios de Goiás, em ordem alfabética.

    Alimenta o campo de município do cadastro de organizações. A lista vem da
    API de Localidades do IBGE e fica em cache por 30 dias, porque muda apenas
    quando uma lei cria ou extingue um município.
    """
    dados, fonte = ibge.municipios_de_goias()
    resposta.headers[CABECALHO_FONTE] = fonte.value
    return dados


@router.get(
    "/cep/{cep}",
    response_model=EnderecoCepSaida,
    responses=DOCUMENTACAO_DA_FONTE,
    summary="Endereço de um CEP (ViaCEP)",
)
def endereco_do_cep(
    cep: CepNaUrl, resposta: Response, _: UsuarioAtual
) -> dict[str, str]:
    """Busca o endereço de um CEP para preencher o formulário de cadastro.

    Devolve 404 quando o CEP não existe na base dos Correios — situação
    diferente de o ViaCEP estar fora do ar, que resulta em 503 (ou no último
    endereço consultado, se houver cache).
    """
    dados, fonte = viacep.endereco_por_cep(cep)
    resposta.headers[CABECALHO_FONTE] = fonte.value
    return dados
