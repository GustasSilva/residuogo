"""Rotas de cadastro de usuarios. Restritas ao ADMIN.

Nao existe auto-cadastro: quem opera em nome de uma organizacao precisa ser
cadastrado por um administrador, que e quem confirma o vinculo entre a pessoa
e a empresa.
"""

from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.dependencies import PaginaParams, Sessao, UsuarioAdmin
from app.models import Usuario
from app.paginacao import paginar
from app.schemas import Pagina, UsuarioCriar, UsuarioSaida
from app.services import usuarios as servico

router = APIRouter(prefix="/usuarios", tags=["Usuários"])


@router.post(
    "",
    response_model=UsuarioSaida,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastra um usuário (ADMIN)",
)
def criar(dados: UsuarioCriar, sessao: Sessao, _: UsuarioAdmin) -> Usuario:
    return servico.criar(sessao, dados)


@router.get(
    "",
    response_model=Pagina[UsuarioSaida],
    summary="Lista usuários (ADMIN)",
)
def listar(
    sessao: Sessao,
    paginacao: PaginaParams,
    _: UsuarioAdmin,
    organizacao_id: Annotated[
        int | None, Query(description="Filtra os usuários de uma organização.")
    ] = None,
) -> dict:
    consulta = select(Usuario)
    if organizacao_id is not None:
        consulta = consulta.where(Usuario.organizacao_id == organizacao_id)
    return paginar(sessao, consulta.order_by(Usuario.nome), paginacao)
