"""Conexao com o banco de dados e tipos de coluna compartilhados.

Define tres coisas usadas pelo resto do projeto:

* `engine` e `SessionLocal` - a conexao com o SQLite e a fabrica de sessoes;
* `Base` - a classe-mae de todos os models;
* `DataHoraUTC` - tipo de coluna que garante que toda data trafega em UTC.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, TypeDecorator, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import config

# `check_same_thread=False` e necessario porque o SQLite, por padrao, recusa
# conexoes usadas em threads diferentes - e o servidor web usa varias.
# A opcao so se aplica ao SQLite; outros bancos ignoram `connect_args`.
engine = create_engine(
    config.database_url,
    connect_args={"check_same_thread": False} if config.database_url.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """Classe-mae dos models. O SQLAlchemy usa suas subclasses para
    descobrir quais tabelas precisa criar."""


class DataHoraUTC(TypeDecorator):
    """Coluna de data e hora sempre em UTC.

    O SQLite nao armazena o fuso horario: ao gravar uma data com fuso ele
    guarda os numeros e descarta o `+00:00`, e a leitura volta sem fuso. Isso
    gera o classico bug de relatorio que conta um registro no mes errado.

    Este tipo elimina a ambiguidade nas duas pontas:

    * na gravacao, converte qualquer data para UTC (uma data sem fuso e
      interpretada como UTC) e remove o fuso, que e o formato aceito pelo banco;
    * na leitura, reinstala o fuso UTC.

    Resultado: dentro do Python toda data e sempre consciente de fuso e sempre
    em UTC. A conversao para o horario de Brasilia acontece apenas na exibicao,
    no front-end.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)


def agora_utc() -> datetime:
    """Momento atual em UTC.

    Usada como valor padrao das colunas de data. Centralizar isso em uma
    funcao garante que nenhum ponto do projeto grave `datetime.now()` sem
    fuso, que e a origem mais comum de inconsistencia de horario.
    """
    return datetime.now(timezone.utc)


def criar_tabelas() -> None:
    """Cria no banco as tabelas que ainda nao existem.

    Substitui uma ferramenta de migracao (como o Alembic), adequada quando o
    esquema ainda esta em evolucao e o banco pode ser recriado a vontade.
    """
    from app import models  # noqa: F401 - o import registra os models na Base

    Base.metadata.create_all(bind=engine)
