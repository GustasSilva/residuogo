"""Rota do painel inicial.

Uma unica rota, que devolve de uma vez os seis blocos que a tela inicial
mostra: os numeros do mes, os manifestos pendentes por estado, o indicador de
desvio de aterro, a distribuicao por destinacao, a serie dos ultimos meses e o
alerta de licencas ambientais.

Reunir tudo em uma resposta e deliberado. Em seis requisicoes separadas, cada
bloco poderia ser apurado em um instante diferente - e o grafico mostraria um
periodo que o cartao ao lado nao confirma.

Todos os numeros respeitam a regra RN07: a organizacao ve os seus manifestos,
o administrador ve todos.
"""

from fastapi import APIRouter

from app.dependencies import Sessao, UsuarioAtual
from app.schemas import IndicadoresSaida
from app.services import relatorios as servico

router = APIRouter(prefix="/dashboard", tags=["Painel"])


@router.get(
    "/indicadores",
    response_model=IndicadoresSaida,
    summary="Números do painel inicial",
)
def indicadores(sessao: Sessao, usuario: UsuarioAtual) -> dict:
    """Apura os indicadores do painel para a organização do usuário."""
    return servico.indicadores(sessao, usuario)
