"""Carga de dados de demonstracao.

Popula o banco com organizacoes, usuarios e tipos de residuo ficticios, para
que o sistema possa ser demonstrado sem cadastrar tudo a mao.

Como executar, a partir da pasta `backend`:

    python -m scripts.seed              # carrega (recusa se ja houver dados)
    python -m scripts.seed --recriar    # apaga tudo e carrega de novo

Decisoes de dados que importam para a demonstracao:

* uma das transportadoras esta com a **licenca ambiental vencida**, de
  proposito: e o que permite demonstrar ao vivo a regra RN04 recusando a
  emissao de um manifesto;
* os municipios sao reais, com codigos conferidos na API do IBGE;
* os CEP tambem sao reais e conferidos no ViaCEP, de modo que a consulta de
  CEP do sistema (`/localidades/cep/{cep}`) devolve exatamente o logradouro,
  o bairro e o municipio que estao cadastrados aqui;
* os CNPJ sao ficticios, mas com digitos verificadores calculados, de modo
  que passam pela validacao do proprio sistema.
"""

import sys
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.database import Base, SessionLocal, criar_tabelas, engine
from app.enums import ClasseResiduo, PapelOrganizacao, PerfilUsuario, UnidadeMedida
from app.models import Organizacao, TipoResiduo, Usuario
from app.security import gerar_hash_senha
from app.validacoes import completar_cnpj
from scripts import manifestos_demo

# Senha unica para todos os usuarios de demonstracao. Documentada no README:
# e dado de teste, nao segredo.
SENHA_DEMO = "residuogo123"

# Licencas: uma data no futuro para quem esta regular e uma no passado para a
# transportadora que serve de contraexemplo.
LICENCA_VALIDA = date(2027, 12, 31)
LICENCA_VENCIDA = date(2025, 6, 30)


# Organizacoes de demonstracao. A base do CNPJ tem 12 digitos; os dois
# verificadores sao calculados na carga.
ORGANIZACOES = [
    {
        "base_cnpj": "112223330001",
        "razao_social": "Indústria de Alimentos Cerrado S.A.",
        "papel": PapelOrganizacao.GERADOR,
        "cep": "75133662",
        "logradouro": "Rua do Daia",
        "numero": "1500",
        "bairro": "Setor Industrial Munir Calixto",
        "municipio_ibge_codigo": "5201108",
        "municipio_nome": "Anápolis",
        "licenca_numero": "LO-GO-2024-001",
        "licenca_validade": LICENCA_VALIDA,
        "email": "gerador1@residuogo.com.br",
        "responsavel": "Marina Alves Rocha",
    },
    {
        "base_cnpj": "223334440001",
        "razao_social": "Frigorífico Vale do Rio Verde Ltda.",
        "papel": PapelOrganizacao.GERADOR,
        "cep": "75910800",
        "logradouro": "Rodovia GO-174",
        "numero": "Km 12",
        "bairro": "Residencial Bela Vista",
        "municipio_ibge_codigo": "5218805",
        "municipio_nome": "Rio Verde",
        "licenca_numero": "LO-GO-2024-002",
        "licenca_validade": LICENCA_VALIDA,
        "email": "gerador2@residuogo.com.br",
        "responsavel": "Eduardo Petrini Campos",
    },
    {
        "base_cnpj": "334445550001",
        "razao_social": "Transportes Ambientais Goiás Ltda.",
        "papel": PapelOrganizacao.TRANSPORTADOR,
        "cep": "74130010",
        "logradouro": "Avenida Assis Chateaubriand",
        "numero": "320",
        "bairro": "Setor Oeste",
        "municipio_ibge_codigo": "5208707",
        "municipio_nome": "Goiânia",
        "licenca_numero": "LT-GO-2024-114",
        "licenca_validade": LICENCA_VALIDA,
        "email": "transportador1@residuogo.com.br",
        "responsavel": "Silas Moreira Lima",
    },
    {
        "base_cnpj": "445556660001",
        "razao_social": "Rodolimp Transporte de Resíduos ME",
        "papel": PapelOrganizacao.TRANSPORTADOR,
        # Licenca vencida de proposito: usada para demonstrar a regra RN04.
        "cep": "74913135",
        "logradouro": "Avenida São Paulo",
        "numero": "77",
        "bairro": "Parque Primavera",
        "municipio_ibge_codigo": "5201405",
        "municipio_nome": "Aparecida de Goiânia",
        "licenca_numero": "LT-GO-2022-049",
        "licenca_validade": LICENCA_VENCIDA,
        "email": "transportador2@residuogo.com.br",
        "responsavel": "Cleide Barros Pontes",
    },
    {
        "base_cnpj": "556667770001",
        "razao_social": "Aterro Sanitário Central do Cerrado S.A.",
        "papel": PapelOrganizacao.DESTINADOR,
        "cep": "75707265",
        "logradouro": "Rodovia BR-050",
        "numero": "Km 40",
        "bairro": "São Francisco",
        "municipio_ibge_codigo": "5205109",
        "municipio_nome": "Catalão",
        "licenca_numero": "LD-GO-2023-008",
        "licenca_validade": LICENCA_VALIDA,
        "email": "destinador1@residuogo.com.br",
        "responsavel": "Hélio Tavares Nunes",
    },
    {
        "base_cnpj": "667778880001",
        "razao_social": "Cooperativa de Reciclagem Renascer",
        "papel": PapelOrganizacao.DESTINADOR,
        "cep": "75536100",
        "logradouro": "Avenida Modesto de Carvalho",
        "numero": "245",
        "bairro": "Distrito Agroindustrial de Itumbiara - DIAGRI",
        "municipio_ibge_codigo": "5211503",
        "municipio_nome": "Itumbiara",
        "licenca_numero": "LD-GO-2024-031",
        "licenca_validade": LICENCA_VALIDA,
        "email": "destinador2@residuogo.com.br",
        "responsavel": "Juraci Ferreira dos Santos",
    },
]


# Catalogo de residuos. Os codigos seguem o formato da Lista Brasileira de
# Residuos Solidos; sao exemplos ilustrativos e devem ser conferidos na lista
# oficial antes de qualquer uso real.
TIPOS_RESIDUO = [
    ("150110", "Embalagens contaminadas com substâncias perigosas", ClasseResiduo.I, UnidadeMedida.KG),
    ("130205", "Óleo lubrificante usado", ClasseResiduo.I, UnidadeMedida.L),
    ("080111", "Resíduo de tinta e verniz", ClasseResiduo.I, UnidadeMedida.KG),
    ("160601", "Baterias de chumbo-ácido", ClasseResiduo.I, UnidadeMedida.KG),
    ("180103", "Resíduo de serviço de saúde infectante", ClasseResiduo.I, UnidadeMedida.KG),
    ("020202", "Resíduo de tecido animal", ClasseResiduo.IIA, UnidadeMedida.T),
    ("020304", "Resíduo orgânico de processamento de alimentos", ClasseResiduo.IIA, UnidadeMedida.T),
    ("200101", "Papel e cartão", ClasseResiduo.IIB, UnidadeMedida.KG),
    ("150102", "Embalagens de plástico", ClasseResiduo.IIB, UnidadeMedida.KG),
    ("170101", "Concreto e entulho de construção civil", ClasseResiduo.IIB, UnidadeMedida.M3),
    ("200140", "Sucata metálica", ClasseResiduo.IIB, UnidadeMedida.KG),
]


def _apagar_tudo() -> None:
    """Derruba e recria as tabelas, zerando o banco."""
    Base.metadata.drop_all(bind=engine)
    criar_tabelas()
    print("Banco zerado.")


def carregar(recriar: bool = False) -> None:
    """Grava os dados de demonstracao.

    Em uma unica transacao: se qualquer passo falhar, nada e gravado e o banco
    nao fica pela metade.
    """
    criar_tabelas()

    if recriar:
        _apagar_tudo()

    with SessionLocal() as sessao:
        if sessao.scalar(select(Usuario).limit(1)) is not None:
            print(
                "O banco já contém dados. Use --recriar para apagar tudo e "
                "carregar novamente.",
                file=sys.stderr,
            )
            raise SystemExit(1)

        # --- administrador -------------------------------------------------
        # Sem organizacao: o ADMIN atua sobre o sistema inteiro.
        sessao.add(
            Usuario(
                nome="Administrador do Sistema",
                email="admin@residuogo.com.br",
                senha_hash=gerar_hash_senha("admin12345"),
                perfil=PerfilUsuario.ADMIN,
                organizacao_id=None,
            )
        )

        # --- organizacoes e seus usuarios ----------------------------------
        for dados in ORGANIZACOES:
            organizacao = Organizacao(
                razao_social=dados["razao_social"],
                cnpj=completar_cnpj(dados["base_cnpj"]),
                papel=dados["papel"],
                cep=dados["cep"],
                logradouro=dados["logradouro"],
                numero=dados["numero"],
                bairro=dados["bairro"],
                municipio_ibge_codigo=dados["municipio_ibge_codigo"],
                municipio_nome=dados["municipio_nome"],
                licenca_numero=dados["licenca_numero"],
                licenca_validade=dados["licenca_validade"],
            )
            sessao.add(organizacao)

            # `flush` envia o INSERT e preenche o id, sem encerrar a
            # transacao - o id e necessario para vincular o usuario.
            sessao.flush()

            sessao.add(
                Usuario(
                    nome=dados["responsavel"],
                    email=dados["email"],
                    senha_hash=gerar_hash_senha(SENHA_DEMO),
                    perfil=PerfilUsuario.USUARIO,
                    organizacao_id=organizacao.id,
                )
            )

        # --- catalogo de residuos ------------------------------------------
        for codigo, descricao, classe, unidade in TIPOS_RESIDUO:
            sessao.add(
                TipoResiduo(
                    codigo=codigo,
                    descricao=descricao,
                    classe=classe,
                    unidade_padrao=unidade,
                )
            )

        sessao.commit()

    # Os manifestos vêm depois, em transação própria: dependem de todas as
    # organizações, usuários e tipos de resíduo já estarem gravados.
    with SessionLocal() as sessao:
        total = manifestos_demo.criar(sessao)
        print(f"\n{total} manifestos de demonstração criados.")

    _resumir()


def _resumir() -> None:
    """Imprime o que foi carregado e as credenciais de acesso.

    A impressao acontece toda dentro do `with`, e os usuarios sao carregados
    junto das organizacoes (`selectinload`). Por padrao o SQLAlchemy busca um
    relacionamento apenas quando ele e acessado, e fora da sessao essa busca
    nao e mais possivel.
    """
    with SessionLocal() as sessao:
        organizacoes = sessao.scalars(
            select(Organizacao)
            .options(selectinload(Organizacao.usuarios))
            .order_by(Organizacao.papel, Organizacao.razao_social)
        ).all()
        total_tipos = sessao.scalar(select(func.count()).select_from(TipoResiduo)) or 0

        print(f"\n{len(organizacoes)} organizações e {total_tipos} tipos de resíduo carregados.\n")
        print(f"{'PAPEL':<16}{'ORGANIZAÇÃO':<42}{'LICENÇA':<22}{'USUÁRIO'}")
        print("-" * 112)

        for organizacao in organizacoes:
            licenca = f"{organizacao.licenca_validade:%d/%m/%Y}"
            if not organizacao.licenca_vigente():
                licenca += "  (VENCIDA)"
            print(
                f"{organizacao.papel.value:<16}"
                f"{organizacao.razao_social[:40]:<42}"
                f"{licenca:<22}"
                f"{organizacao.usuarios[0].email}"
            )

    print("\nAdministrador: admin@residuogo.com.br / admin12345")
    print(f"Demais usuários: senha {SENHA_DEMO}")


if __name__ == "__main__":
    carregar(recriar="--recriar" in sys.argv)
