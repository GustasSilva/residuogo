"""Montagem das respostas paginadas.

Isola a parte chata da paginacao - contar o total e calcular o numero de
paginas - em um unico lugar, para que as rotas apenas descrevam *o que*
consultar e deleguem *como* paginar.
"""

import math
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.dependencies import ParametrosPagina


def paginar(sessao: Session, consulta: Select, parametros: ParametrosPagina) -> dict[str, Any]:
    """Executa a consulta em duas etapas e devolve o envelope da `Pagina`.

    Primeiro conta quantos registros atendem ao filtro, depois busca apenas a
    fatia da pagina pedida. Contar antes e necessario para o front-end saber
    quantas paginas existem; buscar so a fatia e o que mantem a resposta
    pequena mesmo com a tabela cheia.

    A contagem reaproveita a consulta recebida como subconsulta, de modo que
    os filtros aplicados pela rota valem para o total - um descuido comum e
    contar a tabela inteira e paginar um resultado filtrado.
    """
    total = sessao.scalar(select(func.count()).select_from(consulta.subquery())) or 0

    itens = sessao.scalars(
        consulta.limit(parametros.tamanho).offset(parametros.deslocamento)
    ).all()

    return {
        "itens": itens,
        "total": total,
        "pagina": parametros.pagina,
        "tamanho": parametros.tamanho,
        "paginas": math.ceil(total / parametros.tamanho) if total else 0,
    }
