"""Models do SQLAlchemy: o desenho das tabelas do banco.

Cada classe equivale a uma tabela e cada `mapped_column` a uma coluna. Os
`relationship` nao criam colunas: eles ensinam ao SQLAlchemy como navegar
entre as tabelas (por exemplo, `manifesto.itens`), evitando SQL manual.

As regras de negocio nao ficam aqui. Este modulo descreve a *estrutura* dos
dados; o comportamento (quem pode mudar o que, e quando) fica em `services/`.
"""

from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, DataHoraUTC, agora_utc
from app.enums import (
    Acondicionamento,
    ClasseResiduo,
    PapelOrganizacao,
    PerfilUsuario,
    StatusManifesto,
    TipoDestinacao,
    UnidadeMedida,
)


def _enum(tipo) -> Enum:
    """Cria uma coluna de enum armazenada como texto.

    `native_enum=False` faz o SQLAlchemy gravar o nome do enum em uma coluna
    VARCHAR com uma restricao CHECK, em vez de usar o tipo ENUM nativo (que o
    SQLite nao possui). A vantagem pratica e que o banco continua legivel por
    qualquer ferramenta: o valor gravado e o texto "GERADOR", nao um indice.
    """
    return Enum(tipo, native_enum=False, validate_strings=True)


# Quantidades de residuo: 12 digitos no total, 3 deles decimais (ate 1 grama).
# `asdecimal=False` devolve float em Python, que e o que o SQLite armazena de
# fato; um sistema com valores financeiros usaria Decimal.
Quantidade = Numeric(12, 3, asdecimal=False)


class Organizacao(Base):
    """Empresa participante do ciclo do residuo.

    A mesma tabela guarda geradores, transportadores e destinadores; o que os
    diferencia e a coluna `papel`.
    """

    __tablename__ = "organizacao"

    id: Mapped[int] = mapped_column(primary_key=True)
    razao_social: Mapped[str] = mapped_column(String(120))

    # Guardado apenas com digitos (sem pontos, barra ou hifen) para que a
    # restricao de unicidade funcione: "00.000.000/0001-00" e "00000000000100"
    # sao o mesmo CNPJ e nao podem conviver na tabela.
    cnpj: Mapped[str] = mapped_column(String(14), unique=True, index=True)

    papel: Mapped[PapelOrganizacao] = mapped_column(_enum(PapelOrganizacao), index=True)

    cep: Mapped[str] = mapped_column(String(8))
    logradouro: Mapped[str] = mapped_column(String(160))
    numero: Mapped[str] = mapped_column(String(20))
    bairro: Mapped[str] = mapped_column(String(80))
    municipio_ibge_codigo: Mapped[str] = mapped_column(String(7))
    municipio_nome: Mapped[str] = mapped_column(String(80))

    # Licenca ambiental de operacao. A validade e verificada na emissao do
    # manifesto (regra RN04).
    licenca_numero: Mapped[str] = mapped_column(String(40))
    licenca_validade: Mapped[date] = mapped_column(Date)

    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DataHoraUTC, default=agora_utc)

    usuarios: Mapped[list["Usuario"]] = relationship(back_populates="organizacao")

    def licenca_vigente(self, referencia: date | None = None) -> bool:
        """Informa se a licenca ambiental esta valida na data de referencia."""
        return self.licenca_validade >= (referencia or date.today())


class Usuario(Base):
    """Pessoa que acessa o sistema em nome de uma organizacao.

    O usuario nao tem papel proprio no fluxo do residuo: ele herda o papel da
    organizacao a qual pertence. O ADMIN e a excecao e nao possui organizacao.
    """

    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)

    # Apenas o hash bcrypt da senha e guardado; a senha original nunca e
    # armazenada nem registrada em log.
    senha_hash: Mapped[str] = mapped_column(String(100))

    perfil: Mapped[PerfilUsuario] = mapped_column(_enum(PerfilUsuario))

    # Nulo somente para o ADMIN, que atua sobre o sistema inteiro.
    organizacao_id: Mapped[int | None] = mapped_column(ForeignKey("organizacao.id"))

    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DataHoraUTC, default=agora_utc)

    organizacao: Mapped[Organizacao | None] = relationship(back_populates="usuarios")

    @property
    def e_admin(self) -> bool:
        return self.perfil is PerfilUsuario.ADMIN


class TipoResiduo(Base):
    """Item do catalogo de residuos.

    Catalogo compartilhado por todas as organizacoes e mantido pelo ADMIN, de
    modo que o mesmo residuo seja declarado da mesma forma por todos - o que e
    o que torna os relatorios comparaveis.
    """

    __tablename__ = "tipo_residuo"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Codigo da Lista Brasileira de Residuos Solidos.
    codigo: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    descricao: Mapped[str] = mapped_column(String(160))
    classe: Mapped[ClasseResiduo] = mapped_column(_enum(ClasseResiduo))
    unidade_padrao: Mapped[UnidadeMedida] = mapped_column(_enum(UnidadeMedida))


class Manifesto(Base):
    """Documento que rastreia um lote de residuo do gerador ate a destinacao.

    E o centro do sistema. As tres chaves estrangeiras para `organizacao`
    registram os participantes, e as quatro colunas de data registram quando
    cada etapa aconteceu - o que permite reconstruir a linha do tempo mesmo
    sem consultar o historico.
    """

    __tablename__ = "manifesto"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Identificador externo, no formato RGO-AAAA-NNNNNN, derivado do `id`.
    # Aceita nulo no banco porque o `id` so existe depois do INSERT: o
    # servico de emissao preenche o numero na mesma transacao, logo apos
    # gravar a linha. Nenhum manifesto e confirmado sem numero.
    numero: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)

    # Os tres participantes. `foreign_keys` e obrigatorio nos relacionamentos
    # abaixo porque as tres colunas apontam para a mesma tabela e o SQLAlchemy
    # nao conseguiria adivinhar qual relacionamento usa qual coluna.
    gerador_id: Mapped[int] = mapped_column(ForeignKey("organizacao.id"), index=True)
    transportador_id: Mapped[int] = mapped_column(ForeignKey("organizacao.id"), index=True)
    destinador_id: Mapped[int] = mapped_column(ForeignKey("organizacao.id"), index=True)

    status: Mapped[StatusManifesto] = mapped_column(
        _enum(StatusManifesto), default=StatusManifesto.EMITIDO, index=True
    )

    # Preenchidos na confirmacao da coleta pelo transportador.
    placa_veiculo: Mapped[str | None] = mapped_column(String(10))
    motorista_nome: Mapped[str | None] = mapped_column(String(120))

    # Preenchido na destinacao final pelo destinador (regra RN06).
    tipo_destinacao: Mapped[TipoDestinacao | None] = mapped_column(_enum(TipoDestinacao))

    # Preenchido quando o destinador recusa a carga (regra RN06).
    motivo_recusa: Mapped[str | None] = mapped_column(Text)

    observacoes: Mapped[str | None] = mapped_column(Text)

    # Token impresso como QR code no PDF. E um UUID aleatorio, e nao o `id`,
    # para que a etiqueta nao revele quantos manifestos existem no sistema.
    qr_token: Mapped[str] = mapped_column(
        String(36), unique=True, index=True, default=lambda: str(uuid4())
    )

    emitido_em: Mapped[datetime] = mapped_column(DataHoraUTC, default=agora_utc, index=True)
    coletado_em: Mapped[datetime | None] = mapped_column(DataHoraUTC)
    recebido_em: Mapped[datetime | None] = mapped_column(DataHoraUTC)

    # Data do fato que os relatorios de massa destinada usam como referencia.
    destinado_em: Mapped[datetime | None] = mapped_column(DataHoraUTC, index=True)

    atualizado_em: Mapped[datetime] = mapped_column(
        DataHoraUTC, default=agora_utc, onupdate=agora_utc
    )

    gerador: Mapped[Organizacao] = relationship(foreign_keys=[gerador_id])
    transportador: Mapped[Organizacao] = relationship(foreign_keys=[transportador_id])
    destinador: Mapped[Organizacao] = relationship(foreign_keys=[destinador_id])

    # `cascade="all, delete-orphan"` faz os itens acompanharem o manifesto:
    # eles nao existem sozinhos. O historico nao recebe cascade porque e
    # registro de auditoria.
    itens: Mapped[list["ItemManifesto"]] = relationship(
        back_populates="manifesto", cascade="all, delete-orphan"
    )
    movimentacoes: Mapped[list["Movimentacao"]] = relationship(
        back_populates="manifesto", order_by="Movimentacao.data_hora"
    )

    def participantes_ids(self) -> set[int]:
        """Ids das organizacoes envolvidas neste manifesto.

        Usado pelo controle de visibilidade (regra RN07): um usuario so pode
        ver o manifesto se a organizacao dele estiver neste conjunto.
        """
        return {self.gerador_id, self.transportador_id, self.destinador_id}


class ItemManifesto(Base):
    """Uma linha de residuo dentro do manifesto.

    Um manifesto transporta um ou mais tipos de residuo; cada tipo e um item,
    com sua propria quantidade e forma de acondicionamento.
    """

    __tablename__ = "item_manifesto"

    id: Mapped[int] = mapped_column(primary_key=True)
    manifesto_id: Mapped[int] = mapped_column(ForeignKey("manifesto.id"), index=True)
    tipo_residuo_id: Mapped[int] = mapped_column(ForeignKey("tipo_residuo.id"))

    # Quantidade informada pelo gerador na emissao.
    quantidade_declarada: Mapped[float] = mapped_column(Quantidade)

    # Quantidade conferida pelo destinador no recebimento (regra RN05).
    # Nula ate a carga chegar ao destino.
    quantidade_recebida: Mapped[float | None] = mapped_column(Quantidade)

    unidade: Mapped[UnidadeMedida] = mapped_column(_enum(UnidadeMedida))
    acondicionamento: Mapped[Acondicionamento] = mapped_column(_enum(Acondicionamento))

    # Marcado quando declarado e recebido diferem mais que a tolerancia de 5%.
    # Nao impede o recebimento: serve de alerta e entra no relatorio.
    divergente: Mapped[bool] = mapped_column(Boolean, default=False)

    manifesto: Mapped[Manifesto] = relationship(back_populates="itens")
    tipo_residuo: Mapped[TipoResiduo] = relationship()


class Movimentacao(Base):
    """Registro de uma mudanca de status do manifesto.

    Tabela de auditoria: as linhas sao apenas inseridas, nunca alteradas ou
    apagadas. E ela que responde "quem mudou o que, e quando" - a
    rastreabilidade que uma auditoria ambiental exige.
    """

    __tablename__ = "movimentacao"

    id: Mapped[int] = mapped_column(primary_key=True)
    manifesto_id: Mapped[int] = mapped_column(ForeignKey("manifesto.id"), index=True)

    # Nulo na primeira movimentacao, quando o manifesto acabou de ser emitido
    # e portanto nao havia status anterior.
    status_anterior: Mapped[StatusManifesto | None] = mapped_column(_enum(StatusManifesto))
    status_novo: Mapped[StatusManifesto] = mapped_column(_enum(StatusManifesto))

    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    data_hora: Mapped[datetime] = mapped_column(DataHoraUTC, default=agora_utc)
    observacao: Mapped[str | None] = mapped_column(Text)

    manifesto: Mapped[Manifesto] = relationship(back_populates="movimentacoes")
    usuario: Mapped[Usuario] = relationship()
