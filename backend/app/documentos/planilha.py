"""A listagem de manifestos em CSV.

E a exportacao para quem vai continuar o trabalho em planilha: montar um
grafico diferente, cruzar com dados proprios, conferir um total. Por isso a
linha do CSV e o **item**, nao o manifesto - uma linha por tipo de residuo,
repetindo os dados do manifesto. E o formato que permite uma tabela dinamica
somar por residuo, por classe ou por destinacao sem tratar o arquivo antes.

Duas escolhas de formato, ambas pensadas para o Excel em portugues:

* separador ponto e virgula, nao virgula, porque e o que o Excel brasileiro
  espera - com virgula ele joga a linha inteira em uma celula;
* numero com virgula decimal, pelo mesmo motivo.

O arquivo sai em UTF-8 com BOM. O BOM e o que faz o Excel reconhecer a
codificacao e mostrar "Goiânia" em vez de "GoiÃ¢nia".
"""

import csv
import io
from collections.abc import Iterable

from app.datas import formatar
from app.enums import ROTULOS_ACONDICIONAMENTO, ROTULOS_DESTINACAO, ROTULOS_STATUS
from app.models import Manifesto
from app.validacoes import formatar_cnpj

SEPARADOR = ";"

# O Excel em portugues usa a codificacao do sistema ao abrir um CSV com duplo
# clique; a marca de ordem de bytes (BOM) do UTF-8 e o sinal que o faz usar
# UTF-8 em vez dela.
CODIFICACAO = "utf-8-sig"

CABECALHO = [
    "numero",
    "status",
    "emitido_em",
    "coletado_em",
    "recebido_em",
    "destinado_em",
    "gerador",
    "gerador_cnpj",
    "gerador_municipio",
    "transportador",
    "transportador_cnpj",
    "destinador",
    "destinador_cnpj",
    "destinador_municipio",
    "tipo_destinacao",
    "placa_veiculo",
    "residuo_codigo",
    "residuo_descricao",
    "classe",
    "acondicionamento",
    "unidade",
    "quantidade_declarada",
    "quantidade_recebida",
    "divergente",
]


def gerar(manifestos: Iterable[Manifesto]) -> bytes:
    """Monta o CSV e devolve os bytes do arquivo.

    O arquivo e montado inteiro em memoria. Para a escala deste sistema isso e
    irrelevante; uma exportacao de centenas de milhares de linhas pediria uma
    resposta transmitida em partes, gerando linha a linha.
    """
    texto = io.StringIO()
    escritor = csv.writer(texto, delimiter=SEPARADOR, lineterminator="\r\n")

    escritor.writerow(CABECALHO)
    for manifesto in manifestos:
        for linha in _linhas_do_manifesto(manifesto):
            escritor.writerow(linha)

    return texto.getvalue().encode(CODIFICACAO)


def _linhas_do_manifesto(manifesto: Manifesto) -> list[list[str]]:
    """Uma linha por item, com os dados do manifesto repetidos em todas.

    Manifesto sem item nao existe (regra RN08), mas o laco sobre os itens
    deixa isso explicito: um manifesto sem itens simplesmente nao produz
    linha, em vez de produzir uma linha pela metade.
    """
    comuns = [
        manifesto.numero or "",
        ROTULOS_STATUS[manifesto.status],
        formatar(manifesto.emitido_em),
        formatar(manifesto.coletado_em),
        formatar(manifesto.recebido_em),
        formatar(manifesto.destinado_em),
        manifesto.gerador.razao_social,
        formatar_cnpj(manifesto.gerador.cnpj),
        manifesto.gerador.municipio_nome,
        manifesto.transportador.razao_social,
        formatar_cnpj(manifesto.transportador.cnpj),
        manifesto.destinador.razao_social,
        formatar_cnpj(manifesto.destinador.cnpj),
        manifesto.destinador.municipio_nome,
        ROTULOS_DESTINACAO[manifesto.tipo_destinacao] if manifesto.tipo_destinacao else "",
        manifesto.placa_veiculo or "",
    ]

    return [
        comuns
        + [
            item.tipo_residuo.codigo,
            item.tipo_residuo.descricao,
            item.tipo_residuo.classe.value,
            ROTULOS_ACONDICIONAMENTO[item.acondicionamento],
            item.unidade.value,
            _decimal(item.quantidade_declarada),
            _decimal(item.quantidade_recebida),
            "sim" if item.divergente else "não",
        ]
        for item in manifesto.itens
    ]


def _decimal(valor: float | None) -> str:
    """Numero com virgula decimal, que e como a planilha brasileira le."""
    return "" if valor is None else f"{valor:.3f}".replace(".", ",")
