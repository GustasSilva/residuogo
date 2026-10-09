"""Dependencias injetadas nas rotas.

O FastAPI resolve automaticamente os parametros de uma rota que estejam
anotados com `Depends`. Isso permite que cada rota declare *o que precisa*
(uma sessao de banco, o usuario autenticado, o usuario administrador) sem
saber *como* aquilo e obtido.

O ganho pratico aparece nas rotas: `def listar(usuario: UsuarioAdmin)` ja
chega com a verificacao de perfil feita, e nenhuma rota repete codigo de
autenticacao.
"""

from collections.abc import Generator
from typing import Annotated

import jwt
from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.errors import NaoAutenticado, PermissaoNegada
from app.models import Usuario
from app.security import ler_token

# `auto_error=False` desliga a resposta de erro propria do FastAPI para que o
# erro seja levantado por nos e saia no formato RFC 7807, como todos os
# outros. Sem isso, a falta do token produziria uma resposta em formato
# diferente do resto da API.
esquema_bearer = HTTPBearer(
    auto_error=False,
    description="Token devolvido por POST /api/v1/auth/login.",
)


def obter_sessao() -> Generator[Session, None, None]:
    """Abre uma sessao de banco para a requisicao e a fecha no fim.

    O `yield` entrega a sessao para a rota; o `finally` roda depois de a
    resposta ser montada, inclusive quando a rota levanta excecao. E isso que
    garante que nenhuma conexao fique aberta.
    """
    sessao = SessionLocal()
    try:
        yield sessao
    finally:
        sessao.close()


Sessao = Annotated[Session, Depends(obter_sessao)]


def usuario_autenticado(
    credenciais: Annotated[HTTPAuthorizationCredentials | None, Depends(esquema_bearer)],
    sessao: Sessao,
) -> Usuario:
    """Identifica o usuario a partir do token enviado no cabecalho.

    Recusa a requisicao em quatro situacoes, todas com 401: token ausente,
    token invalido ou expirado, usuario que nao existe mais e usuario
    desativado. A mensagem e deliberadamente parecida nos casos de token, para
    nao revelar a quem tenta adivinhar se um token chegou a ser valido.
    """
    if credenciais is None:
        raise NaoAutenticado("Envie o token no cabeçalho Authorization: Bearer <token>.")

    try:
        usuario_id = ler_token(credenciais.credentials)
    except jwt.ExpiredSignatureError:
        raise NaoAutenticado("Sessão expirada. Faça login novamente.") from None
    except jwt.InvalidTokenError:
        raise NaoAutenticado("Token inválido.") from None

    usuario = sessao.get(Usuario, usuario_id)
    if usuario is None:
        raise NaoAutenticado("Token inválido.")
    if not usuario.ativo:
        raise NaoAutenticado("Usuário desativado.")

    return usuario


UsuarioAtual = Annotated[Usuario, Depends(usuario_autenticado)]


def usuario_administrador(usuario: UsuarioAtual) -> Usuario:
    """Restringe a rota ao perfil ADMIN.

    Observe que esta dependencia depende de outra (`UsuarioAtual`): o FastAPI
    resolve a cadeia inteira, de modo que a rota so recebe o usuario depois de
    autenticado *e* verificado.
    """
    if not usuario.e_admin:
        raise PermissaoNegada("Esta operação é restrita a administradores.")
    return usuario


UsuarioAdmin = Annotated[Usuario, Depends(usuario_administrador)]


class ParametrosPagina:
    """Parametros de paginacao comuns a todas as listagens.

    Reunidos em uma classe para que cada rota declare apenas
    `paginacao: PaginaParams` em vez de repetir os dois parametros de consulta.
    O limite maximo de 100 registros por pagina protege o servidor de uma
    requisicao que tentasse carregar a tabela inteira.
    """

    def __init__(
        self,
        pagina: Annotated[int, Query(ge=1, description="Pagina atual, comecando em 1.")] = 1,
        tamanho: Annotated[int, Query(ge=1, le=100, description="Registros por pagina.")] = 20,
    ) -> None:
        self.pagina = pagina
        self.tamanho = tamanho

    @property
    def deslocamento(self) -> int:
        """Quantos registros pular na consulta SQL (clausula OFFSET)."""
        return (self.pagina - 1) * self.tamanho


PaginaParams = Annotated[ParametrosPagina, Depends()]
