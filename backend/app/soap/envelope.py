"""Leitura e escrita do envelope SOAP 1.1.

Este modulo e a tradutura entre XML e Python: ele nao conhece manifesto nem
banco de dados, apenas a estrutura de uma mensagem SOAP.

Um envelope SOAP 1.1 e sempre assim:

    <soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
      <soap:Body>
        <rgo:ConsultarStatusManifesto xmlns:rgo="http://residuogo.example/soap/manifesto">
          <rgo:numero>RGO-2026-000001</rgo:numero>
          <rgo:cnpj_consultante>11222333000181</rgo:cnpj_consultante>
        </rgo:ConsultarStatusManifesto>
      </soap:Body>
    </soap:Envelope>

O `Envelope` e o involucro; o `Body` carrega a mensagem; o primeiro elemento
dentro do `Body` nomeia a operacao a executar e seus filhos sao os parametros.
Quando algo da errado, o `Body` carrega um `Fault` em vez da resposta - o
equivalente SOAP de um codigo de erro HTTP.
"""

from lxml import etree

# Namespace do envelope, fixado pela especificacao SOAP 1.1. Nao pode mudar:
# e por ele que o cliente reconhece a mensagem como SOAP.
NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"

# Namespace do nosso servico. Identifica as mensagens do ResiduoGO e separa
# nossos elementos de elementos de mesmo nome de qualquer outro servico.
NS_SERVICO = "http://residuogo.example/soap/manifesto"

PREFIXOS = {"soap": NS_SOAP, "rgo": NS_SERVICO}

# Content-Type exigido pelo SOAP 1.1 (o SOAP 1.2 usa application/soap+xml).
MIDIA_SOAP = "text/xml; charset=utf-8"


class EnvelopeInvalido(Exception):
    """A mensagem recebida nao e um envelope SOAP utilizavel."""


def _leitor_seguro() -> etree.XMLParser:
    """Cria o leitor de XML com as defesas necessarias ligadas.

    XML aceita declarar entidades que o leitor expande ao processar o
    documento. Um atacante pode usar isso para fazer o servidor ler arquivos
    locais ou abrir conexoes de rede - os ataques conhecidos como XXE
    (XML External Entity) e "billion laughs".

    Como este endpoint recebe XML de fora, as tres defesas sao obrigatorias:
    nao resolver entidades, nao carregar DTD e nao acessar a rede.
    """
    return etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)


def extrair_operacao(mensagem: bytes) -> tuple[str, dict[str, str]]:
    """Le o envelope recebido e devolve o nome da operacao e seus parametros.

    Devolve, para o exemplo do inicio do modulo:

        ("ConsultarStatusManifesto",
         {"numero": "RGO-2026-000001", "cnpj_consultante": "11222333000181"})

    A operacao e identificada pelo nome do elemento dentro do `Body`, e nao
    pelo cabecalho HTTP `SOAPAction`: o cabecalho e opcional em muitos
    clientes, enquanto o elemento esta sempre presente.
    """
    try:
        envelope = etree.fromstring(mensagem, parser=_leitor_seguro())
    except etree.XMLSyntaxError as erro:
        raise EnvelopeInvalido(f"XML mal formado: {erro}") from erro

    if etree.QName(envelope).localname != "Envelope":
        raise EnvelopeInvalido("O elemento raiz da mensagem deve ser soap:Envelope.")

    corpo = envelope.find(f"{{{NS_SOAP}}}Body")
    if corpo is None:
        raise EnvelopeInvalido("O envelope não contém soap:Body.")

    # `len()` em um elemento lxml conta os filhos, nao caracteres.
    elementos = [filho for filho in corpo if isinstance(filho.tag, str)]
    if not elementos:
        raise EnvelopeInvalido("O soap:Body está vazio: nenhuma operação foi informada.")

    chamada = elementos[0]
    operacao = etree.QName(chamada).localname

    parametros = {
        etree.QName(parametro).localname: (parametro.text or "").strip()
        for parametro in chamada
        if isinstance(parametro.tag, str)
    }

    return operacao, parametros


def _novo_envelope() -> tuple[etree._Element, etree._Element]:
    """Cria um envelope vazio e devolve a raiz e o `Body`, prontos para uso."""
    envelope = etree.Element(f"{{{NS_SOAP}}}Envelope", nsmap=PREFIXOS)
    corpo = etree.SubElement(envelope, f"{{{NS_SOAP}}}Body")
    return envelope, corpo


def _serializar(envelope: etree._Element) -> bytes:
    return etree.tostring(envelope, xml_declaration=True, encoding="UTF-8", pretty_print=True)


def montar_resposta(operacao: str, campos: dict[str, str | None]) -> bytes:
    """Monta o envelope de resposta de uma operacao bem-sucedida.

    Por convencao do WSDL, o elemento de resposta e o nome da operacao
    seguido de `Response`. Campos nulos sao omitidos, e nao enviados vazios,
    porque o esquema os declara como opcionais - assim o cliente distingue
    "sem valor" de "valor em branco".
    """
    envelope, corpo = _novo_envelope()
    resposta = etree.SubElement(corpo, f"{{{NS_SERVICO}}}{operacao}Response")

    for nome, valor in campos.items():
        if valor is None:
            continue
        etree.SubElement(resposta, f"{{{NS_SERVICO}}}{nome}").text = str(valor)

    return _serializar(envelope)


def montar_falha(mensagem: str, codigo: str, *, culpa_do_cliente: bool = True) -> bytes:
    """Monta um SOAP Fault, a forma padrao de relatar erro em SOAP.

    O `faultcode` tem valores definidos pela especificacao: `soap:Client`
    quando a mensagem recebida esta errada (manifesto inexistente, CNPJ sem
    permissao) e `soap:Server` quando a falha e do servidor. E o equivalente a
    diferenca entre os codigos HTTP 4xx e 5xx.

    Os tres elementos `faultcode`, `faultstring` e `detail` nao levam
    namespace: no SOAP 1.1 eles sao deliberadamente sem qualificacao.

    Dentro de `detail` vai o codigo interno do erro, o mesmo vocabulario
    usado pelas respostas REST (`codigo` na RFC 7807), para que os dois
    servicos relatem o mesmo problema com o mesmo nome.
    """
    envelope, corpo = _novo_envelope()
    falha = etree.SubElement(corpo, f"{{{NS_SOAP}}}Fault")

    # O conteudo e um QName: o prefixo "soap" ja esta declarado no envelope.
    etree.SubElement(falha, "faultcode").text = "soap:Client" if culpa_do_cliente else "soap:Server"
    etree.SubElement(falha, "faultstring").text = mensagem

    detalhe = etree.SubElement(falha, "detail")
    erro = etree.SubElement(detalhe, f"{{{NS_SERVICO}}}ManifestoFault")
    etree.SubElement(erro, f"{{{NS_SERVICO}}}codigo").text = codigo
    etree.SubElement(erro, f"{{{NS_SERVICO}}}mensagem").text = mensagem

    return _serializar(envelope)
