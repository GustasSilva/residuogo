"""Rotas de autenticacao: login, usuario logado e troca da propria senha."""

from fastapi import APIRouter, status
from sqlalchemy import select

from app.config import config
from app.dependencies import Sessao, UsuarioAtual
from app.errors import NaoAutenticado
from app.models import Usuario
from app.schemas import LoginEntrada, TokenSaida, TrocaDeSenhaEntrada, UsuarioLogadoSaida
from app.security import criar_token, senha_confere
from app.services import usuarios as servico_usuarios

router = APIRouter(prefix="/auth", tags=["Autenticação"])


@router.post(
    "/login",
    response_model=TokenSaida,
    status_code=status.HTTP_200_OK,
    summary="Autentica o usuário e devolve o token de acesso",
)
def login(dados: LoginEntrada, sessao: Sessao) -> TokenSaida:
    """Troca e-mail e senha por um token JWT.

    A mesma mensagem de erro e usada para e-mail inexistente e para senha
    errada. Diferenciar as duas situacoes permitiria descobrir quais e-mails
    estao cadastrados no sistema testando um a um.
    """
    # O e-mail e comparado em minusculas porque "Joao@x.com" e "joao@x.com"
    # sao o mesmo endereco; o cadastro tambem grava em minusculas.
    usuario = sessao.scalar(select(Usuario).where(Usuario.email == dados.email.lower()))

    if usuario is None or not senha_confere(dados.senha, usuario.senha_hash):
        raise NaoAutenticado("E-mail ou senha incorretos.")

    if not usuario.ativo:
        raise NaoAutenticado("Usuário desativado. Procure o administrador.")

    return TokenSaida(
        token=criar_token(usuario.id),
        expira_em_minutos=config.jwt_expiracao_minutos,
    )


@router.get(
    "/me",
    response_model=UsuarioLogadoSaida,
    summary="Dados do usuário autenticado e da organização dele",
)
def usuario_logado(usuario: UsuarioAtual) -> Usuario:
    """Devolve quem esta logado.

    O front-end chama esta rota ao abrir a aplicacao: e dela que sai o papel
    da organizacao, que determina quais acoes aparecem em cada manifesto.
    """
    return usuario


@router.put(
    "/senha",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Troca a senha do usuário autenticado",
)
def trocar_senha(dados: TrocaDeSenhaEntrada, sessao: Sessao, usuario: UsuarioAtual) -> None:
    """Exige a senha atual; o token em uso continua valendo depois da troca."""
    servico_usuarios.trocar_senha(sessao, usuario, dados)
