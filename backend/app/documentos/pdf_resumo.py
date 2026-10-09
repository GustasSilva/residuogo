"""O resumo do periodo em PDF.

Mesmo conteudo que a rota `/relatorios/resumo` devolve em JSON, formatado para
leitura e arquivamento - e o documento que uma organizacao anexa ao seu
relatorio de gestao ambiental.

Recebe o dicionario pronto do servico de relatorios e nao consulta o banco:
os numeros do PDF sao exatamente os mesmos do JSON, por construcao. Se o PDF
refizesse as contas, as duas respostas poderiam divergir.
"""

from typing import Any

from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Table

from app.documentos.estilo import (
    ESTILO_CELULA,
    ESTILO_SECAO,
    ESTILO_SUBTITULO,
    ESTILO_TEXTO,
    ESTILO_TITULO,
    gerar_pdf,
    numero,
    tabela,
)
from app.datas import formatar_data

LARGURA_UTIL = 180 * mm

# Cabecalho comum as tres tabelas do resumo. "Manifestos" e "Itens" dizem de
# quantos documentos cada linha foi apurada, o que permite conferir o total.
COLUNAS = ["", "Massa (kg)", "Volume (m³)", "Manifestos", "Itens"]
LARGURAS = [LARGURA_UTIL - 120 * mm, 34 * mm, 34 * mm, 26 * mm, 26 * mm]
COLUNAS_NUMERICAS = (1, 2, 3, 4)


def gerar(resumo: dict[str, Any], abrangencia: str) -> bytes:
    """Monta o PDF do resumo e devolve os bytes do arquivo.

    `abrangencia` descreve de quem sao os dados - a razao social da
    organizacao, ou todas elas quando quem pede e o administrador. Fica
    impresso no cabecalho porque um relatorio sem essa informacao e ambiguo:
    os mesmos numeros significam coisas diferentes se forem de uma empresa ou
    do estado inteiro.
    """
    divergencias = resumo["divergencias"]

    elementos: list[Any] = [
        Paragraph("Resumo de resíduos destinados", ESTILO_TITULO),
        Paragraph(
            f"Período de {formatar_data(resumo['inicio'])} a "
            f"{formatar_data(resumo['fim'])} &nbsp;·&nbsp; {abrangencia}",
            ESTILO_SUBTITULO,
        ),
        Spacer(1, 5 * mm),
        Paragraph(
            "Considera apenas manifestos já destinados, pela data da destinação. "
            "Massa e volume são apresentados separadamente: converter um no outro "
            "exigiria arbitrar a densidade de cada resíduo.",
            ESTILO_TEXTO,
        ),
        Paragraph("Total do período", ESTILO_SECAO),
        _tabela_do_total(resumo["total"]),
        Paragraph("Por tipo de resíduo", ESTILO_SECAO),
        _tabela_de_linhas(resumo["por_tipo"]),
        Paragraph("Por classe (NBR 10004)", ESTILO_SECAO),
        _tabela_de_linhas(resumo["por_classe"]),
        Paragraph("Por destinação final", ESTILO_SECAO),
        _tabela_de_linhas(resumo["por_destinacao"]),
        Paragraph("Divergências de quantidade", ESTILO_SECAO),
        Paragraph(
            f"{divergencias['itens_divergentes']} de "
            f"{divergencias['itens_conferidos']} itens conferidos divergiram em mais "
            f"de 5% entre a quantidade declarada pelo gerador e a recebida no "
            f"destino ({numero(divergencias['percentual'], casas=1)}%).",
            ESTILO_TEXTO,
        ),
    ]

    return gerar_pdf(elementos, titulo="Resumo de resíduos destinados", autor=abrangencia)


def _tabela_do_total(total: dict[str, Any]) -> Table:
    """Uma unica linha, com os totais do periodo."""
    return _tabela_de_linhas([total])


def _tabela_de_linhas(linhas: list[dict[str, Any]]) -> Table:
    """Tabela de uma agregacao do resumo, no mesmo formato para as tres.

    Periodo sem nenhum manifesto destinado produz lista vazia; nesse caso sai
    uma linha avisando, e nao uma tabela vazia que pareceria defeito.
    """
    if not linhas:
        return tabela(
            [COLUNAS, [Paragraph("Nenhum manifesto destinado no período.", ESTILO_CELULA), "", "", "", ""]],
            LARGURAS,
        )

    montadas = [COLUNAS]

    for linha in linhas:
        montadas.append(
            [
                Paragraph(linha["rotulo"], ESTILO_CELULA),
                numero(linha["massa_kg"]),
                numero(linha["volume_m3"]),
                str(linha["manifestos"]),
                str(linha["itens"]),
            ]
        )

    return tabela(montadas, LARGURAS, colunas_a_direita=COLUNAS_NUMERICAS)
