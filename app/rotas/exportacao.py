"""Arquivos da busca para baixar: planilha CSV e relatorio em PDF."""

import csv
import io
from datetime import datetime

from fpdf import FPDF
from fpdf.fonts import FontFace

from app.servicos.materiais import MATERIAIS

# Como o ponto de partida foi localizado, para quem le saber o quanto ele e aproximado.
COMO_FOI_LOCALIZADO = {
    "endereço": "localizado pela rua",
    "bairro": "localizado pelo bairro",
    "município": "localizado pela cidade",
    "lugar": "localizado pelo texto digitado",
}

NOTAS_DO_RELATORIO = [
    "Este relatório pode apoiar o levantamento de alternativas de destinação no Plano de Gerenciamento de "
    "Resíduos Sólidos (PGRS) da organização, previsto na Política Nacional de Resíduos Sólidos "
    "(Lei 12.305/2010), e o controle operacional da ISO 14001.",
    "Fontes: © colaboradores do OpenStreetMap (openstreetmap.org/copyright), IBGE e ViaCEP.",
]


# --- CSV ---


def planilha(pontos: list[dict]) -> str:
    saida = io.StringIO()
    # O Excel em portugues separa colunas por ponto e virgula e decimais por virgula.
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(["Nome", "Tipo", "Endereço", "Materiais", "Distância (km)", "Latitude", "Longitude"])
    for ponto in pontos:
        escritor.writerow(
            [
                _celula_segura(ponto["nome"]),
                ponto["tipo"],
                _celula_segura(ponto["endereco"]),
                _materiais(ponto),
                _decimal(ponto["distancia_km"]),
                _decimal(ponto["latitude"]),
                _decimal(ponto["longitude"]),
            ]
        )
    # O BOM (marca no inicio do arquivo) faz o Excel reconhecer os acentos.
    return "﻿" + saida.getvalue()


def _celula_segura(texto: str) -> str:
    """Os nomes vem de um mapa aberto: impede que o Excel execute um deles como formula."""
    return f"'{texto}" if texto[:1] in ("=", "+", "-", "@") else texto


# --- PDF ---


# APS-TRECHO 10: O relatorio da busca em PDF
def relatorio_pdf(resultado: dict) -> bytes:
    """Relatorio da busca: de onde, o que, ate onde, a tabela dos pontos e as fontes dos dados."""
    pdf = FPDF(orientation="landscape", format="A4")
    # As fontes que todo leitor de PDF tem cobrem o Windows-1252, que inclui o portugues.
    pdf.core_fonts_encoding = "windows-1252"
    pdf.set_title("ResíduoGO: pontos de coleta de resíduos")
    pdf.add_page()
    _cabecalho(pdf, resultado)

    if resultado["fora_do_raio"] and resultado["pontos"]:
        pdf.set_font("Helvetica", "B", 10)
        aviso = f"Não há pontos até {resultado['raio_km']} km. A tabela mostra os mais próximos, mesmo que mais longe."
        pdf.cell(h=6, text=aviso, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    pdf.set_font("Helvetica", size=9)
    if resultado["pontos"]:
        cabecalho = FontFace(emphasis="BOLD", fill_color=(230, 230, 230))
        with pdf.table(col_widths=(62, 38, 77, 20, 80), headings_style=cabecalho, line_height=5, text_align="LEFT") as tabela:
            tabela.row(["Nome", "Tipo", "Endereço", "Distância", "Materiais"])
            for ponto in resultado["pontos"]:
                tabela.row([
                    _texto(ponto["nome"]),
                    ponto["tipo"],
                    _texto(ponto["endereco"]) or "-",
                    f"{_decimal(ponto['distancia_km'])} km",
                    _materiais(ponto),
                ])
    else:
        pdf.cell(h=6, text="Nenhum ponto encontrado para esta busca.", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(5)
    pdf.set_font("Helvetica", size=8)
    for nota in NOTAS_DO_RELATORIO:
        pdf.multi_cell(0, 4, nota, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
    return bytes(pdf.output())
# APS-FIM


def _cabecalho(pdf: FPDF, resultado: dict) -> None:
    """Titulo, data e, um em cada linha, os dados da busca."""
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(h=9, text="ResíduoGO: pontos de coleta de resíduos", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(90)
    pdf.cell(h=5, text=f"Relatório gerado em {datetime.now():%d/%m/%Y às %H:%M}", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0)
    pdf.ln(2)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(4)

    for rotulo, valor in (
        ("Local", _local(resultado["origem"])),
        ("Material", MATERIAIS.get(resultado["material"], "Qualquer material")),
        ("Distância máxima", f"{resultado['raio_km']} km"),
        ("Pontos encontrados", str(resultado["total"])),
    ):
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(38, 6, rotulo)
        pdf.set_font("Helvetica", size=10)
        pdf.multi_cell(0, 6, _texto(valor), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)


def _local(origem: dict) -> str:
    if origem["precisao"] == "mapa":
        return f"Ponto escolhido no mapa ({origem['latitude']:.5f}, {origem['longitude']:.5f})"
    return f"{origem['descricao']} ({COMO_FOI_LOCALIZADO[origem['precisao']]})"


def _texto(texto: str) -> str:
    """Nomes do mapa podem ter qualquer caractere: o que a fonte nao tem vira "?" em vez de derrubar o PDF."""
    return str(texto).encode("cp1252", "replace").decode("cp1252")


# --- Comum ---


def _materiais(ponto: dict) -> str:
    return ", ".join(item["rotulo"] for item in ponto["materiais"]) or "Não informado"


def _decimal(numero: float) -> str:
    return str(numero).replace(".", ",")
