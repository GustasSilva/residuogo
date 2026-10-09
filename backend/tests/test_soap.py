"""Testes do web service SOAP.

Os envelopes sao montados a mao e enviados pelo cliente de teste, sem subir um
servidor. Isso mantem os testes rapidos e independentes de rede.

O consumo pelo `zeep` - que le o WSDL e monta a chamada sozinho - e
demonstrado por `clients/soap_client.py`, executado contra o servidor em pe.
O que se verifica aqui e a outra ponta: que o envelope produzido e o
esperado, e que todo erro sai como um SOAP Fault bem formado.
"""

from fastapi.testclient import TestClient
from lxml import etree

from app.enums import StatusManifesto, TipoDestinacao
from app.models import Manifesto
from app.soap.envelope import NS_SERVICO, NS_SOAP

ENDERECO = "/soap/manifesto"

ENVELOPE_CONSULTA = """<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <rgo:ConsultarStatusManifesto xmlns:rgo="{ns}">
      <rgo:numero>{numero}</rgo:numero>
      <rgo:cnpj_consultante>{cnpj}</rgo:cnpj_consultante>
    </rgo:ConsultarStatusManifesto>
  </soap:Body>
</soap:Envelope>
"""


def consultar(cliente: TestClient, numero: str, cnpj: str):
    """Envia uma consulta SOAP e devolve a resposta HTTP."""
    envelope = ENVELOPE_CONSULTA.format(ns=NS_SERVICO, numero=numero, cnpj=cnpj)
    return cliente.post(
        ENDERECO,
        content=envelope.encode("utf-8"),
        headers={"Content-Type": "text/xml; charset=utf-8"},
    )


def ler_xml(resposta) -> etree._Element:
    return etree.fromstring(resposta.content)


def campo(raiz: etree._Element, nome: str) -> str | None:
    """Le o texto de um campo da resposta, pelo nome local."""
    elemento = raiz.find(f".//{{{NS_SERVICO}}}{nome}")
    return None if elemento is None else elemento.text


def ler_falha(resposta) -> tuple[str, str, str]:
    """Extrai (faultcode, faultstring, codigo interno) de um SOAP Fault."""
    raiz = ler_xml(resposta)
    falha = raiz.find(f".//{{{NS_SOAP}}}Fault")
    assert falha is not None, f"esperava um SOAP Fault, veio: {resposta.text[:300]}"

    # faultcode e faultstring nao levam namespace no SOAP 1.1.
    return (
        falha.findtext("faultcode"),
        falha.findtext("faultstring"),
        campo(raiz, "codigo"),
    )


def criar_manifesto(sessao, dados: dict, **ajustes) -> Manifesto:
    """Grava um manifesto diretamente, para os testes de consulta."""
    manifesto = Manifesto(
        gerador_id=dados["gerador"].id,
        transportador_id=dados["transportador"].id,
        destinador_id=dados["destinador"].id,
        status=StatusManifesto.EMITIDO,
        **ajustes,
    )
    sessao.add(manifesto)
    sessao.flush()
    manifesto.numero = f"RGO-{manifesto.emitido_em.year}-{manifesto.id:06d}"
    sessao.commit()
    return manifesto


class TestContratoWsdl:
    def test_wsdl_e_servido_e_e_xml_valido(self, cliente: TestClient) -> None:
        resposta = cliente.get(f"{ENDERECO}?wsdl")

        assert resposta.status_code == 200
        assert "xml" in resposta.headers["content-type"]
        etree.fromstring(resposta.content)  # levanta excecao se nao for XML valido

    def test_wsdl_declara_a_operacao_e_o_endereco(self, cliente: TestClient) -> None:
        raiz = ler_xml(cliente.get(f"{ENDERECO}?wsdl"))
        texto = etree.tostring(raiz, encoding="unicode")

        assert 'name="ConsultarStatusManifesto"' in texto
        assert f'targetNamespace="{NS_SERVICO}"' in texto
        # O endereco publicado tem de ser a URL real, nao o marcador do modelo.
        assert "__URL_DO_SERVICO__" not in texto
        assert ENDERECO in texto


class TestConsultaComSucesso:
    def test_participante_consulta_o_manifesto(
        self, cliente: TestClient, dados: dict, sessao
    ) -> None:
        manifesto = criar_manifesto(sessao, dados)

        resposta = consultar(cliente, manifesto.numero, dados["gerador"].cnpj)

        assert resposta.status_code == 200
        raiz = ler_xml(resposta)
        assert campo(raiz, "numero") == manifesto.numero
        assert campo(raiz, "status") == "EMITIDO"
        assert campo(raiz, "gerador_razao_social") == dados["gerador"].razao_social
        assert campo(raiz, "destinador_razao_social") == dados["destinador"].razao_social

    def test_qualquer_um_dos_tres_participantes_pode_consultar(
        self, cliente: TestClient, dados: dict, sessao
    ) -> None:
        manifesto = criar_manifesto(sessao, dados)

        for participante in ("gerador", "transportador", "destinador"):
            resposta = consultar(cliente, manifesto.numero, dados[participante].cnpj)
            assert resposta.status_code == 200, f"{participante} deveria conseguir consultar"

    def test_cnpj_com_mascara_e_aceito(
        self, cliente: TestClient, dados: dict, sessao
    ) -> None:
        """O numero e o CNPJ costumam ser digitados de um documento impresso."""
        manifesto = criar_manifesto(sessao, dados)

        resposta = consultar(cliente, f"  {manifesto.numero.lower()}  ", "11.222.333/0001-81")

        assert resposta.status_code == 200

    def test_destinacao_ausente_e_omitida_da_resposta(
        self, cliente: TestClient, dados: dict, sessao
    ) -> None:
        """Campo opcional nao enviado vazio: o cliente distingue 'sem valor'."""
        manifesto = criar_manifesto(sessao, dados)

        raiz = ler_xml(consultar(cliente, manifesto.numero, dados["gerador"].cnpj))

        assert campo(raiz, "tipo_destinacao") is None

    def test_destinacao_preenchida_aparece(
        self, cliente: TestClient, dados: dict, sessao
    ) -> None:
        manifesto = criar_manifesto(
            sessao,
            dados,
            tipo_destinacao=TipoDestinacao.RECICLAGEM,
        )

        raiz = ler_xml(consultar(cliente, manifesto.numero, dados["gerador"].cnpj))

        assert campo(raiz, "tipo_destinacao") == "RECICLAGEM"


class TestFalhas:
    def test_manifesto_inexistente_devolve_fault(
        self, cliente: TestClient, dados: dict
    ) -> None:
        resposta = consultar(cliente, "RGO-2026-999999", dados["gerador"].cnpj)

        assert resposta.status_code == 500  # o SOAP 1.1 responde 500 em qualquer Fault
        codigo_soap, mensagem, codigo_interno = ler_falha(resposta)
        assert codigo_soap == "soap:Client"
        assert codigo_interno == "RECURSO_NAO_ENCONTRADO"
        assert "RGO-2026-999999" in mensagem

    def test_cnpj_nao_participante_devolve_fault(
        self, cliente: TestClient, dados: dict, sessao
    ) -> None:
        """A regra de visibilidade do SOAP, equivalente a RN07 do REST."""
        manifesto = criar_manifesto(sessao, dados)
        intruso = dados["transportador_vencido"].cnpj

        resposta = consultar(cliente, manifesto.numero, intruso)

        _, mensagem, codigo_interno = ler_falha(resposta)
        assert codigo_interno == "PERMISSAO_NEGADA"
        assert "não participa" in mensagem

    def test_operacao_desconhecida_devolve_fault(self, cliente: TestClient) -> None:
        envelope = (
            f'<soap:Envelope xmlns:soap="{NS_SOAP}"><soap:Body>'
            f'<rgo:NaoExiste xmlns:rgo="{NS_SERVICO}"/>'
            f"</soap:Body></soap:Envelope>"
        )

        resposta = cliente.post(
            ENDERECO, content=envelope.encode(), headers={"Content-Type": "text/xml"}
        )

        _, _, codigo_interno = ler_falha(resposta)
        assert codigo_interno == "OPERACAO_DESCONHECIDA"

    def test_xml_mal_formado_devolve_fault(self, cliente: TestClient) -> None:
        resposta = cliente.post(
            ENDERECO, content=b"<isso nao e xml", headers={"Content-Type": "text/xml"}
        )

        _, _, codigo_interno = ler_falha(resposta)
        assert codigo_interno == "ENVELOPE_INVALIDO"

    def test_envelope_sem_operacao_devolve_fault(self, cliente: TestClient) -> None:
        envelope = f'<soap:Envelope xmlns:soap="{NS_SOAP}"><soap:Body/></soap:Envelope>'

        resposta = cliente.post(
            ENDERECO, content=envelope.encode(), headers={"Content-Type": "text/xml"}
        )

        _, _, codigo_interno = ler_falha(resposta)
        assert codigo_interno == "ENVELOPE_INVALIDO"

    def test_parametro_faltando_devolve_fault(self, cliente: TestClient, dados: dict) -> None:
        envelope = (
            f'<soap:Envelope xmlns:soap="{NS_SOAP}"><soap:Body>'
            f'<rgo:ConsultarStatusManifesto xmlns:rgo="{NS_SERVICO}">'
            f"<rgo:numero>RGO-2026-000001</rgo:numero>"
            f"</rgo:ConsultarStatusManifesto></soap:Body></soap:Envelope>"
        )

        resposta = cliente.post(
            ENDERECO, content=envelope.encode(), headers={"Content-Type": "text/xml"}
        )

        _, _, codigo_interno = ler_falha(resposta)
        assert codigo_interno == "PARAMETROS_OBRIGATORIOS"


class TestDefesaContraXxe:
    def test_entidade_externa_nao_e_expandida(self, cliente: TestClient) -> None:
        """Defesa contra XXE.

        O envelope declara uma entidade que aponta para um arquivo do sistema.
        Com a expansao de entidades desligada, o conteudo do arquivo nunca
        chega a ser lido - a requisicao falha como envelope invalido.
        """
        ataque = f"""<?xml version="1.0"?>
        <!DOCTYPE dados [<!ENTITY vazamento SYSTEM "file:///etc/passwd">]>
        <soap:Envelope xmlns:soap="{NS_SOAP}"><soap:Body>
          <rgo:ConsultarStatusManifesto xmlns:rgo="{NS_SERVICO}">
            <rgo:numero>&vazamento;</rgo:numero>
            <rgo:cnpj_consultante>11222333000181</rgo:cnpj_consultante>
          </rgo:ConsultarStatusManifesto>
        </soap:Body></soap:Envelope>"""

        resposta = cliente.post(
            ENDERECO, content=ataque.encode(), headers={"Content-Type": "text/xml"}
        )

        assert "root:" not in resposta.text, "o conteúdo do arquivo não pode vazar"
        assert b"Fault" in resposta.content
