"""Endpoint do servico SOAP.

Duas rotas no mesmo endereco, separadas pelo metodo HTTP - como manda a
pratica em SOAP:

* `GET  /soap/manifesto` (ou `?wsdl`) devolve o contrato WSDL;
* `POST /soap/manifesto` executa uma operacao.

Esta camada e fina de proposito: ela traduz XML para chamada de servico e o
resultado (ou o erro) de volta para XML. A regra de negocio fica em
`services/manifestos.py`, a mesma que o REST usa - de modo que os dois
servicos nunca divirjam no comportamento, apenas no formato da mensagem.
"""

from fastapi import APIRouter, Request, Response

from app.dependencies import Sessao
from app.errors import ErroDominio
from app.services import manifestos as servico
from app.soap.envelope import (
    MIDIA_SOAP,
    EnvelopeInvalido,
    extrair_operacao,
    montar_falha,
    montar_resposta,
)
from app.soap.wsdl import OPERACAO, gerar_wsdl

router = APIRouter(prefix="/soap", tags=["Web Service SOAP"])

# O SOAP 1.1 responde a um Fault com o codigo HTTP 500, mesmo quando a causa e
# um erro do cliente. Quem distingue os dois casos e o `faultcode` dentro do
# envelope (soap:Client ou soap:Server), nao o codigo HTTP.
HTTP_FALHA_SOAP = 500


def _resposta_soap(conteudo: bytes, status: int = 200) -> Response:
    return Response(content=conteudo, media_type=MIDIA_SOAP, status_code=status)


@router.get(
    "/manifesto",
    summary="Contrato WSDL do serviço SOAP",
    response_class=Response,
)
def obter_wsdl(request: Request) -> Response:
    """Devolve o WSDL do servico.

    O endereco publicado dentro do documento e a propria URL desta
    requisicao, sem a query string. Assim o WSDL funciona tanto em
    `localhost` quanto em qualquer outro host, sem configuracao.
    """
    url_do_servico = str(request.url.replace(query=""))
    return Response(content=gerar_wsdl(url_do_servico), media_type="text/xml; charset=utf-8")


@router.post(
    "/manifesto",
    summary="Executa uma operação SOAP (corpo: envelope XML)",
    response_class=Response,
)
async def atender(request: Request, sessao: Sessao) -> Response:
    """Recebe um envelope SOAP, executa a operacao e devolve a resposta.

    A sequencia de verificacoes vai do envelope para o conteudo: primeiro se a
    mensagem e XML valido, depois se a operacao existe, depois se os
    parametros vieram, e so no fim a regra de negocio. Cada falha produz um
    SOAP Fault com codigo proprio, o que permite ao cliente distinguir
    "mensagem mal formada" de "manifesto inexistente".
    """
    mensagem = await request.body()

    try:
        operacao, parametros = extrair_operacao(mensagem)
    except EnvelopeInvalido as erro:
        return _resposta_soap(
            montar_falha(str(erro), "ENVELOPE_INVALIDO"), HTTP_FALHA_SOAP
        )

    if operacao != OPERACAO:
        return _resposta_soap(
            montar_falha(
                f"Operação '{operacao}' não existe neste serviço. "
                f"A operação disponível é '{OPERACAO}'.",
                "OPERACAO_DESCONHECIDA",
            ),
            HTTP_FALHA_SOAP,
        )

    numero = parametros.get("numero", "")
    cnpj_consultante = parametros.get("cnpj_consultante", "")

    if not numero or not cnpj_consultante:
        return _resposta_soap(
            montar_falha(
                "Os parâmetros 'numero' e 'cnpj_consultante' são obrigatórios.",
                "PARAMETROS_OBRIGATORIOS",
            ),
            HTTP_FALHA_SOAP,
        )

    try:
        manifesto = servico.consultar_por_numero(sessao, numero, cnpj_consultante)
    except ErroDominio as erro:
        # As excecoes do dominio sao as mesmas levantadas pelo REST. Aqui elas
        # viram Fault; la, respostas RFC 7807. O `codigo` e identico nos dois
        # formatos, de modo que o mesmo erro tem sempre o mesmo nome.
        return _resposta_soap(
            montar_falha(erro.detalhe, erro.codigo, culpa_do_cliente=erro.status < 500),
            HTTP_FALHA_SOAP,
        )

    return _resposta_soap(
        montar_resposta(
            OPERACAO,
            {
                "numero": manifesto.numero,
                "status": manifesto.status.value,
                "gerador_razao_social": manifesto.gerador.razao_social,
                "destinador_razao_social": manifesto.destinador.razao_social,
                # Ausente enquanto o manifesto nao foi destinado; o schema do
                # WSDL declara o campo como opcional justamente por isso.
                "tipo_destinacao": (
                    manifesto.tipo_destinacao.value if manifesto.tipo_destinacao else None
                ),
                "atualizado_em": manifesto.atualizado_em.isoformat(),
            },
        )
    )
