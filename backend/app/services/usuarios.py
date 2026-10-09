"""Regras de negocio dos usuarios."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import Conflito
from app.models import Usuario
from app.schemas import UsuarioCriar
from app.security import gerar_hash_senha
from app.services import organizacoes as servico_organizacoes


def criar(sessao: Session, dados: UsuarioCriar) -> Usuario:
    """Cadastra um usuario, convertendo a senha em hash antes de gravar.

    A coerencia entre perfil e vinculo com organizacao (ADMIN sem organizacao,
    USUARIO com organizacao) ja foi validada pelo schema de entrada. O que
    cabe aqui e o que depende do banco: e-mail repetido e organizacao
    inexistente.
    """
    email = dados.email.lower()

    ja_existe = sessao.scalar(select(Usuario).where(Usuario.email == email))
    if ja_existe is not None:
        raise Conflito(f"Já existe um usuário cadastrado com o e-mail {email}.")

    if dados.organizacao_id is not None:
        # Levanta 404 se a organizacao nao existir, antes de tentar gravar.
        servico_organizacoes.buscar(sessao, dados.organizacao_id)

    usuario = Usuario(
        nome=dados.nome,
        email=email,
        senha_hash=gerar_hash_senha(dados.senha),
        perfil=dados.perfil,
        organizacao_id=dados.organizacao_id,
    )
    sessao.add(usuario)
    sessao.commit()
    sessao.refresh(usuario)
    return usuario
