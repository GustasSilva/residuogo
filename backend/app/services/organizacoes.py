"""Regras de negocio das organizacoes participantes.

Aqui vive a definicao de **organizacao apta**: ativa, com o papel esperado e
com licenca ambiental dentro da validade.

Essa definicao e usada em dois lugares diferentes - no filtro da listagem
(para a tela de novo manifesto oferecer apenas participantes validos) e na
emissao do manifesto (regra RN04, que recusa participante inapto). Manter uma
unica definicao e o que impede o front-end oferecer uma transportadora que o
back-end vai depois recusar.
"""

from datetime import date

from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session

from app.enums import PapelOrganizacao
from app.errors import Conflito, LicencaVencida, PapelInvalido, RecursoNaoEncontrado
from app.models import Organizacao
from app.schemas import OrganizacaoCriar


def condicoes_apta(
    papel: PapelOrganizacao, referencia: date | None = None
) -> list[ColumnElement[bool]]:
    """Condicoes SQL que definem uma organizacao apta para um papel.

    Devolve uma lista de condicoes em vez de uma consulta pronta para que
    quem chama possa combina-las com os proprios filtros.
    """
    hoje = referencia or date.today()
    return [
        Organizacao.ativo.is_(True),
        Organizacao.papel == papel,
        Organizacao.licenca_validade >= hoje,
    ]


def exigir_apta(
    organizacao: Organizacao,
    papel: PapelOrganizacao,
    funcao: str,
    referencia: date | None = None,
) -> None:
    """Confere se a organizacao pode atuar como `papel`, ou levanta o erro.

    A mesma regra de `condicoes_apta`, aplicada a um objeto ja carregado.
    O parametro `funcao` entra na mensagem de erro ("transportador",
    "destinador") para que o usuario saiba qual dos participantes recusou.

    Implementa a regra RN04. A ordem das verificacoes importa: papel errado e
    um erro de preenchimento e deve ser apontado antes da licenca, que e uma
    pendencia administrativa.
    """
    if organizacao.papel is not papel:
        raise PapelInvalido(
            f"A organização {organizacao.razao_social} tem o papel "
            f"{organizacao.papel.value} e não pode ser indicada como {funcao}."
        )

    if not organizacao.ativo:
        raise PapelInvalido(
            f"A organização {organizacao.razao_social} está desativada e não "
            f"pode ser indicada como {funcao}."
        )

    if not organizacao.licenca_vigente(referencia):
        raise LicencaVencida(
            f"A licença ambiental de {organizacao.razao_social} venceu em "
            f"{organizacao.licenca_validade:%d/%m/%Y} e por isso ela não pode "
            f"atuar como {funcao}."
        )


def buscar(sessao: Session, organizacao_id: int) -> Organizacao:
    """Carrega uma organizacao pelo id ou levanta 404."""
    organizacao = sessao.get(Organizacao, organizacao_id)
    if organizacao is None:
        raise RecursoNaoEncontrado(f"Organização {organizacao_id} não encontrada.")
    return organizacao


def criar(sessao: Session, dados: OrganizacaoCriar) -> Organizacao:
    """Cadastra uma organizacao, recusando CNPJ repetido.

    A consulta previa existe para devolver uma mensagem clara; a garantia real
    da unicidade e a restricao UNIQUE da coluna, que o banco aplica mesmo se
    duas requisicoes chegarem ao mesmo tempo.
    """
    ja_existe = sessao.scalar(select(Organizacao).where(Organizacao.cnpj == dados.cnpj))
    if ja_existe is not None:
        raise Conflito(
            f"O CNPJ informado já está cadastrado para a organização "
            f"{ja_existe.razao_social}"
        )

    organizacao = Organizacao(**dados.model_dump())
    sessao.add(organizacao)
    sessao.commit()
    sessao.refresh(organizacao)
    return organizacao
