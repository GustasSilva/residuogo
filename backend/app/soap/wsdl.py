"""O documento WSDL que descreve o servico SOAP.

WSDL (Web Services Description Language) e o contrato do servico, em XML. E o
equivalente SOAP do que o OpenAPI/Swagger e para o REST, com uma diferenca
importante: o WSDL e lido por programa. Um cliente como o `zeep` baixa este
documento e monta sozinho os metodos Python correspondentes - nao e preciso
escrever codigo de serializacao no cliente.

O documento se le de baixo para cima, porque cada secao usa a anterior:

* `types`    - define, em XML Schema, o formato dos dados que entram e saem;
* `message`  - da nome aos documentos de entrada, de saida e de falha;
* `portType` - agrupa as operacoes: para cada uma, qual mensagem entra, qual
               sai e qual falha pode ocorrer. E a interface abstrata, sem
               dizer como os dados viajam;
* `binding`  - define o "como": SOAP sobre HTTP, estilo `document`, corpo
               `literal` (o XML na rede e exatamente o descrito no schema);
* `service`  - diz o endereco onde o servico atende.

O endereco e a unica parte que nao pode ser fixa no arquivo: ele depende de
onde a aplicacao esta rodando (`localhost` em desenvolvimento, outro host na
apresentacao). Por isso o WSDL e montado a cada requisicao, com a URL real.
"""

from app.soap.envelope import NS_SERVICO

# Namespaces da propria linguagem WSDL e do seu complemento para SOAP.
NS_WSDL = "http://schemas.xmlsoap.org/wsdl/"
NS_WSDL_SOAP = "http://schemas.xmlsoap.org/wsdl/soap/"
NS_XSD = "http://www.w3.org/2001/XMLSchema"

# Transporte declarado no binding: SOAP sobre HTTP.
TRANSPORTE_HTTP = "http://schemas.xmlsoap.org/soap/http"

OPERACAO = "ConsultarStatusManifesto"
ACAO_SOAP = f"{NS_SERVICO}/{OPERACAO}"

_MODELO_WSDL = f"""<?xml version="1.0" encoding="UTF-8"?>
<definitions xmlns="{NS_WSDL}"
             xmlns:soap="{NS_WSDL_SOAP}"
             xmlns:xsd="{NS_XSD}"
             xmlns:rgo="{NS_SERVICO}"
             targetNamespace="{NS_SERVICO}"
             name="ManifestoService">

  <!-- ============================================================
       types: o formato dos dados, em XML Schema.
       ============================================================ -->
  <types>
    <xsd:schema targetNamespace="{NS_SERVICO}" elementFormDefault="qualified">

      <!-- Entrada da operacao. -->
      <xsd:element name="{OPERACAO}">
        <xsd:complexType>
          <xsd:sequence>
            <xsd:element name="numero" type="xsd:string"/>
            <xsd:element name="cnpj_consultante" type="xsd:string"/>
          </xsd:sequence>
        </xsd:complexType>
      </xsd:element>

      <!-- Saida da operacao. `tipo_destinacao` e opcional porque so existe
           depois de o manifesto ser destinado. -->
      <xsd:element name="{OPERACAO}Response">
        <xsd:complexType>
          <xsd:sequence>
            <xsd:element name="numero" type="xsd:string"/>
            <xsd:element name="status" type="xsd:string"/>
            <xsd:element name="gerador_razao_social" type="xsd:string"/>
            <xsd:element name="destinador_razao_social" type="xsd:string"/>
            <xsd:element name="tipo_destinacao" type="xsd:string" minOccurs="0"/>
            <xsd:element name="atualizado_em" type="xsd:dateTime"/>
          </xsd:sequence>
        </xsd:complexType>
      </xsd:element>

      <!-- Conteudo do campo `detail` de um SOAP Fault. -->
      <xsd:element name="ManifestoFault">
        <xsd:complexType>
          <xsd:sequence>
            <xsd:element name="codigo" type="xsd:string"/>
            <xsd:element name="mensagem" type="xsd:string"/>
          </xsd:sequence>
        </xsd:complexType>
      </xsd:element>

    </xsd:schema>
  </types>

  <!-- ============================================================
       message: nomeia os documentos que trafegam.
       ============================================================ -->
  <message name="{OPERACAO}Entrada">
    <part name="parametros" element="rgo:{OPERACAO}"/>
  </message>
  <message name="{OPERACAO}Saida">
    <part name="resultado" element="rgo:{OPERACAO}Response"/>
  </message>
  <message name="ManifestoFalha">
    <part name="falha" element="rgo:ManifestoFault"/>
  </message>

  <!-- ============================================================
       portType: a interface abstrata do servico.
       ============================================================ -->
  <portType name="ManifestoPortType">
    <operation name="{OPERACAO}">
      <documentation>
        Consulta a situacao de um manifesto. Apenas organizacoes participantes
        do manifesto (gerador, transportador ou destinador) podem consultar.
      </documentation>
      <input message="rgo:{OPERACAO}Entrada"/>
      <output message="rgo:{OPERACAO}Saida"/>
      <fault name="ManifestoFalha" message="rgo:ManifestoFalha"/>
    </operation>
  </portType>

  <!-- ============================================================
       binding: como a interface viaja na rede.
       ============================================================ -->
  <binding name="ManifestoBinding" type="rgo:ManifestoPortType">
    <soap:binding style="document" transport="{TRANSPORTE_HTTP}"/>
    <operation name="{OPERACAO}">
      <soap:operation soapAction="{ACAO_SOAP}"/>
      <input>
        <soap:body use="literal"/>
      </input>
      <output>
        <soap:body use="literal"/>
      </output>
      <fault name="ManifestoFalha">
        <soap:fault name="ManifestoFalha" use="literal"/>
      </fault>
    </operation>
  </binding>

  <!-- ============================================================
       service: onde o servico atende. O endereco e preenchido em
       tempo de execucao com a URL real desta instalacao.
       ============================================================ -->
  <service name="ManifestoService">
    <documentation>Servico SOAP de consulta de manifestos do ResiduoGO.</documentation>
    <port name="ManifestoPort" binding="rgo:ManifestoBinding">
      <soap:address location="__URL_DO_SERVICO__"/>
    </port>
  </service>

</definitions>
"""


def gerar_wsdl(url_do_servico: str) -> bytes:
    """Devolve o WSDL com o endereco real do servico preenchido.

    O documento e montado uma unica vez, quando o modulo e importado: os
    namespaces e o nome da operacao sao constantes. Apenas o endereco muda a
    cada requisicao, e por isso ele e o unico marcador substituido aqui.
    """
    return _MODELO_WSDL.replace("__URL_DO_SERVICO__", url_do_servico).encode("utf-8")
