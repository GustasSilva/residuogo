"""Regras de negocio dos usuarios."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import Conflito, RecursoNaoEncontrado, RegraDeNegocio
from app.models import Usuario
from app.schemas import TrocaDeSenhaEntrada, UsuarioAtualizar, UsuarioCriar
from app.security import gerar_hash_senha, senha_confere
from app.services import organizacoes as servico_organizacoes


def buscar(sessao: Session, usuario_id: int) -> Usuario:
    """Carrega um usuario pelo id ou levanta 404."""
    usuario = sessao.get(Usuario, usuario_id)
    if usuario is None:
        raise RecursoNaoEncontrado(f"Usuário {usuario_id} não encontrado.")
    return usuario


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


def atualizar(
    sessao: Session, administrador: Usuario, usuario_id: int, dados: UsuarioAtualizar
) -> Usuario:
    """Altera nome e situacao de um usuario e, se pedido, redefine a senha.

    Desativar tem efeito imediato: a autenticacao confere a situacao a cada
    requisicao, entao o token que o usuario ja tinha deixa de valer.

    O administrador nao pode desativar a si mesmo: se fosse o unico, o sistema
    ficaria sem ninguem capaz de reativa-lo.
    """
    usuario = buscar(sessao, usuario_id)

    if usuario.id == administrador.id and not dados.ativo:
        raise RegraDeNegocio("Você não pode desativar o seu próprio usuário.")

    usuario.nome = dados.nome
    usuario.ativo = dados.ativo
    if dados.nova_senha is not None:
        usuario.senha_hash = gerar_hash_senha(dados.nova_senha)

    sessao.commit()
    sessao.refresh(usuario)
    return usuario


def trocar_senha(sessao: Session, usuario: Usuario, dados: TrocaDeSenhaEntrada) -> None:
    """Troca a senha do proprio usuario, exigindo a senha atual.

    Sem essa exigencia, quem encontrasse a sessao aberta em um computador
    poderia trocar a senha e tomar a conta.

    A senha atual errada e 422, e nao 401: o usuario esta autenticado, o que
    esta errado e um campo do formulario. Um 401 faria o front-end encerrar
    a sessao.
    """
    if not senha_confere(dados.senha_atual, usuario.senha_hash):
        raise RegraDeNegocio("A senha atual não confere.")

    usuario.senha_hash = gerar_hash_senha(dados.nova_senha)
    sessao.commit()
