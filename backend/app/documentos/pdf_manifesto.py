"""O manifesto em PDF, com QR code.

E o documento que acompanha a carga. Reune em uma pagina o que cada
participante precisa conferir na entrega: quem gerou, quem transporta, quem
recebe, o que esta sendo transportado, em que quantidade e sob qual licenca.

O QR code no alto da pagina abre este mesmo manifesto na tela do sistema. E o
que liga o papel ao registro digital: o destinador aponta a camera e lanca o
recebimento sem digitar o numero.

A pagina e montada como uma lista de elementos, de cima para baixo. Se o
manifesto tiver muitos itens ou um historico longo, a biblioteca abre a
segunda pagina sozinha - o rodape e o cabecalho das tabelas se repetem.
"""

import io
from typing import Any

from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, Spacer, Table

from app.documentos import qr
from app.documentos.estilo import (
    ESTILO_CELULA,
    ESTILO_SECAO,
    ESTILO_SUBTITULO,
    ESTILO_TEXTO,
    ESTILO_TITULO,
    VERMELHO_HEX,
    data_e_hora,
    gerar_pdf,
    numero,
    tabela,
)
from app.enums import (
    ROTULOS_ACONDICIONAMENTO,
    ROTULOS_DESTINACAO,
    ROTULOS_STATUS,
    UnidadeMedida,
)
from app.models import ItemManifesto, Manifesto, Movimentacao, Organizacao
from app.validacoes import formatar_cep, formatar_cnpj

# Largura util da pagina A4 descontadas as duas margens de 15 mm.
LARGURA_UTIL = 180 * mm

LADO_DO_QR = 26 * mm


def gerar(manifesto: Manifesto, movimentacoes: list[Movimentacao]) -> bytes:
    """Monta o PDF do manifesto e devolve os bytes do arquivo.

    Recebe o manifesto e o seu historico ja carregados - a geracao do
    documento nao consulta o banco. Isso mantem a montagem do PDF testavel com
    objetos em memoria e evita o problema classico de uma consulta disparada
    por acesso a atributo no meio da renderizacao.
    """
    elementos: list[Any] = [
        _cabecalho(manifesto),
        Spacer(1, 6 * mm),
        Paragraph("Participantes", ESTILO_SECAO),
        _tabela_de_participantes(manifesto),
        Paragraph("Resíduos", ESTILO_SECAO),
        _tabela_de_itens(manifesto.itens),
        Paragraph("Transporte e destinação", ESTILO_SECAO),
        _tabela_de_etapas(manifesto),
    ]

    if manifesto.observacoes:
        elementos += [
            Paragraph("Observações", ESTILO_SECAO),
            Paragraph(manifesto.observacoes, ESTILO_TEXTO),
        ]

    if manifesto.motivo_recusa:
        elementos += [
            Paragraph("Motivo da recusa", ESTILO_SECAO),
            Paragraph(manifesto.motivo_recusa, ESTILO_TEXTO),
        ]

    if movimentacoes:
        elementos += [
            Paragraph("Histórico", ESTILO_SECAO),
            _tabela_de_historico(movimentacoes),
        ]

    return gerar_pdf(
        elementos,
        titulo=f"Manifesto {manifesto.numero}",
        autor=manifesto.gerador.razao_social,
    )


def _cabecalho(manifesto: Manifesto) -> Table:
    """Titulo, numero e situacao a esquerda; QR code a direita.

    Montado como uma tabela de duas colunas sem bordas, que e a forma de
    colocar dois blocos lado a lado em um documento que flui de cima para
    baixo.
    """
    identificacao = [
        Paragraph("Manifesto de Transporte de Resíduos", ESTILO_TITULO),
        Paragraph(
            f"<b>{manifesto.numero}</b> &nbsp;·&nbsp; "
            f"{ROTULOS_STATUS[manifesto.status]} &nbsp;·&nbsp; "
            f"emitido em {data_e_hora(manifesto.emitido_em)}",
            ESTILO_SUBTITULO,
        ),
    ]

    imagem = Image(
        io.BytesIO(qr.imagem_do_manifesto(manifesto.qr_token)),
        width=LADO_DO_QR,
        height=LADO_DO_QR,
    )

    cabecalho = Table(
        [[identificacao, imagem]],
        colWidths=[LARGURA_UTIL - LADO_DO_QR, LADO_DO_QR],
    )
    cabecalho.setStyle(
        [
            ("VALIGN", (0, 0), (0, 0), "TOP"),
            ("VALIGN", (1, 0), (1, 0), "TOP"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
        ]
    )
    return cabecalho


def _descricao_da_organizacao(organizacao: Organizacao) -> Paragraph:
    """Bloco de identificacao de um participante.

    Inclui a licenca ambiental porque e o dado que a fiscalizacao confere na
    estrada: sem licenca valida, o transporte nao pode acontecer.
    """
    return Paragraph(
        f"<b>{organizacao.razao_social}</b><br/>"
        f"CNPJ {formatar_cnpj(organizacao.cnpj)}<br/>"
        f"{organizacao.logradouro}, {organizacao.numero} - {organizacao.bairro}<br/>"
        f"{organizacao.municipio_nome} - CEP {formatar_cep(organizacao.cep)}<br/>"
        f"Licença {organizacao.licenca_numero}, válida até "
        f"{organizacao.licenca_validade:%d/%m/%Y}",
        ESTILO_CELULA,
    )


def _tabela_de_participantes(manifesto: Manifesto) -> Table:
    """Os tres participantes, um por linha, na ordem do fluxo do residuo."""
    linhas = [
        ["Papel", "Organização"],
        ["Gerador", _descricao_da_organizacao(manifesto.gerador)],
        ["Transportador", _descricao_da_organizacao(manifesto.transportador)],
        ["Destinador", _descricao_da_organizacao(manifesto.destinador)],
    ]
    return tabela(linhas, [30 * mm, LARGURA_UTIL - 30 * mm])


def _tabela_de_itens(itens: list[ItemManifesto]) -> Table:
    """Os residuos transportados, com declarado, recebido e divergencia.

    A coluna de divergencia e preenchida apenas quando a regra RN05 acusou
    diferenca acima de 5%, e sai em vermelho: e a informacao que o destinador
    precisa ver primeiro ao conferir a carga.
    """
    linhas: list[list[Any]] = [
        ["Resíduo", "Classe", "Acondicionamento", "Un.", "Declarado", "Recebido", ""]
    ]

    for item in itens:
        divergencia = (
            Paragraph(f'<font color="{VERMELHO_HEX}">divergente</font>', ESTILO_CELULA)
            if item.divergente
            else ""
        )

        linhas.append(
            [
                Paragraph(
                    f"{item.tipo_residuo.codigo}<br/>{item.tipo_residuo.descricao}",
                    ESTILO_CELULA,
                ),
                item.tipo_residuo.classe.value,
                ROTULOS_ACONDICIONAMENTO[item.acondicionamento],
                _unidade(item.unidade),
                numero(item.quantidade_declarada),
                numero(item.quantidade_recebida),
                divergencia,
            ]
        )

    return tabela(
        linhas,
        [58 * mm, 14 * mm, 30 * mm, 10 * mm, 24 * mm, 24 * mm, 20 * mm],
        colunas_a_direita=(4, 5),
    )


def _unidade(unidade: UnidadeMedida) -> str:
    """Unidade como se escreve: m3 sai com o expoente, as outras em minusculas."""
    return "m³" if unidade is UnidadeMedida.M3 else unidade.value.lower()


def _tabela_de_etapas(manifesto: Manifesto) -> Table:
    """Dados do veiculo e as datas de cada etapa do fluxo.

    As quatro datas contam a historia do manifesto sem precisar do historico:
    etapa nao cumprida aparece como traco.
    """
    destinacao = (
        ROTULOS_DESTINACAO[manifesto.tipo_destinacao]
        if manifesto.tipo_destinacao
        else "-"
    )

    linhas = [
        ["Etapa", "Quando", "Dados"],
        ["Emissão", data_e_hora(manifesto.emitido_em), manifesto.gerador.municipio_nome],
        [
            "Coleta",
            data_e_hora(manifesto.coletado_em),
            _dados_do_veiculo(manifesto),
        ],
        [
            "Recebimento",
            data_e_hora(manifesto.recebido_em),
            manifesto.destinador.municipio_nome,
        ],
        ["Destinação", data_e_hora(manifesto.destinado_em), destinacao],
    ]
    return tabela(linhas, [30 * mm, 45 * mm, LARGURA_UTIL - 75 * mm])


def _dados_do_veiculo(manifesto: Manifesto) -> str:
    """Placa e motorista, informados na confirmacao da coleta."""
    if not manifesto.placa_veiculo:
        return "-"
    return f"Placa {manifesto.placa_veiculo} - {manifesto.motorista_nome}"


def _tabela_de_historico(movimentacoes: list[Movimentacao]) -> Table:
    """A linha do tempo das mudancas de status, com o autor de cada uma.

    E a parte do documento que serve a auditoria: responde quem mudou o que, e
    quando. Vem da tabela de movimentacoes, que so recebe insercoes.
    """
    linhas: list[list[Any]] = [["Quando", "Mudança", "Responsável", "Observação"]]

    for movimentacao in movimentacoes:
        anterior = (
            ROTULOS_STATUS[movimentacao.status_anterior]
            if movimentacao.status_anterior
            else "início"
        )
        linhas.append(
            [
                data_e_hora(movimentacao.data_hora),
                f"{anterior} → {ROTULOS_STATUS[movimentacao.status_novo]}",
                Paragraph(movimentacao.usuario.nome, ESTILO_CELULA),
                Paragraph(movimentacao.observacao or "", ESTILO_CELULA),
            ]
        )

    return tabela(linhas, [32 * mm, 45 * mm, 45 * mm, LARGURA_UTIL - 122 * mm])
