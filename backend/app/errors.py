"""Erros do dominio e respostas de erro padronizadas (RFC 7807).

O problema que este modulo resolve: sem padronizacao, uma API devolve erro de
tres formas diferentes (o formato do framework, o da biblioteca de validacao e
o escrito a mao em cada rota), e o cliente precisa saber lidar com todas.

A solucao e a RFC 7807, que define um corpo unico para qualquer erro, servido
com o tipo `application/problem+json`:

    {
      "type":     "https://residuogo.example/erros/transicao-invalida",
      "title":    "Transicao de status invalida",
      "status":   409,
      "detail":   "Manifesto RGO-2026-000012 esta EMITIDO e nao pode ir para RECEBIDO.",
      "instance": "/api/v1/manifestos/12/recebimento",
      "codigo":   "TRANSICAO_INVALIDA",
      "erros":    []
    }

Os quatro primeiros campos sao da norma; `codigo` e `erros` sao extensoes
nossas, permitidas pela RFC. O `codigo` existe para o front-end decidir o que
fazer sem depender do texto da mensagem (que pode mudar), e `erros` lista as
falhas campo por campo nos erros de validacao.

Como funciona: as rotas e servicos apenas levantam as excecoes definidas aqui.
Os handlers registrados por `registrar_handlers()` capturam qualquer excecao
que escape e a traduzem para o formato acima - inclusive as que nao sao
nossas, para que nenhuma resposta de erro fuja do padrao.
"""

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("residuogo")

# Prefixo dos identificadores de tipo de erro. A RFC pede uma URI que
# documente o erro; usamos o dominio reservado `.example` porque o sistema nao
# publica documentacao na internet.
TIPO_BASE = "https://residuogo.example/erros"

MIDIA_PROBLEMA = "application/problem+json"


# ---------------------------------------------------------------------------
# Excecoes do dominio
# ---------------------------------------------------------------------------


class ErroDominio(Exception):
    """Base de todos os erros previstos do sistema.

    Cada subclasse fixa o codigo HTTP, o codigo interno e o titulo; quem
    levanta a excecao informa apenas o `detalhe`, que e a parte especifica
    daquela ocorrencia.

    Levantar uma subclasse destas e a unica forma correta de um servico
    recusar uma operacao: o servico nao monta resposta HTTP nem sabe que
    existe uma API em volta dele.
    """

    status: int = 400
    codigo: str = "ERRO_DE_DOMINIO"
    titulo: str = "Erro de domínio"

    def __init__(self, detalhe: str, erros: list[dict] | None = None) -> None:
        super().__init__(detalhe)
        self.detalhe = detalhe
        self.erros = erros or []


class NaoAutenticado(ErroDominio):
    """Token ausente, expirado ou invalido."""

    status = 401
    codigo = "NAO_AUTENTICADO"
    titulo = "Autenticação necessária"


class PermissaoNegada(ErroDominio):
    """O usuario esta autenticado, mas nao pode executar esta acao.

    Cobre a regra RN01 (apenas a organizacao do papel correto e vinculada ao
    manifesto executa cada transicao) e a RN07 (visibilidade restrita aos
    participantes).
    """

    status = 403
    codigo = "PERMISSAO_NEGADA"
    titulo = "Permissão negada"


class RecursoNaoEncontrado(ErroDominio):
    """O registro pedido nao existe."""

    status = 404
    codigo = "RECURSO_NAO_ENCONTRADO"
    titulo = "Recurso não encontrado"


class Conflito(ErroDominio):
    """A operacao conflita com o estado atual dos dados.

    Usado, por exemplo, quando se tenta cadastrar um CNPJ que ja existe.
    """

    status = 409
    codigo = "CONFLITO"
    titulo = "Conflito com o estado atual"


class TransicaoInvalida(ErroDominio):
    """A mudanca de status pedida nao existe na maquina de estados (RN02)."""

    status = 409
    codigo = "TRANSICAO_INVALIDA"
    titulo = "Transição de status inválida"


class RegraDeNegocio(ErroDominio):
    """Os dados estao bem formados, mas violam uma regra do negocio.

    O codigo 422 (e nao 400) e o apropriado: o servidor entendeu a requisicao
    e a sintaxe esta correta; o que falha e uma condicao do dominio.
    """

    status = 422
    codigo = "REGRA_VIOLADA"
    titulo = "Regra de negócio violada"


class LicencaVencida(RegraDeNegocio):
    """Participante com licenca ambiental fora da validade (RN04)."""

    codigo = "LICENCA_VENCIDA"
    titulo = "Licença ambiental vencida"


class PapelInvalido(RegraDeNegocio):
    """Participante indicado para uma funcao que nao corresponde ao seu papel (RN04)."""

    codigo = "PAPEL_INVALIDO"
    titulo = "Papel da organização inválido"


class ServicoExternoIndisponivel(ErroDominio):
    """Uma API externa (IBGE ou ViaCEP) falhou e nao havia cache para servir."""

    status = 503
    codigo = "SERVICO_EXTERNO_INDISPONIVEL"
    titulo = "Serviço externo indisponível"


# ---------------------------------------------------------------------------
# Montagem da resposta
# ---------------------------------------------------------------------------


def _uri_do_tipo(codigo: str) -> str:
    """Converte o codigo interno na URI exigida pela RFC.

    LICENCA_VENCIDA -> https://residuogo.example/erros/licenca-vencida
    """
    return f"{TIPO_BASE}/{codigo.lower().replace('_', '-')}"


def _resposta_problema(
    request: Request,
    *,
    status: int,
    codigo: str,
    titulo: str,
    detalhe: str,
    erros: list[dict] | None = None,
) -> JSONResponse:
    """Monta a resposta de erro no formato RFC 7807.

    Unico ponto do projeto que constroi corpo de erro. Centralizar aqui e o
    que garante que todas as respostas tenham a mesma forma.
    """
    corpo = {
        "type": _uri_do_tipo(codigo),
        "title": titulo,
        "status": status,
        "detail": detalhe,
        "instance": request.url.path,
        "codigo": codigo,
        "erros": erros or [],
    }
    return JSONResponse(status_code=status, content=corpo, media_type=MIDIA_PROBLEMA)


# Traducao dos erros que o proprio framework levanta (rota inexistente, metodo
# nao permitido) para codigos nossos, de modo que nem esses escapem do padrao.
# Cada entrada traz o codigo interno, o titulo e a mensagem em portugues que
# substitui o texto em ingles do framework.
_ERROS_HTTP = {
    401: (
        "NAO_AUTENTICADO",
        "Autenticação necessária",
        "É preciso autenticar-se para acessar este recurso.",
    ),
    403: (
        "PERMISSAO_NEGADA",
        "Permissão negada",
        "Você não tem permissão para executar esta operação.",
    ),
    404: (
        "RECURSO_NAO_ENCONTRADO",
        "Recurso não encontrado",
        "O endereço solicitado não existe nesta API.",
    ),
    405: (
        "METODO_NAO_PERMITIDO",
        "Método não permitido",
        "O método HTTP utilizado não é aceito neste endereço.",
    ),
    422: ("DADOS_INVALIDOS", "Dados inválidos", "Os dados enviados não são válidos."),
}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def registrar_handlers(app: FastAPI) -> None:
    """Liga os tradutores de excecao a aplicacao.

    Chamada uma vez, na criacao do app (`main.py`). A partir dai nenhuma rota
    precisa tratar erro: basta levantar a excecao adequada.
    """

    @app.exception_handler(ErroDominio)
    async def _dominio(request: Request, exc: ErroDominio) -> JSONResponse:
        """Erros previstos: a mensagem vai inteira para o cliente."""
        logger.info("[%s] %s - %s", request.url.path, exc.codigo, exc.detalhe)
        return _resposta_problema(
            request,
            status=exc.status,
            codigo=exc.codigo,
            titulo=exc.titulo,
            detalhe=exc.detalhe,
            erros=exc.erros,
        )

    @app.exception_handler(RequestValidationError)
    async def _validacao(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Erros de validacao do Pydantic.

        O formato nativo do FastAPI e aninhado e dificil de consumir. Aqui ele
        e achatado em uma lista de `{campo, mensagem}`, que e o que o
        front-end precisa para destacar o input errado.
        """
        erros = [
            {
                # `loc` vem como ("body", "itens", 0, "quantidade_declarada");
                # descartamos o primeiro nivel ("body"/"query"), que diz apenas
                # onde o dado veio, e juntamos o resto no caminho do campo.
                "campo": ".".join(str(parte) for parte in erro["loc"][1:]) or "(corpo)",
                # O Pydantic prefixa com "Value error, " a mensagem de todo
                # validador nosso. Como essas mensagens ja estao escritas em
                # portugues e vao direto para a tela, o prefixo sai aqui.
                "mensagem": erro["msg"].removeprefix("Value error, "),
            }
            for erro in exc.errors()
        ]
        return _resposta_problema(
            request,
            status=422,
            codigo="DADOS_INVALIDOS",
            titulo="Dados inválidos",
            detalhe="Um ou mais campos foram preenchidos incorretamente.",
            erros=erros,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Erros levantados pelo proprio framework (404 de rota, 405 de metodo).

        Quando o framework nao informa uma mensagem propria, ele usa a frase
        padrao do codigo HTTP, em ingles ("Not Found"). Nesse caso a frase e
        trocada pela nossa versao em portugues, para que a API responda em um
        unico idioma.
        """
        codigo, titulo, detalhe_padrao = _ERROS_HTTP.get(
            exc.status_code, ("ERRO_HTTP", "Erro na requisição", "Não foi possível atender à requisição.")
        )

        detalhe = str(exc.detail)
        if detalhe == HTTPStatus(exc.status_code).phrase:
            detalhe = detalhe_padrao

        return _resposta_problema(
            request,
            status=exc.status_code,
            codigo=codigo,
            titulo=titulo,
            detalhe=detalhe,
        )

    @app.exception_handler(Exception)
    async def _inesperado(request: Request, exc: Exception) -> JSONResponse:
        """Qualquer falha nao prevista.

        O cliente recebe uma mensagem generica, sem rastro de pilha nem nome
        de tabela: detalhe tecnico em resposta de erro e informacao util para
        quem quer atacar o sistema. O diagnostico completo vai para o log do
        servidor, junto do id da requisicao, que tambem volta no cabecalho
        `X-Request-Id` - e o que permite ligar a reclamacao do usuario a
        linha certa do log.
        """
        id_requisicao = getattr(request.state, "id_requisicao", "-")
        logger.exception("[%s] falha inesperada em %s", id_requisicao, request.url.path)
        return _resposta_problema(
            request,
            status=500,
            codigo="ERRO_INTERNO",
            titulo="Erro interno do servidor",
            detalhe=(
                "Ocorreu uma falha inesperada. Informe o código "
                f"{id_requisicao} ao suporte técnico."
            ),
        )
