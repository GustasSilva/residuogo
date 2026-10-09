"""Hash de senha e emissao de tokens JWT.

Duas responsabilidades separadas:

* senhas - guardadas apenas como hash bcrypt, que e irreversivel: o sistema
  nunca consegue descobrir a senha original, apenas conferir se uma senha
  informada gera o mesmo hash;
* tokens - apos o login o servidor emite um JWT assinado. Nas chamadas
  seguintes o cliente envia esse token, e o servidor confia nele porque
  confere a assinatura, sem precisar guardar sessao em memoria.
"""

from datetime import timedelta

import bcrypt
import jwt

from app.config import config
from app.database import agora_utc

# O bcrypt ignora silenciosamente o que passa de 72 bytes. Recusar a senha e
# melhor que aceitar uma senha longa e validar apenas o inicio dela.
LIMITE_BYTES_SENHA = 72


def gerar_hash_senha(senha: str) -> str:
    """Transforma a senha em um hash bcrypt pronto para ser gravado.

    O bcrypt gera um "sal" aleatorio a cada chamada e o embute no proprio
    hash. Por isso a mesma senha produz hashes diferentes - o que impede
    descobrir que dois usuarios usam a mesma senha so comparando a tabela.
    """
    senha_bytes = senha.encode("utf-8")
    if len(senha_bytes) > LIMITE_BYTES_SENHA:
        raise ValueError(f"A senha nao pode passar de {LIMITE_BYTES_SENHA} bytes.")
    return bcrypt.hashpw(senha_bytes, bcrypt.gensalt()).decode("utf-8")


def senha_confere(senha: str, hash_armazenado: str) -> bool:
    """Confere uma senha contra o hash gravado no banco."""
    senha_bytes = senha.encode("utf-8")
    if len(senha_bytes) > LIMITE_BYTES_SENHA:
        return False
    try:
        return bcrypt.checkpw(senha_bytes, hash_armazenado.encode("utf-8"))
    except ValueError:
        # Hash malformado no banco: trata como senha incorreta em vez de
        # derrubar a requisicao com erro 500.
        return False


def criar_token(usuario_id: int) -> str:
    """Emite um JWT que identifica o usuario pelo tempo configurado.

    O conteudo do token e publico (qualquer pessoa consegue ler), por isso
    carrega apenas o id do usuario. O que o protege e a assinatura: sem o
    segredo nao e possivel alterar o id sem invalidar o token.
    """
    emitido_em = agora_utc()
    conteudo = {
        "sub": str(usuario_id),  # "subject": de quem e o token
        "iat": emitido_em,  # "issued at": quando foi emitido
        "exp": emitido_em + timedelta(minutes=config.jwt_expiracao_minutos),  # expiracao
    }
    return jwt.encode(conteudo, config.jwt_segredo, algorithm=config.jwt_algoritmo)


def ler_token(token: str) -> int:
    """Confere a assinatura e a validade do token e devolve o id do usuario.

    Levanta `jwt.InvalidTokenError` (ou uma subclasse, como
    `ExpiredSignatureError`) se o token foi alterado, expirou ou nao tem o
    formato esperado. Quem chama decide o que responder ao cliente.
    """
    conteudo = jwt.decode(token, config.jwt_segredo, algorithms=[config.jwt_algoritmo])
    identificador = conteudo.get("sub")
    if identificador is None:
        raise jwt.InvalidTokenError("Token sem identificacao de usuario.")
    return int(identificador)
