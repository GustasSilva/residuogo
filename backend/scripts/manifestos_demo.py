"""Geração dos manifestos de demonstração.

Separado de `seed.py` porque é a parte mais extensa da carga: cria cerca de 40
manifestos distribuídos pelos últimos seis meses, em todos os status, para que
a listagem, os relatórios e o painel tenham dados realistas.

Dois cuidados que fazem a diferença nos dados gerados:

* **os manifestos são retroativos.** O serviço de emissão sempre marca a data
  atual, o que é correto em uso real, mas produziria quarenta manifestos no
  mesmo dia. Aqui as datas são escritas explicitamente, respeitando a ordem
  natural (emissão → coleta → recebimento → destinação);
* **a destinação combina com o destinador.** O aterro aterra e a cooperativa
  recicla. Sem isso, a taxa de desvio de aterro ficaria aleatória e o painel
  não contaria nada.

O sorteio usa semente fixa: a carga é aleatória, mas sempre a mesma. Assim os
números mostrados na apresentação não mudam entre uma execução e outra.
"""

import random
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import config
from app.enums import (
    Acondicionamento,
    PapelOrganizacao,
    StatusManifesto,
    TipoDestinacao,
    UnidadeMedida,
)
from app.models import ItemManifesto, Manifesto, Movimentacao, Organizacao, TipoResiduo, Usuario
from app.services.manifestos import ha_divergencia, numero_do_manifesto

SEMENTE = 42
TOTAL_MESES = 6

# Quantos manifestos em cada status. A maioria concluída, porque é o estado
# normal de um manifesto antigo; os demais representam o movimento do dia.
DISTRIBUICAO = {
    StatusManifesto.DESTINADO: 24,
    StatusManifesto.RECEBIDO: 5,
    StatusManifesto.EM_TRANSPORTE: 4,
    StatusManifesto.EMITIDO: 3,
    StatusManifesto.RECUSADO: 2,
    StatusManifesto.CANCELADO: 2,
}

# Faixa de quantidade plausível para cada unidade de medida.
FAIXA_POR_UNIDADE = {
    UnidadeMedida.T: (1.0, 28.0),
    UnidadeMedida.KG: (80.0, 4800.0),
    UnidadeMedida.L: (40.0, 1800.0),
    UnidadeMedida.M3: (2.0, 45.0),
}

# Tratamentos que cada destinador costuma aplicar, pela palavra-chave no nome.
DESTINACOES_POR_DESTINADOR = {
    "Aterro": [TipoDestinacao.ATERRO] * 8 + [TipoDestinacao.INCINERACAO] * 2,
    "Cooperativa": (
        [TipoDestinacao.RECICLAGEM] * 6
        + [TipoDestinacao.COMPOSTAGEM] * 3
        + [TipoDestinacao.COPROCESSAMENTO] * 1
    ),
}

MOTIVOS_DE_RECUSA = [
    "Carga apresentava resíduo não declarado no manifesto.",
    "Acondicionamento rompido durante o transporte, com risco de vazamento.",
    "Quantidade recebida incompatível com a declarada, sem justificativa.",
]

ACONDICIONAMENTOS_POR_UNIDADE = {
    UnidadeMedida.T: [Acondicionamento.CACAMBA, Acondicionamento.GRANEL, Acondicionamento.BIG_BAG],
    UnidadeMedida.KG: [Acondicionamento.TAMBOR, Acondicionamento.BIG_BAG, Acondicionamento.OUTRO],
    UnidadeMedida.L: [Acondicionamento.BOMBONA, Acondicionamento.TAMBOR],
    UnidadeMedida.M3: [Acondicionamento.CACAMBA, Acondicionamento.GRANEL],
}


def _para_utc(momento_local: datetime) -> datetime:
    """Converte um horário local de Goiás no instante UTC correspondente."""
    return momento_local.replace(tzinfo=ZoneInfo(config.fuso_local)).astimezone(timezone.utc)


def _horario_comercial(sorteio: random.Random, dia: datetime) -> datetime:
    """Sorteia um horário de expediente no dia informado."""
    return _para_utc(
        datetime.combine(
            dia.date(), time(hour=sorteio.randint(7, 17), minute=sorteio.choice([0, 15, 30, 45]))
        )
    )


def _destinacao_de(destinador: Organizacao, sorteio: random.Random) -> TipoDestinacao:
    """Escolhe um tratamento coerente com o tipo de destinador."""
    for palavra_chave, opcoes in DESTINACOES_POR_DESTINADOR.items():
        if palavra_chave.lower() in destinador.razao_social.lower():
            return sorteio.choice(opcoes)
    return TipoDestinacao.OUTRO_TRATAMENTO


def _criar_itens(
    sorteio: random.Random, manifesto: Manifesto, tipos: list[TipoResiduo]
) -> list[ItemManifesto]:
    """Monta de um a três itens, com unidade e acondicionamento coerentes."""
    itens = []

    for tipo in sorteio.sample(tipos, k=sorteio.randint(1, 3)):
        minimo, maximo = FAIXA_POR_UNIDADE[tipo.unidade_padrao]
        itens.append(
            ItemManifesto(
                manifesto_id=manifesto.id,
                tipo_residuo_id=tipo.id,
                quantidade_declarada=round(sorteio.uniform(minimo, maximo), 3),
                unidade=tipo.unidade_padrao,
                acondicionamento=sorteio.choice(
                    ACONDICIONAMENTOS_POR_UNIDADE[tipo.unidade_padrao]
                ),
            )
        )

    return itens


def _conferir_itens(sorteio: random.Random, itens: list[ItemManifesto]) -> None:
    """Preenche a quantidade recebida de cada item, gerando divergências.

    Em quatro de cada cinco itens o recebido fica dentro da tolerância; no
    restante a diferença é grande o bastante para marcar divergência — é o que
    dá ao relatório algo para apontar.
    """
    for item in itens:
        if sorteio.random() < 0.8:
            fator = sorteio.uniform(0.97, 1.03)  # dentro dos 5%
        else:
            fator = sorteio.choice([sorteio.uniform(0.70, 0.92), sorteio.uniform(1.08, 1.25)])

        item.quantidade_recebida = round(item.quantidade_declarada * fator, 3)
        # Mesmo critério do recebimento pela API (regra RN05).
        item.divergente = ha_divergencia(item.quantidade_declarada, item.quantidade_recebida)


def criar(sessao: Session) -> int:
    """Cria os manifestos de demonstração. Devolve quantos foram criados.

    Precisa ser chamada depois de as organizações, os usuários e os tipos de
    resíduo já estarem gravados.
    """
    sorteio = random.Random(SEMENTE)

    organizacoes = list(sessao.scalars(select(Organizacao)))
    tipos = list(sessao.scalars(select(TipoResiduo)))
    usuarios = list(sessao.scalars(select(Usuario)))

    por_papel = {papel: [o for o in organizacoes if o.papel is papel] for papel in PapelOrganizacao}
    usuario_da_organizacao = {u.organizacao_id: u for u in usuarios if u.organizacao_id}

    # Apenas a transportadora com licença válida participa dos manifestos: a
    # outra existe para demonstrar a recusa da emissão (RN04).
    transportadoras = [
        organizacao
        for organizacao in por_papel[PapelOrganizacao.TRANSPORTADOR]
        if organizacao.licenca_vigente()
    ]

    agora = datetime.now(ZoneInfo(config.fuso_local))
    primeiro_dia = agora - timedelta(days=30 * TOTAL_MESES)

    status_sorteados = [
        status for status, quantidade in DISTRIBUICAO.items() for _ in range(quantidade)
    ]
    sorteio.shuffle(status_sorteados)

    # A coluna `atualizado_em` tem `onupdate`: o SQLAlchemy a sobrescreve com o
    # horário atual em qualquer UPDATE. Como este script altera o manifesto
    # depois de inseri-lo (para gravar o número e as datas), o valor histórico
    # seria perdido. A solução é guardá-lo aqui e aplicá-lo no fim, em um
    # UPDATE que informa a coluna explicitamente — o que desativa o `onupdate`.
    datas_de_atualizacao: list[tuple[int, datetime]] = []

    for indice, status in enumerate(status_sorteados):
        gerador = sorteio.choice(por_papel[PapelOrganizacao.GERADOR])
        transportador = sorteio.choice(transportadoras)
        destinador = sorteio.choice(por_papel[PapelOrganizacao.DESTINADOR])

        # Manifestos ainda em andamento ficam nos últimos dias; os concluídos
        # se espalham pelos seis meses. É o que se vê num sistema em uso.
        em_andamento = status in {
            StatusManifesto.EMITIDO,
            StatusManifesto.EM_TRANSPORTE,
            StatusManifesto.RECEBIDO,
        }
        if em_andamento:
            dia_emissao = agora - timedelta(days=sorteio.randint(0, 6))
        else:
            avanco = (indice / len(status_sorteados)) * (agora - primeiro_dia).days
            dia_emissao = primeiro_dia + timedelta(days=avanco + sorteio.randint(0, 4))

        emitido_em = _horario_comercial(sorteio, dia_emissao)

        manifesto = Manifesto(
            gerador_id=gerador.id,
            transportador_id=transportador.id,
            destinador_id=destinador.id,
            status=status,
            emitido_em=emitido_em,
            atualizado_em=emitido_em,
            observacoes=sorteio.choice(
                [None, "Coleta programada mensal.", "Retirada extraordinária.", None]
            ),
        )
        sessao.add(manifesto)
        sessao.flush()
        manifesto.numero = numero_do_manifesto(manifesto)

        itens = _criar_itens(sorteio, manifesto, tipos)
        sessao.add_all(itens)

        # A linha do tempo é montada em paralelo às datas, para que o
        # histórico conte a mesma história que as colunas do manifesto (RN03).
        passos: list[tuple[StatusManifesto | None, StatusManifesto, datetime, int, str]] = [
            (
                None,
                StatusManifesto.EMITIDO,
                emitido_em,
                usuario_da_organizacao[gerador.id].id,
                "Manifesto emitido.",
            )
        ]

        if status is StatusManifesto.CANCELADO:
            cancelado_em = emitido_em + timedelta(hours=sorteio.randint(1, 20))
            passos.append(
                (
                    StatusManifesto.EMITIDO,
                    StatusManifesto.CANCELADO,
                    cancelado_em,
                    usuario_da_organizacao[gerador.id].id,
                    "Cancelado pelo gerador antes da coleta.",
                )
            )
            manifesto.atualizado_em = cancelado_em

        elif status is not StatusManifesto.EMITIDO:
            coletado_em = emitido_em + timedelta(days=sorteio.randint(1, 2))
            manifesto.coletado_em = coletado_em
            manifesto.placa_veiculo = (
                f"{sorteio.choice(['ABC', 'GOI', 'RVD', 'ANP'])}"
                f"{sorteio.randint(1, 9)}{sorteio.choice('DEFG')}{sorteio.randint(10, 99)}"
            )
            manifesto.motorista_nome = sorteio.choice(
                [
                    "Antônio Ribeiro da Costa",
                    "Jair Mendes Oliveira",
                    "Sebastião Luz Pereira",
                    "Valdir Souza Martins",
                ]
            )
            passos.append(
                (
                    StatusManifesto.EMITIDO,
                    StatusManifesto.EM_TRANSPORTE,
                    coletado_em,
                    usuario_da_organizacao[transportador.id].id,
                    f"Coleta confirmada. Veículo {manifesto.placa_veiculo}.",
                )
            )
            manifesto.atualizado_em = coletado_em

            if status is StatusManifesto.RECUSADO:
                recusado_em = coletado_em + timedelta(hours=sorteio.randint(6, 30))
                manifesto.motivo_recusa = sorteio.choice(MOTIVOS_DE_RECUSA)
                passos.append(
                    (
                        StatusManifesto.EM_TRANSPORTE,
                        StatusManifesto.RECUSADO,
                        recusado_em,
                        usuario_da_organizacao[destinador.id].id,
                        manifesto.motivo_recusa,
                    )
                )
                manifesto.atualizado_em = recusado_em

            elif status is not StatusManifesto.EM_TRANSPORTE:
                recebido_em = coletado_em + timedelta(hours=sorteio.randint(4, 28))
                manifesto.recebido_em = recebido_em
                _conferir_itens(sorteio, itens)
                passos.append(
                    (
                        StatusManifesto.EM_TRANSPORTE,
                        StatusManifesto.RECEBIDO,
                        recebido_em,
                        usuario_da_organizacao[destinador.id].id,
                        "Carga conferida no recebimento.",
                    )
                )
                manifesto.atualizado_em = recebido_em

                if status is StatusManifesto.DESTINADO:
                    destinado_em = recebido_em + timedelta(days=sorteio.randint(1, 4))
                    manifesto.tipo_destinacao = _destinacao_de(destinador, sorteio)
                    manifesto.destinado_em = destinado_em
                    passos.append(
                        (
                            StatusManifesto.RECEBIDO,
                            StatusManifesto.DESTINADO,
                            destinado_em,
                            usuario_da_organizacao[destinador.id].id,
                            f"Destinação final: {manifesto.tipo_destinacao.value}.",
                        )
                    )
                    manifesto.atualizado_em = destinado_em

        for anterior, novo, momento, usuario_id, observacao in passos:
            sessao.add(
                Movimentacao(
                    manifesto_id=manifesto.id,
                    status_anterior=anterior,
                    status_novo=novo,
                    usuario_id=usuario_id,
                    data_hora=momento,
                    observacao=observacao,
                )
            )

        datas_de_atualizacao.append((manifesto.id, manifesto.atualizado_em))

    sessao.commit()

    for manifesto_id, momento in datas_de_atualizacao:
        sessao.execute(
            update(Manifesto).where(Manifesto.id == manifesto_id).values(atualizado_em=momento)
        )
    sessao.commit()

    return len(status_sorteados)
