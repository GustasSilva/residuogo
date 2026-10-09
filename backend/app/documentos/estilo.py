"""O que os dois PDFs do sistema tem em comum.

Pagina, margens, cores, estilos de texto e o formato das tabelas ficam aqui
para que o manifesto e o resumo saiam com a mesma identidade visual, e para
que mudar essa identidade seja mudar um arquivo.

A biblioteca usada e o ReportLab, na API de alto nivel (`platypus`): o
documento e descrito como uma lista de elementos - paragrafo, tabela, espaco -
e a biblioteca cuida de distribui-los nas paginas. A alternativa seria desenhar
em coordenadas absolutas, o que quebraria assim que um texto crescesse.

As fontes sao as embutidas no proprio formato PDF (Helvetica), que ja cobrem os
acentos do portugues. Usar uma fonte externa exigiria distribuir o arquivo da
fonte junto do projeto.
"""

import io
from datetime import datetime
from typing import Any, Sequence

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

from app.config import config
from app.database import agora_utc
from app.datas import formatar

MARGEM = 15 * mm

# Paleta: o verde identifica o sistema, o cinza escuro e o texto comum e o
# cinza claro preenche o cabecalho das tabelas.
VERDE = colors.HexColor("#1B5E20")
CINZA = colors.HexColor("#424242")
CINZA_CLARO = colors.HexColor("#EEEEEE")
# O vermelho existe em duas formas porque o ReportLab as usa em contextos
# diferentes: objeto nos estilos de tabela, texto no markup dos paragrafos.
VERMELHO_HEX = "#B71C1C"
VERMELHO = colors.HexColor(VERMELHO_HEX)

_BASE = getSampleStyleSheet()

ESTILO_TITULO = ParagraphStyle(
    "TituloResiduoGO",
    parent=_BASE["Title"],
    fontSize=15,
    leading=19,
    alignment=0,  # alinhado a esquerda; o padrao do ReportLab e centralizado
    textColor=VERDE,
    spaceAfter=2,
)

ESTILO_SUBTITULO = ParagraphStyle(
    "SubtituloResiduoGO",
    parent=_BASE["Normal"],
    fontSize=10,
    leading=13,
    textColor=CINZA,
)

ESTILO_SECAO = ParagraphStyle(
    "SecaoResiduoGO",
    parent=_BASE["Heading2"],
    fontSize=11,
    leading=14,
    textColor=VERDE,
    spaceBefore=10,
    spaceAfter=4,
)

ESTILO_TEXTO = ParagraphStyle(
    "TextoResiduoGO",
    parent=_BASE["Normal"],
    fontSize=9,
    leading=12,
)

ESTILO_CELULA = ParagraphStyle(
    "CelulaResiduoGO",
    parent=ESTILO_TEXTO,
    fontSize=8.5,
    leading=11,
)

ESTILO_NUMERO = ParagraphStyle(
    "NumeroResiduoGO",
    parent=ESTILO_CELULA,
    alignment=TA_RIGHT,
)


def montar_documento(arquivo_em_memoria: Any, titulo: str, autor: str) -> SimpleDocTemplate:
    """Cria o documento A4 com as margens e os metadados do PDF.

    `titulo` e `autor` aparecem nas propriedades do arquivo - o que o leitor
    de PDF mostra na aba e no dialogo de informacoes.
    """
    return SimpleDocTemplate(
        arquivo_em_memoria,
        pagesize=A4,
        leftMargin=MARGEM,
        rightMargin=MARGEM,
        topMargin=MARGEM,
        bottomMargin=MARGEM + 8 * mm,  # espaco reservado para o rodape
        title=titulo,
        author=autor,
        subject=f"{config.app_nome} {config.app_versao}",
    )


def desenhar_rodape(canvas: Any, documento: SimpleDocTemplate) -> None:
    """Escreve o rodape em todas as paginas.

    Chamado pela biblioteca uma vez por pagina, ja com a pagina montada - e
    por isso que o numero da pagina pode ser escrito aqui e nao na lista de
    elementos, onde ele ainda nao e conhecido.

    O rodape traz o instante da geracao e o aviso de que o documento nao
    substitui o manifesto oficial exigido pelo orgao ambiental. Omitir esse
    aviso em um documento com aparencia de formulario oficial seria
    irresponsavel.
    """
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(CINZA)

    largura, _ = A4
    altura_do_rodape = MARGEM

    canvas.drawString(
        MARGEM,
        altura_do_rodape,
        f"{config.app_nome} - documento gerado em {formatar(agora_utc())}. "
        "Trabalho acadêmico: não substitui o manifesto oficial de resíduos.",
    )
    canvas.drawRightString(largura - MARGEM, altura_do_rodape, f"Página {documento.page}")

    canvas.restoreState()


def gerar_pdf(elementos: Sequence[Any], titulo: str, autor: str) -> bytes:
    """Monta o PDF e devolve os bytes.

    Devolver bytes, e nao gravar arquivo, e o que permite a rota responder o
    download direto: o PDF existe apenas durante a requisicao.
    """
    arquivo_em_memoria = io.BytesIO()
    documento = montar_documento(arquivo_em_memoria, titulo, autor)

    documento.build(
        list(elementos), onFirstPage=desenhar_rodape, onLaterPages=desenhar_rodape
    )

    return arquivo_em_memoria.getvalue()


def tabela(
    linhas: Sequence[Sequence[Any]],
    larguras: Sequence[float],
    *,
    colunas_a_direita: Sequence[int] = (),
) -> Table:
    """Tabela com a primeira linha como cabecalho e zebra nas demais.

    A zebra existe por legibilidade: em tabela de muitas colunas estreitas, o
    olho perde a linha sem ela. `colunas_a_direita` alinha as colunas
    numericas, para que as casas decimais fiquem alinhadas na vertical.
    """
    estilo = [
        ("BACKGROUND", (0, 0), (-1, 0), CINZA_CLARO),
        ("TEXTCOLOR", (0, 0), (-1, 0), CINZA),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.white),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, CINZA),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F7F7")]),
    ]

    for coluna in colunas_a_direita:
        estilo.append(("ALIGN", (coluna, 0), (coluna, -1), "RIGHT"))

    montada = Table(list(linhas), colWidths=list(larguras), repeatRows=1)
    montada.setStyle(TableStyle(estilo))
    return montada


def numero(valor: float | None, casas: int = 3) -> str:
    """Formata um numero no padrao brasileiro: ponto de milhar, virgula decimal.

    O PDF e lido por pessoas, entao segue a convencao do pais. Na API o numero
    continua saindo como numero, sem formatacao, que e o que um programa
    espera.
    """
    if valor is None:
        return "-"

    texto = f"{valor:,.{casas}f}"
    return texto.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def data_e_hora(momento: datetime | None) -> str:
    """Data e hora no fuso local, ou um traco quando a etapa nao aconteceu."""
    return formatar(momento) or "-"
