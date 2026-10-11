"""Rotas do catalogo de tipos de residuo.

Escrita restrita ao ADMIN para que o catalogo permaneca padronizado; leitura
liberada a qualquer usuario autenticado, porque todos precisam dele para
emitir e consultar manifestos.
"""

from fastapi import APIRouter, status
from sqlalchemy import select

from app.dependencies import PaginaParams, Sessao, UsuarioAdmin, UsuarioAtual
from app.errors import Conflito, RecursoNaoEncontrado
from app.models import TipoResiduo
from app.paginacao import paginar
from app.schemas import Pagina, TipoResiduoAtualizar, TipoResiduoCriar, TipoResiduoSaida

router = APIRouter(prefix="/tipos-residuo", tags=["Tipos de resíduo"])


@router.post(
    "",
    response_model=TipoResiduoSaida,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra um tipo de resíduo (ADMIN)",
)
def criar(dados: TipoResiduoCriar, sessao: Sessao, _: UsuarioAdmin) -> TipoResiduo:
    ja_existe = sessao.scalar(select(TipoResiduo).where(TipoResiduo.codigo == dados.codigo))
    if ja_existe is not None:
        raise Conflito(f"Já existe um tipo de resíduo com o código {dados.codigo}.")

    tipo = TipoResiduo(**dados.model_dump())
    sessao.add(tipo)
    sessao.commit()
    sessao.refresh(tipo)
    return tipo


@router.get(
    "",
    response_model=Pagina[TipoResiduoSaida],
    summary="Lista o catálogo de tipos de resíduo",
)
def listar(sessao: Sessao, paginacao: PaginaParams, _: UsuarioAtual) -> dict:
    consulta = select(TipoResiduo).order_by(TipoResiduo.codigo)
    return paginar(sessao, consulta, paginacao)


@router.put(
    "/{tipo_id}",
    response_model=TipoResiduoSaida,
    summary="Corrige um tipo de resíduo (ADMIN)",
)
def atualizar(
    tipo_id: int, dados: TipoResiduoAtualizar, sessao: Sessao, _: UsuarioAdmin
) -> TipoResiduo:
    """Corrige descrição, classe ou unidade padrão de um tipo do catálogo.

    Os relatórios agrupam pela classe atual do tipo, então uma classe
    corrigida vale também para períodos passados — que é o desejado quando a
    alteração conserta um erro de cadastro.
    """
    tipo = sessao.get(TipoResiduo, tipo_id)
    if tipo is None:
        raise RecursoNaoEncontrado(f"Tipo de resíduo {tipo_id} não encontrado.")

    for campo, valor in dados.model_dump().items():
        setattr(tipo, campo, valor)

    sessao.commit()
    sessao.refresh(tipo)
    return tipo
