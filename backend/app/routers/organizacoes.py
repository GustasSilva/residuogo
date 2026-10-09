"""Rotas de cadastro e consulta das organizacoes participantes.

Cadastro restrito ao ADMIN; consulta liberada a qualquer usuario autenticado,
porque a tela de novo manifesto precisa listar transportadores e destinadores
disponiveis.
"""

from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.dependencies import PaginaParams, Sessao, UsuarioAdmin, UsuarioAtual
from app.enums import PapelOrganizacao
from app.models import Organizacao
from app.paginacao import paginar
from app.schemas import OrganizacaoCriar, OrganizacaoSaida, Pagina
from app.services import organizacoes as servico

router = APIRouter(prefix="/organizacoes", tags=["Organizações"])


@router.post(
    "",
    response_model=OrganizacaoSaida,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra uma organização (ADMIN)",
)
def criar(dados: OrganizacaoCriar, sessao: Sessao, _: UsuarioAdmin) -> Organizacao:
    """Cadastra um participante do ciclo do resíduo.

    O CNPJ é validado pelos dígitos verificadores e gravado somente com
    dígitos; a regra está em `validacoes.py`, aplicada pelo schema de entrada.
    """
    return servico.criar(sessao, dados)


@router.get(
    "",
    response_model=Pagina[OrganizacaoSaida],
    summary="Lista organizações, com filtros",
)
def listar(
    sessao: Sessao,
    paginacao: PaginaParams,
    _: UsuarioAtual,
    papel: Annotated[
        PapelOrganizacao | None,
        Query(description="Filtra pelo papel no ciclo do resíduo."),
    ] = None,
    apenas_aptas: Annotated[
        bool,
        Query(
            description=(
                "Quando verdadeiro, devolve apenas organizações ativas e com licença "
                "ambiental válida. Exige que `papel` seja informado. É o filtro usado "
                "pela tela de novo manifesto."
            )
        ),
    ] = False,
    busca: Annotated[
        str | None,
        Query(description="Texto procurado na razão social ou no CNPJ."),
    ] = None,
) -> dict:
    """Lista participantes de forma paginada.

    O filtro `apenas_aptas` reutiliza exatamente as mesmas condições que a
    emissão do manifesto aplica (regra RN04), de modo que a tela nunca ofereça
    um participante que a API depois recusaria.
    """
    consulta = select(Organizacao)

    if papel is not None:
        if apenas_aptas:
            # A definição de "apta" vem do serviço, não daqui: é a mesma
            # usada na emissão do manifesto.
            consulta = consulta.where(*servico.condicoes_apta(papel))
        else:
            consulta = consulta.where(Organizacao.papel == papel)

    if busca:
        termo = f"%{busca.strip()}%"
        consulta = consulta.where(
            Organizacao.razao_social.ilike(termo) | Organizacao.cnpj.ilike(termo)
        )

    return paginar(sessao, consulta.order_by(Organizacao.razao_social), paginacao)


@router.get(
    "/{organizacao_id}",
    response_model=OrganizacaoSaida,
    summary="Detalhe de uma organização",
)
def detalhar(organizacao_id: int, sessao: Sessao, _: UsuarioAtual) -> Organizacao:
    return servico.buscar(sessao, organizacao_id)
