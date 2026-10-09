"""Rotas de relatório: resumo do período em JSON e em PDF, e listagem em CSV.

As três respondem com o mesmo recorte de dados que o usuário enxerga na
listagem — a regra RN07 vale aqui como em qualquer consulta, e o relatório de
uma organização nunca inclui manifestos de outra.

O resumo existe em dois formatos a partir da **mesma apuração**: a rota JSON
devolve o dicionário montado pelo serviço e a rota PDF entrega esse mesmo
dicionário ao gerador de documento. Se o PDF refizesse as contas, os dois
poderiam divergir — e divergiriam, na primeira correção aplicada só de um lado.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.datas import hoje_local
from app.dependencies import Sessao, UsuarioAtual
from app.documentos import pdf_resumo, planilha
from app.enums import StatusManifesto
from app.models import Usuario
from app.schemas import ResumoSaida
from app.services import manifestos as servico_manifestos
from app.services import relatorios as servico

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])

# Tipos dos filtros de período, declarados uma vez porque as rotas de JSON e
# de PDF precisam aceitar exatamente os mesmos parâmetros.
InicioQuery = Annotated[
    date | None,
    Query(description="Primeiro dia do período. Padrão: 6 meses atrás, no dia 1."),
]
FimQuery = Annotated[
    date | None, Query(description="Último dia do período, incluído. Padrão: hoje.")
]


def _abrangencia(usuario: Usuario) -> str:
    """De quem são os dados do relatório, para imprimir no cabeçalho do PDF.

    Um relatório sem essa informação é ambíguo: os mesmos números significam
    coisas diferentes se forem de uma empresa ou de todas elas.
    """
    if usuario.e_admin:
        return "Todas as organizações"
    return usuario.organizacao.razao_social


def _para_download(
    conteudo: bytes, *, nome: str, tipo: str, anexar: bool
) -> Response:
    """Monta a resposta de um arquivo gerado na hora.

    `anexar` escolhe entre baixar direto (`attachment`) e abrir no visualizador
    do navegador (`inline`). O PDF abre, porque o usuário quer conferir antes
    de guardar; o CSV baixa, porque o navegador não tem o que mostrar.
    """
    disposicao = "attachment" if anexar else "inline"
    return Response(
        content=conteudo,
        media_type=tipo,
        headers={"Content-Disposition": f'{disposicao}; filename="{nome}"'},
    )


@router.get(
    "/resumo",
    response_model=ResumoSaida,
    summary="Resumo do período: massa e volume por tipo, classe e destinação",
)
def resumo(
    sessao: Sessao,
    usuario: UsuarioAtual,
    inicio: InicioQuery = None,
    fim: FimQuery = None,
) -> dict:
    """Apura o que foi destinado no período.

    Considera apenas manifestos já destinados, pela data da destinação: é
    quando o resíduo efetivamente teve destino, e é o que o indicador
    ambiental mede. Manifestos em trânsito ainda não produziram resultado.
    """
    inicio, fim = servico.resolver_periodo(inicio, fim)
    return servico.resumo(sessao, usuario, inicio, fim)


@router.get(
    "/resumo.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "Resumo em PDF"}},
    summary="O mesmo resumo, em PDF",
)
def resumo_em_pdf(
    sessao: Sessao,
    usuario: UsuarioAtual,
    inicio: InicioQuery = None,
    fim: FimQuery = None,
) -> Response:
    """Gera o resumo do período como documento para arquivo ou impressão."""
    inicio, fim = servico.resolver_periodo(inicio, fim)
    apuracao = servico.resumo(sessao, usuario, inicio, fim)

    return _para_download(
        pdf_resumo.gerar(apuracao, _abrangencia(usuario)),
        nome=f"resumo-{inicio:%Y-%m-%d}-a-{fim:%Y-%m-%d}.pdf",
        tipo="application/pdf",
        anexar=False,
    )


@router.get(
    "/manifestos.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "Listagem em CSV"}},
    summary="Exporta a listagem de manifestos em CSV",
)
def manifestos_em_csv(
    sessao: Sessao,
    usuario: UsuarioAtual,
    status: Annotated[StatusManifesto | None, Query(description="Filtra por status.")] = None,
    inicio: Annotated[
        date | None, Query(description="Emitidos a partir desta data.")
    ] = None,
    fim: Annotated[date | None, Query(description="Emitidos até esta data.")] = None,
    participante_id: Annotated[
        int | None, Query(description="Organização participante, em qualquer papel.")
    ] = None,
) -> Response:
    """Exporta a listagem com os mesmos filtros da rota `GET /manifestos`.

    O CSV é a listagem exportada, não um recorte diferente: reaproveita a
    consulta da listagem, inclusive a visibilidade. A diferença é que não tem
    paginação — exportar meia página seria inútil.

    Cada linha do arquivo é um **item** do manifesto, com os dados do
    manifesto repetidos. É o formato que uma tabela dinâmica consegue somar
    por resíduo, por classe ou por destinação.
    """
    # A consulta da listagem ja traz itens, tipos de residuo e participantes
    # carregados, que e exatamente o que cada linha do CSV precisa.
    consulta = servico_manifestos.montar_consulta(
        usuario, status=status, inicio=inicio, fim=fim, participante_id=participante_id
    )
    encontrados = sessao.scalars(consulta).unique().all()

    return _para_download(
        planilha.gerar(encontrados),
        nome=f"manifestos-{hoje_local():%Y-%m-%d}.csv",
        tipo="text/csv; charset=utf-8",
        anexar=True,
    )
