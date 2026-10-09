"""Cliente do servico SOAP do ResiduoGO.

Demonstra o consumo do web service SOAP por um programa externo, usando a
biblioteca `zeep`.

O ponto que esta demonstracao evidencia: em nenhum lugar deste arquivo existe
XML. O `zeep` baixa o WSDL, le o contrato e constroi sozinho os metodos
correspondentes - por isso a chamada se parece com a de uma funcao Python
comum. E o WSDL que torna isso possivel, e e essa a diferenca pratica entre
SOAP e REST: o contrato SOAP e legivel por maquina.

Uso, com o servidor rodando:

    python clients/soap_client.py                       # consulta de exemplo
    python clients/soap_client.py RGO-2026-000001 11222333000181
    python clients/soap_client.py --url http://outro-host:8000/soap/manifesto

Para observar o tratamento de erro (SOAP Fault), basta informar um numero de
manifesto inexistente ou um CNPJ que nao participe do manifesto.
"""

import argparse
import sys

from zeep import Client
from zeep.exceptions import Fault

WSDL_PADRAO = "http://127.0.0.1:8000/soap/manifesto?wsdl"


def consultar(url_wsdl: str, numero: str, cnpj: str) -> int:
    """Consulta um manifesto e imprime o resultado.

    Devolve o codigo de saida do processo: 0 em caso de sucesso e 1 em caso de
    falha, para que o script possa ser usado dentro de outro automatismo.
    """
    print(f"Lendo o contrato em {url_wsdl}")

    try:
        cliente = Client(url_wsdl)
    except Exception as erro:
        print(f"\nNão foi possível ler o WSDL: {erro}", file=sys.stderr)
        print("O servidor está rodando? (uvicorn app.main:app)", file=sys.stderr)
        return 1

    print(f"Consultando o manifesto {numero} como o CNPJ {cnpj}\n")

    try:
        # Chamada da operacao descrita no WSDL. Os nomes dos argumentos sao os
        # mesmos declarados no XML Schema do contrato.
        resposta = cliente.service.ConsultarStatusManifesto(
            numero=numero,
            cnpj_consultante=cnpj,
        )
    except Fault as falha:
        # Um SOAP Fault chega ao Python como excecao. `message` traz o
        # `faultstring` e `code`, o `faultcode` - o equivalente SOAP de um
        # erro 4xx/5xx do REST.
        print("O serviço respondeu com um SOAP Fault:")
        print(f"  código   : {falha.code}")
        print(f"  mensagem : {falha.message}")
        return 1

    print("Manifesto encontrado:")
    print(f"  número          : {resposta.numero}")
    print(f"  status          : {resposta.status}")
    print(f"  gerador         : {resposta.gerador_razao_social}")
    print(f"  destinador      : {resposta.destinador_razao_social}")
    print(f"  tipo destinação : {resposta.tipo_destinacao or '(ainda não destinado)'}")
    print(f"  atualizado em   : {resposta.atualizado_em}")
    return 0


def main() -> int:
    leitor = argparse.ArgumentParser(description="Consulta um manifesto pelo serviço SOAP.")
    leitor.add_argument("numero", nargs="?", default="RGO-2026-000001", help="Número do manifesto.")
    leitor.add_argument(
        "cnpj",
        nargs="?",
        default="11222333000181",
        help="CNPJ de quem consulta; precisa participar do manifesto.",
    )
    leitor.add_argument("--url", default=WSDL_PADRAO, help="Endereço do WSDL.")
    argumentos = leitor.parse_args()

    return consultar(argumentos.url, argumentos.numero, argumentos.cnpj)


if __name__ == "__main__":
    raise SystemExit(main())
