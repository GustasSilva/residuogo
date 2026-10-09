"""Infraestrutura comum dos testes.

As "fixtures" definidas aqui ficam disponiveis para todos os arquivos de teste
sem precisarem ser importadas - o pytest as encontra pelo nome do parametro.

A decisao central deste arquivo: cada teste roda sobre um banco SQLite **em
memoria**, criado vazio e descartado no fim. Isso garante que os testes nao
dependam da ordem em que rodam, nao sujem o banco de desenvolvimento e nao
precisem de limpeza manual.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.dependencies import obter_sessao
from app.enums import ClasseResiduo, PapelOrganizacao, PerfilUsuario, UnidadeMedida
from app.main import app
from app.models import Organizacao, TipoResiduo, Usuario
from app.security import gerar_hash_senha
from app.validacoes import completar_cnpj

SENHA_TESTE = "senhaDeTeste123"


@pytest.fixture
def sessao() -> Session:
    """Entrega uma sessao ligada a um banco em memoria, vazio.

    `StaticPool` faz todas as sessoes compartilharem a mesma conexao. Sem
    isso, um banco SQLite em memoria seria diferente para cada conexao aberta,
    e o dado gravado pelo teste nao seria encontrado pela aplicacao.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)

    fabrica = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    with fabrica() as sessao_de_teste:
        yield sessao_de_teste

    engine.dispose()


@pytest.fixture
def cliente(sessao: Session) -> TestClient:
    """Cliente HTTP que conversa com a aplicacao sem subir um servidor.

    A substituicao em `dependency_overrides` troca a sessao real pela de
    teste: a aplicacao inteira passa a usar o banco em memoria sem que
    nenhuma linha de codigo de producao mude.

    O `TestClient` e usado sem `with` de proposito. O bloco `with` dispararia
    o ciclo de vida da aplicacao, que cria as tabelas no banco de
    desenvolvimento - justamente o que os testes devem evitar tocar.
    """
    app.dependency_overrides[obter_sessao] = lambda: sessao
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def dados(sessao: Session) -> dict:
    """Cria o conjunto minimo de registros usado pela maioria dos testes.

    Inclui, de proposito, uma transportadora com licenca vencida: e ela que
    permite testar a regra RN04 sem montar o cenario em cada teste.
    """
    ontem = date.today() - timedelta(days=1)
    futuro = date.today() + timedelta(days=365)

    def nova_organizacao(
        base_cnpj: str, razao: str, papel: PapelOrganizacao, validade: date
    ) -> Organizacao:
        return Organizacao(
            razao_social=razao,
            cnpj=completar_cnpj(base_cnpj),
            papel=papel,
            cep="74000000",
            logradouro="Rua de Teste",
            numero="100",
            bairro="Centro",
            municipio_ibge_codigo="5208707",
            municipio_nome="Goiânia",
            licenca_numero="LIC-TESTE",
            licenca_validade=validade,
        )

    gerador = nova_organizacao("112223330001", "Gerador Teste SA", PapelOrganizacao.GERADOR, futuro)
    transportador = nova_organizacao(
        "334445550001", "Transportador Teste SA", PapelOrganizacao.TRANSPORTADOR, futuro
    )
    transportador_vencido = nova_organizacao(
        "445556660001", "Transportador Vencido SA", PapelOrganizacao.TRANSPORTADOR, ontem
    )
    destinador = nova_organizacao(
        "556667770001", "Destinador Teste SA", PapelOrganizacao.DESTINADOR, futuro
    )

    sessao.add_all([gerador, transportador, transportador_vencido, destinador])
    sessao.flush()

    admin = Usuario(
        nome="Admin Teste",
        email="admin@teste.com.br",
        senha_hash=gerar_hash_senha(SENHA_TESTE),
        perfil=PerfilUsuario.ADMIN,
        organizacao_id=None,
    )
    usuario_gerador = Usuario(
        nome="Usuario Gerador",
        email="gerador@teste.com.br",
        senha_hash=gerar_hash_senha(SENHA_TESTE),
        perfil=PerfilUsuario.USUARIO,
        organizacao_id=gerador.id,
    )
    usuario_destinador = Usuario(
        nome="Usuario Destinador",
        email="destinador@teste.com.br",
        senha_hash=gerar_hash_senha(SENHA_TESTE),
        perfil=PerfilUsuario.USUARIO,
        organizacao_id=destinador.id,
    )

    tipo = TipoResiduo(
        codigo="020202",
        descricao="Resíduo de tecido animal",
        classe=ClasseResiduo.IIA,
        unidade_padrao=UnidadeMedida.T,
    )

    sessao.add_all([admin, usuario_gerador, usuario_destinador, tipo])
    sessao.commit()

    return {
        "gerador": gerador,
        "transportador": transportador,
        "transportador_vencido": transportador_vencido,
        "destinador": destinador,
        "admin": admin,
        "usuario_gerador": usuario_gerador,
        "usuario_destinador": usuario_destinador,
        "tipo_residuo": tipo,
    }


def autenticar(cliente: TestClient, email: str, senha: str = SENHA_TESTE) -> dict[str, str]:
    """Faz login e devolve o cabecalho de autorizacao pronto para uso.

    E uma funcao auxiliar, nao uma fixture, porque cada teste precisa escolher
    *qual* usuario autenticar.
    """
    resposta = cliente.post("/api/v1/auth/login", json={"email": email, "senha": senha})
    assert resposta.status_code == 200, resposta.text
    return {"Authorization": f"Bearer {resposta.json()['token']}"}
