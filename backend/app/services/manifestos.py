"""Regras de negocio do manifesto.

Na fase atual contem a consulta usada pelo servico SOAP. A maquina de estados
(emissao, coleta, recebimento, recusa, destinacao e cancelamento) entra neste
mesmo modulo na proxima fase.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import PermissaoNegada, RecursoNaoEncontrado
from app.models import Manifesto
from app.validacoes import apenas_digitos, formatar_cnpj


def consultar_por_numero(sessao: Session, numero: str, cnpj_consultante: str) -> Manifesto:
    """Localiza um manifesto pelo numero, conferindo se quem pergunta participa dele.

    Esta e a regra de visibilidade do servico SOAP, equivalente a RN07 do
    REST: so gerador, transportador ou destinador daquele manifesto podem
    consulta-lo. Sem isso, qualquer pessoa com um numero de manifesto
    conheceria a operacao de empresas das quais nao participa.

    A busca normaliza a entrada (espacos, maiusculas e pontuacao do CNPJ)
    porque o numero costuma ser digitado a partir de um documento impresso.
    """
    numero_normalizado = numero.strip().upper()

    manifesto = sessao.scalar(select(Manifesto).where(Manifesto.numero == numero_normalizado))
    if manifesto is None:
        raise RecursoNaoEncontrado(f"Manifesto {numero_normalizado} não encontrado.")

    cnpj = apenas_digitos(cnpj_consultante)
    participantes = {
        manifesto.gerador.cnpj,
        manifesto.transportador.cnpj,
        manifesto.destinador.cnpj,
    }

    if cnpj not in participantes:
        raise PermissaoNegada(
            f"O CNPJ {formatar_cnpj(cnpj)} não participa do manifesto "
            f"{numero_normalizado} e por isso não pode consultá-lo."
        )

    return manifesto
