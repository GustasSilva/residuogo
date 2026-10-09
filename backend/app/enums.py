"""Enumeracoes do dominio.

Ficam em modulo proprio porque sao usadas tanto pelos models (para gerar as
restricoes do banco) quanto pelos schemas (para validar a entrada da API).

Cada enum herda de `str` para que o valor trafegue no JSON como texto legivel
("GERADOR") em vez de um numero, o que facilita a leitura das respostas e dos
relatorios.
"""

from enum import Enum


class PapelOrganizacao(str, Enum):
    """Posicao da organizacao no ciclo do residuo.

    O papel da organizacao e o que define quais acoes seus usuarios podem
    executar sobre um manifesto (regra RN01).
    """

    GERADOR = "GERADOR"
    TRANSPORTADOR = "TRANSPORTADOR"
    DESTINADOR = "DESTINADOR"


class PerfilUsuario(str, Enum):
    """Nivel de acesso do usuario.

    ADMIN administra cadastros e enxerga todos os manifestos; USUARIO opera
    apenas em nome da propria organizacao.
    """

    ADMIN = "ADMIN"
    USUARIO = "USUARIO"


class ClasseResiduo(str, Enum):
    """Classificacao de residuos solidos conforme a NBR 10004.

    I = perigoso; IIA = nao inerte; IIB = inerte.
    """

    I = "I"
    IIA = "IIA"
    IIB = "IIB"


class UnidadeMedida(str, Enum):
    """Unidade em que a quantidade do residuo e declarada.

    KG e T sao unidades de massa; L e M3, de volume. Os relatorios somam massa
    e volume separadamente, pois converter volume em massa exigiria conhecer a
    densidade de cada residuo.
    """

    KG = "KG"
    T = "T"
    L = "L"
    M3 = "M3"


class StatusManifesto(str, Enum):
    """Estados possiveis de um manifesto.

    A ordem e as transicoes permitidas entre eles estao na maquina de estados
    (`services/manifestos.py`), nao aqui.
    """

    EMITIDO = "EMITIDO"
    EM_TRANSPORTE = "EM_TRANSPORTE"
    RECEBIDO = "RECEBIDO"
    RECUSADO = "RECUSADO"
    DESTINADO = "DESTINADO"
    CANCELADO = "CANCELADO"


class TipoDestinacao(str, Enum):
    """Tratamento final aplicado ao residuo.

    O agrupamento usado no indicador ambiental esta em `GRUPOS_DESTINACAO`,
    logo abaixo.
    """

    RECICLAGEM = "RECICLAGEM"
    COMPOSTAGEM = "COMPOSTAGEM"
    COPROCESSAMENTO = "COPROCESSAMENTO"
    INCINERACAO = "INCINERACAO"
    ATERRO = "ATERRO"
    OUTRO_TRATAMENTO = "OUTRO_TRATAMENTO"


class Acondicionamento(str, Enum):
    """Forma como o residuo e embalado para o transporte."""

    TAMBOR = "TAMBOR"
    BOMBONA = "BOMBONA"
    CACAMBA = "CACAMBA"
    BIG_BAG = "BIG_BAG"
    GRANEL = "GRANEL"
    OUTRO = "OUTRO"


# Destinacoes que recuperam o residuo (devolvem materia ou energia ao ciclo
# produtivo) e destinacoes que apenas dispoem o residuo. A taxa de desvio de
# aterro, principal indicador ambiental do sistema, e a razao entre a massa
# recuperada e a massa total destinada.
DESTINACOES_RECUPERACAO = frozenset(
    {
        TipoDestinacao.RECICLAGEM,
        TipoDestinacao.COMPOSTAGEM,
        TipoDestinacao.COPROCESSAMENTO,
    }
)

DESTINACOES_DISPOSICAO = frozenset(
    {
        TipoDestinacao.ATERRO,
        TipoDestinacao.INCINERACAO,
    }
)

# Estados em que o manifesto ainda aguarda acao de algum participante.
STATUS_EM_ANDAMENTO = frozenset(
    {
        StatusManifesto.EMITIDO,
        StatusManifesto.EM_TRANSPORTE,
        StatusManifesto.RECEBIDO,
    }
)
