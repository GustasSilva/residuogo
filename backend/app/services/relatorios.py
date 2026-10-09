"""Agregacoes do resumo por periodo e dos indicadores do painel.

Duas decisoes governam este modulo.

**Massa e volume nunca se somam.** O residuo e declarado em kg, t, L ou m3.
Converter volume em massa exigiria arbitrar uma densidade para cada tipo de
residuo - um numero inventado que contaminaria todos os indicadores. Entao as
quantidades sao reduzidas a duas grandezas, usando apenas as conversoes exatas
dentro da mesma grandeza (1 t = 1000 kg; 1000 L = 1 m3): **massa em kg** e
**volume em m3**. Cada linha de relatorio traz as duas, e uma delas costuma ser
zero.

**A data de referencia e `destinado_em`.** Um manifesto conta para o mes em que
a destinacao foi informada, e nao em que foi emitido: e a data em que o residuo
efetivamente teve um destino, que e o que o indicador ambiental mede. Por isso
o resumo considera somente manifestos destinados - os demais ainda nao
produziram resultado ambiental algum.

A regra RN07 (visibilidade) vale aqui como em qualquer outra consulta: as
condicoes vem de `services/manifestos.py`, as mesmas usadas na listagem.
"""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import ColumnElement, Row, Select, case, func, select
from sqlalchemy.orm import Session

from app.datas import (
    hoje_local,
    inicio_do_dia_em_utc,
    primeiro_dia_do_mes,
    ultimo_dia_do_mes,
)
from app.enums import (
    DESTINACOES_RECUPERACAO,
    ROTULOS_CLASSE,
    ROTULOS_DESTINACAO,
    ROTULOS_STATUS,
    STATUS_EM_ANDAMENTO,
    ClasseResiduo,
    StatusManifesto,
    TipoDestinacao,
    UnidadeMedida,
)
from app.errors import RegraDeNegocio
from app.models import ItemManifesto, Manifesto, Organizacao, TipoResiduo, Usuario
from app.services.manifestos import condicoes_de_visibilidade

# Conversoes exatas, dentro da mesma grandeza. Unidade que nao aparece no
# dicionario entra na soma como zero: assim um item em litros nao contamina o
# total de massa.
FATORES_MASSA_KG = {UnidadeMedida.KG: 1.0, UnidadeMedida.T: 1000.0}
FATORES_VOLUME_M3 = {UnidadeMedida.M3: 1.0, UnidadeMedida.L: 0.001}

# Quantos meses o painel mostra no grafico e usa como janela do indicador de
# desvio de aterro.
MESES_DA_JANELA = 6

# Antecedencia com que uma licenca ambiental passa a ser alertada no painel.
DIAS_DE_ALERTA_DE_LICENCA = 30

# Casas decimais das quantidades. Tres casas correspondem a um grama, que e a
# precisao da coluna no banco; arredondar aqui evita que a soma de floats
# devolva 1234.5600000000002 para o relatorio.
CASAS = 3


# ---------------------------------------------------------------------------
# Blocos de consulta reaproveitados
# ---------------------------------------------------------------------------


def _quantidade_que_vale() -> ColumnElement[float]:
    """A quantidade usada nos relatorios: a recebida no destino.

    A recebida e o valor pesado na balanca do destinador; a declarada e a
    estimativa do gerador. Onde as duas divergem, o relatorio deve refletir o
    que chegou. O `coalesce` recai na declarada apenas por seguranca: no fluxo
    normal nenhum manifesto chega a DESTINADO sem ter passado pelo
    recebimento, que exige as quantidades (regra RN05).
    """
    return func.coalesce(
        ItemManifesto.quantidade_recebida, ItemManifesto.quantidade_declarada
    )


def _soma_convertida(fatores: dict[UnidadeMedida, float]) -> ColumnElement[float]:
    """SUM da quantidade convertida para a unidade de referencia da grandeza.

    A conversao acontece dentro do SQL, em um CASE por unidade. Trazer as
    linhas para somar em Python funcionaria com os dados de demonstracao, mas
    faria a resposta crescer junto com a base - o banco soma melhor e devolve
    apenas o total.
    """
    quantidade = _quantidade_que_vale()
    convertida = case(
        *[
            (ItemManifesto.unidade == unidade, quantidade * fator)
            for unidade, fator in fatores.items()
        ],
        else_=0.0,
    )
    # `coalesce` externo: SUM de nenhuma linha devolve NULL, e o relatorio
    # precisa de zero.
    return func.coalesce(func.sum(convertida), 0.0)


def _itens_destinados(usuario: Usuario, inicio: date, fim: date) -> Select:
    """Consulta base: itens dos manifestos destinados no periodo.

    O dia final entra inteiro - a comparacao e com o inicio do dia seguinte -
    e o recorte usa o fuso local, nao o UTC em que as datas estao gravadas.
    """
    return (
        select()
        .select_from(ItemManifesto)
        .join(Manifesto, Manifesto.id == ItemManifesto.manifesto_id)
        .join(TipoResiduo, TipoResiduo.id == ItemManifesto.tipo_residuo_id)
        .where(
            Manifesto.destinado_em >= inicio_do_dia_em_utc(inicio),
            Manifesto.destinado_em < inicio_do_dia_em_utc(fim + timedelta(days=1)),
            *condicoes_de_visibilidade(usuario),
        )
    )


def _somar_por(
    sessao: Session,
    usuario: Usuario,
    inicio: date,
    fim: date,
    *agrupamento: ColumnElement,
) -> list[Row]:
    """Agrega o periodo pelas colunas informadas.

    As tres visoes do resumo - por tipo de residuo, por classe e por
    destinacao - sao a mesma consulta mudando apenas o GROUP BY. Passar a
    coluna de agrupamento como parametro evita tres consultas quase iguais,
    que divergiriam na primeira correcao feita em uma e esquecida nas outras.

    Sem colunas de agrupamento, devolve uma unica linha com os totais do
    periodo - que e como o painel obtem os numeros do mes.

    Cada linha termina com quatro valores: massa em kg, volume em m3,
    quantidade de manifestos distintos e quantidade de itens.
    """
    consulta = (
        _itens_destinados(usuario, inicio, fim)
        .add_columns(
            *agrupamento,
            _soma_convertida(FATORES_MASSA_KG),
            _soma_convertida(FATORES_VOLUME_M3),
            func.count(func.distinct(Manifesto.id)),
            func.count(ItemManifesto.id),
        )
        .group_by(*agrupamento)
        .order_by(*agrupamento)
    )
    return list(sessao.execute(consulta).all())


def _linha(chave: str, rotulo: str, valores: Row) -> dict[str, Any]:
    """Monta uma linha de relatorio a partir dos quatro agregados finais."""
    massa_kg, volume_m3, manifestos, itens = valores[-4:]
    return {
        "chave": chave,
        "rotulo": rotulo,
        "massa_kg": round(massa_kg, CASAS),
        "volume_m3": round(volume_m3, CASAS),
        "manifestos": manifestos,
        "itens": itens,
    }


# ---------------------------------------------------------------------------
# Resumo por periodo
# ---------------------------------------------------------------------------


def periodo_padrao() -> tuple[date, date]:
    """Periodo usado quando a requisicao nao informa datas.

    Os seis meses correntes, comecando no primeiro dia do mes: e a janela que
    o painel mostra, e comecar no dia 1 faz o cabecalho do relatorio cair em
    limites de mes, mais legiveis que "10/04 a 09/10".
    """
    hoje = hoje_local()
    return primeiro_dia_do_mes(hoje, MESES_DA_JANELA - 1), hoje


def resolver_periodo(inicio: date | None, fim: date | None) -> tuple[date, date]:
    """Completa o periodo com o padrao e recusa um intervalo invertido.

    Em funcao propria porque as duas rotas do resumo - JSON e PDF - precisam
    resolver o periodo da mesma forma, e porque o intervalo invertido devolve
    uma mensagem clara em vez de um relatorio vazio que o usuario leria como
    "nao houve movimento".
    """
    padrao_inicio, padrao_fim = periodo_padrao()
    inicio = inicio or padrao_inicio
    fim = fim or padrao_fim

    if inicio > fim:
        raise RegraDeNegocio(
            f"O período informado está invertido: a data inicial "
            f"({inicio:%d/%m/%Y}) é posterior à final ({fim:%d/%m/%Y})."
        )

    return inicio, fim


def resumo(sessao: Session, usuario: Usuario, inicio: date, fim: date) -> dict[str, Any]:
    """Resumo do periodo: quanto foi destinado, por tipo, classe e destinacao.

    Devolve tambem a contagem de divergencias, que e o indicador de
    confiabilidade do processo: item cuja quantidade recebida difere da
    declarada em mais de 5% (regra RN05).
    """
    totais = _somar_por(sessao, usuario, inicio, fim)[0]

    return {
        "inicio": inicio,
        "fim": fim,
        "total": _linha("TOTAL", "Total do período", totais),
        "por_tipo": _por_tipo(sessao, usuario, inicio, fim),
        "por_classe": _por_classe(sessao, usuario, inicio, fim),
        "por_destinacao": por_destinacao(sessao, usuario, inicio, fim),
        "divergencias": _divergencias(sessao, usuario, inicio, fim),
    }


def _por_tipo(
    sessao: Session, usuario: Usuario, inicio: date, fim: date
) -> list[dict[str, Any]]:
    """Uma linha por tipo de residuo do catalogo, identificada pelo codigo."""
    agrupadas = []

    for linha in _somar_por(
        sessao, usuario, inicio, fim, TipoResiduo.codigo, TipoResiduo.descricao
    ):
        codigo, descricao = linha[0], linha[1]
        agrupadas.append(_linha(codigo, f"{codigo} - {descricao}", linha))

    return agrupadas


def _por_classe(
    sessao: Session, usuario: Usuario, inicio: date, fim: date
) -> list[dict[str, Any]]:
    """Uma linha por classe da NBR 10004 (I, II A, II B)."""
    agrupadas = []

    for linha in _somar_por(sessao, usuario, inicio, fim, TipoResiduo.classe):
        classe: ClasseResiduo = linha[0]
        agrupadas.append(_linha(classe.value, ROTULOS_CLASSE[classe], linha))

    return agrupadas


def por_destinacao(
    sessao: Session, usuario: Usuario, inicio: date, fim: date
) -> list[dict[str, Any]]:
    """Uma linha por tipo de tratamento final aplicado ao residuo.

    Publica dentro do modulo porque alimenta duas coisas: a tabela do resumo e
    o grafico do painel, que tambem tira dela o indicador de desvio de aterro.
    """
    agrupadas = []

    for linha in _somar_por(sessao, usuario, inicio, fim, Manifesto.tipo_destinacao):
        destinacao: TipoDestinacao | None = linha[0]
        if destinacao is None:
            # Nao deve ocorrer: a destinacao exige o tipo de tratamento (RN06).
            # O desvio existe para um dado antigo sem tipo nao derrubar o painel.
            continue
        agrupadas.append(_linha(destinacao.value, ROTULOS_DESTINACAO[destinacao], linha))

    return agrupadas


def _divergencias(
    sessao: Session, usuario: Usuario, inicio: date, fim: date
) -> dict[str, Any]:
    """Quantos itens foram conferidos e quantos divergiram, no periodo."""
    consulta = _itens_destinados(usuario, inicio, fim).add_columns(
        func.count(ItemManifesto.id),
        func.coalesce(
            func.sum(case((ItemManifesto.divergente.is_(True), 1), else_=0)), 0
        ),
    )
    conferidos, divergentes = sessao.execute(consulta).one()

    return {
        "itens_conferidos": conferidos,
        "itens_divergentes": divergentes,
        "percentual": round(divergentes / conferidos * 100, 1) if conferidos else 0.0,
    }


# ---------------------------------------------------------------------------
# Indicadores do painel
# ---------------------------------------------------------------------------


def indicadores(sessao: Session, usuario: Usuario) -> dict[str, Any]:
    """Todos os numeros do painel, em uma unica resposta.

    Reunir tudo aqui e deliberado: a tela inicial precisa de seis informacoes
    diferentes e, em requisicoes separadas, elas poderiam vir de instantes
    diferentes - o grafico de um mes e o card de outro.
    """
    hoje = hoje_local()
    inicio_do_mes = primeiro_dia_do_mes(hoje)
    inicio_da_janela = primeiro_dia_do_mes(hoje, MESES_DA_JANELA - 1)

    destinacoes = por_destinacao(sessao, usuario, inicio_da_janela, hoje)

    return {
        "referencia": hoje,
        "mes": _resumo_do_mes(sessao, usuario, inicio_do_mes, hoje),
        "pendentes_por_status": _pendentes_por_status(sessao, usuario),
        "desvio_de_aterro": _desvio_de_aterro(destinacoes),
        "por_destinacao": destinacoes,
        "serie_mensal": _serie_mensal(sessao, usuario, hoje),
        "licencas_a_vencer": _licencas_a_vencer(sessao, usuario, hoje),
    }


def _resumo_do_mes(
    sessao: Session, usuario: Usuario, inicio: date, hoje: date
) -> dict[str, Any]:
    """Numeros do mes corrente: o que foi emitido e o que foi destinado.

    As duas contagens respondem a perguntas diferentes. "Emitidos" mede o
    movimento do mes; "destinados" mede o que efetivamente teve destino - e e
    sobre os destinados que as quantidades sao somadas.
    """
    emitidos = sessao.scalar(
        select(func.count(Manifesto.id)).where(
            Manifesto.emitido_em >= inicio_do_dia_em_utc(inicio),
            *condicoes_de_visibilidade(usuario),
        )
    )

    destinado = _linha("MES", "Destinado no mês", _somar_por(sessao, usuario, inicio, hoje)[0])

    return {
        "inicio": inicio,
        "fim": hoje,
        "manifestos_emitidos": emitidos or 0,
        "manifestos_destinados": destinado["manifestos"],
        "massa_kg": destinado["massa_kg"],
        "volume_m3": destinado["volume_m3"],
    }


def _pendentes_por_status(sessao: Session, usuario: Usuario) -> list[dict[str, Any]]:
    """Quantos manifestos aguardam acao, em cada estado nao final.

    Os estados vem de `STATUS_EM_ANDAMENTO` e aparecem todos, inclusive os
    zerados: o painel mostra um card fixo por estado, e nao uma lista variavel.
    """
    contagens = dict(
        sessao.execute(
            select(Manifesto.status, func.count(Manifesto.id))
            .where(
                Manifesto.status.in_(STATUS_EM_ANDAMENTO),
                *condicoes_de_visibilidade(usuario),
            )
            .group_by(Manifesto.status)
        ).all()
    )

    return [
        {
            "status": status.value,
            "rotulo": ROTULOS_STATUS[status],
            "total": contagens.get(status, 0),
        }
        for status in StatusManifesto
        if status in STATUS_EM_ANDAMENTO
    ]


def _desvio_de_aterro(destinacoes: list[dict[str, Any]]) -> dict[str, Any]:
    """Proporcao da massa que foi recuperada em vez de disposta.

    Principal indicador ambiental do sistema: quanto do residuo voltou ao
    ciclo produtivo (reciclagem, compostagem, coprocessamento) em relacao a
    todo o residuo destinado no periodo.

    Calculado sobre a massa, nao sobre volume nem sobre numero de manifestos.
    Massa e a grandeza em que a maior parte do residuo e declarada, e somar
    massa com volume para obter uma unica razao exigiria a densidade que o
    sistema deliberadamente nao arbitra.

    Reaproveita as linhas ja agregadas por destinacao em vez de consultar o
    banco outra vez - os dois numeros saem da mesma apuracao que alimenta o
    grafico, e assim nao podem discordar dele.
    """
    recuperada = sum(
        linha["massa_kg"]
        for linha in destinacoes
        if TipoDestinacao(linha["chave"]) in DESTINACOES_RECUPERACAO
    )
    total = sum(linha["massa_kg"] for linha in destinacoes)

    return {
        "meses": MESES_DA_JANELA,
        "massa_recuperada_kg": round(recuperada, CASAS),
        "massa_total_kg": round(total, CASAS),
        # Sem massa destinada no periodo nao existe proporcao a informar. Zero
        # seria mentira (sugeriria que nada foi recuperado), por isso nulo.
        "percentual": round(recuperada / total * 100, 1) if total else None,
    }


def _serie_mensal(sessao: Session, usuario: Usuario, hoje: date) -> list[dict[str, Any]]:
    """Massa e volume destinados em cada um dos ultimos meses.

    Uma consulta por mes, em vez de um GROUP BY pela data: agrupar no banco
    exigiria uma funcao de data especifica do SQLite (`strftime`), que
    agruparia pelo mes em **UTC** - colocando no mes seguinte o que foi
    destinado a noite do ultimo dia. O laco aqui recorta cada mes no fuso
    local, que e o mes que o usuario ve no relatorio.
    """
    meses = []

    for recuo in reversed(range(MESES_DA_JANELA)):
        inicio = primeiro_dia_do_mes(hoje, recuo)
        fim = min(ultimo_dia_do_mes(inicio), hoje)
        totais = _somar_por(sessao, usuario, inicio, fim)[0]

        linha = _linha(f"{inicio:%Y-%m}", f"{inicio:%m/%Y}", totais)
        linha["inicio"] = inicio
        meses.append(linha)

    return meses


def _licencas_a_vencer(
    sessao: Session, usuario: Usuario, hoje: date
) -> list[dict[str, Any]]:
    """Licencas ambientais vencidas ou a vencer nos proximos 30 dias.

    As vencidas entram na mesma lista, com `dias_restantes` negativo: uma
    licenca que ja venceu e mais urgente que uma que esta por vencer, e
    esconde-la do alerta seria o oposto do util. E essa licenca que faz a
    emissao do manifesto ser recusada pela regra RN04.

    O usuario comum ve apenas a licenca da propria organizacao; o ADMIN ve
    todas, porque e ele quem mantem o cadastro.
    """
    limite = hoje + timedelta(days=DIAS_DE_ALERTA_DE_LICENCA)

    consulta = (
        select(Organizacao)
        .where(Organizacao.ativo.is_(True), Organizacao.licenca_validade <= limite)
        .order_by(Organizacao.licenca_validade)
    )

    if not usuario.e_admin:
        consulta = consulta.where(Organizacao.id == usuario.organizacao_id)

    return [
        {
            "organizacao_id": organizacao.id,
            "razao_social": organizacao.razao_social,
            "papel": organizacao.papel.value,
            "licenca_numero": organizacao.licenca_numero,
            "licenca_validade": organizacao.licenca_validade,
            "dias_restantes": (organizacao.licenca_validade - hoje).days,
            "vencida": not organizacao.licenca_vigente(hoje),
        }
        for organizacao in sessao.scalars(consulta)
    ]
