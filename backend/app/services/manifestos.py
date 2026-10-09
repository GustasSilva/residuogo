"""Regras de negocio do manifesto, incluindo a maquina de estados.

Este e o modulo central do sistema. Tudo o que decide *se* uma operacao pode
acontecer esta aqui; os routers apenas recebem a requisicao e chamam estas
funcoes. Essa separacao e o que permite ao REST e ao SOAP compartilharem
exatamente o mesmo comportamento.

As oito regras do projeto e onde cada uma e aplicada:

* RN01 - so a organizacao do papel correto, e vinculada ao manifesto, executa
         cada transicao .............................. `_exigir_papel`
* RN02 - transicao fora do diagrama e recusada ....... `_aplicar_transicao`
* RN03 - cada transicao grava uma movimentacao ....... `_aplicar_transicao`
* RN04 - participantes ativos, com papel certo e licenca valida .... `emitir`
* RN05 - quantidade recebida obrigatoria; diferenca acima de 5% marca
         divergencia ................................. `registrar_recebimento`
* RN06 - recusa exige motivo; destinacao exige tipo .. schemas de entrada
* RN07 - o usuario so ve manifestos da propria organizacao ... `_exigir_visibilidade`
* RN08 - ao menos um item, com quantidade positiva ... schema `ManifestoCriar`

As regras RN06 e RN08 ficam nos schemas propositalmente: sao exigencias
sobre o *formato* da requisicao, e validadas ali o erro volta apontando o
campo exato, no formato RFC 7807.
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import config
from app.database import agora_utc
from app.enums import PapelOrganizacao, StatusManifesto
from app.errors import (
    PermissaoNegada,
    RecursoNaoEncontrado,
    RegraDeNegocio,
    TransicaoInvalida,
)
from app.models import ItemManifesto, Manifesto, Movimentacao, Organizacao, TipoResiduo, Usuario
from app.schemas import (
    CancelamentoEntrada,
    ColetaEntrada,
    DestinacaoEntrada,
    ManifestoCriar,
    RecebimentoEntrada,
    RecusaEntrada,
)
from app.services import organizacoes as servico_organizacoes
from app.validacoes import apenas_digitos, formatar_cnpj

# Diferenca tolerada entre a quantidade declarada e a recebida. Acima disso o
# item e marcado como divergente (regra RN05). Nao bloqueia o recebimento:
# serve de alerta na tela e entra no relatorio.
TOLERANCIA_DIVERGENCIA = 0.05


# A maquina de estados, declarada como dado e nao como sequencia de `if`.
#
#   status atual -> { status permitido : papel que tem autoridade }
#
# Ler o diagrama de estados deste dicionario e direto, e acrescentar uma
# transicao nova e acrescentar uma linha - sem tocar na logica que o percorre.
# Os estados que nao aparecem como chave (DESTINADO, RECUSADO, CANCELADO) sao
# finais: deles nao sai nenhuma transicao.
TRANSICOES: dict[StatusManifesto, dict[StatusManifesto, PapelOrganizacao]] = {
    StatusManifesto.EMITIDO: {
        StatusManifesto.EM_TRANSPORTE: PapelOrganizacao.TRANSPORTADOR,
        StatusManifesto.CANCELADO: PapelOrganizacao.GERADOR,
    },
    StatusManifesto.EM_TRANSPORTE: {
        StatusManifesto.RECEBIDO: PapelOrganizacao.DESTINADOR,
        StatusManifesto.RECUSADO: PapelOrganizacao.DESTINADOR,
    },
    StatusManifesto.RECEBIDO: {
        StatusManifesto.DESTINADO: PapelOrganizacao.DESTINADOR,
    },
}


# ---------------------------------------------------------------------------
# Verificacoes de permissao
# ---------------------------------------------------------------------------


def _organizacao_do_usuario(sessao: Session, usuario: Usuario) -> Organizacao:
    """Devolve a organizacao em nome da qual o usuario atua.

    O ADMIN nao tem organizacao: ele administra cadastros e consulta tudo, mas
    nao assume o papel de gerador, transportador ou destinador. Por isso nao
    pode executar transicoes - quem responde por elas e a empresa.
    """
    if usuario.organizacao_id is None:
        raise PermissaoNegada(
            "Usuários administradores não participam do fluxo do manifesto. "
            "Entre com um usuário vinculado a uma organização."
        )

    organizacao = sessao.get(Organizacao, usuario.organizacao_id)
    if organizacao is None:  # pragma: no cover - integridade garantida pela FK
        raise PermissaoNegada("A organização do usuário não foi encontrada.")
    return organizacao


def _id_do_participante(manifesto: Manifesto, papel: PapelOrganizacao) -> int:
    """Qual organizacao ocupa um determinado papel neste manifesto."""
    return {
        PapelOrganizacao.GERADOR: manifesto.gerador_id,
        PapelOrganizacao.TRANSPORTADOR: manifesto.transportador_id,
        PapelOrganizacao.DESTINADOR: manifesto.destinador_id,
    }[papel]


def _exigir_papel(usuario: Usuario, manifesto: Manifesto, papel: PapelOrganizacao) -> None:
    """Regra RN01: so o participante daquele papel executa a transicao.

    A regra tem duas condicoes: a organizacao precisa ter o papel certo **e**
    ser a indicada naquele manifesto. As duas estao escritas aqui para que a
    regra possa ser conferida contra a especificacao em um unico lugar.

    Na pratica a segunda condicao funciona como rede de seguranca: quem nao
    participa do manifesto ja e recusado antes, pela verificacao de
    visibilidade (RN07), que roda ao carregar o manifesto.
    """
    organizacao = usuario.organizacao
    if organizacao is None:
        raise PermissaoNegada(
            "Usuários administradores não executam transições de manifesto."
        )

    if organizacao.papel is not papel:
        raise PermissaoNegada(
            f"Esta ação é do {papel.value.lower()}, e sua organização é "
            f"{organizacao.papel.value.lower()}."
        )

    if organizacao.id != _id_do_participante(manifesto, papel):
        raise PermissaoNegada(
            f"Sua organização não é o {papel.value.lower()} indicado neste manifesto."
        )


def _exigir_visibilidade(usuario: Usuario, manifesto: Manifesto) -> None:
    """Regra RN07: o usuario so ve manifestos da propria organizacao.

    O ADMIN e a excecao e enxerga todos, porque precisa dar suporte e auditar.
    """
    if usuario.e_admin:
        return

    if usuario.organizacao_id not in manifesto.participantes_ids():
        # Responder 403 confirma que o manifesto existe. Isso e aceitavel aqui
        # porque o numero do manifesto nao e segredo - ele e impresso no
        # documento que acompanha a carga.
        raise PermissaoNegada("Sua organização não participa deste manifesto.")


# ---------------------------------------------------------------------------
# O coracao da maquina de estados
# ---------------------------------------------------------------------------


def _aplicar_transicao(
    sessao: Session,
    usuario: Usuario,
    manifesto: Manifesto,
    novo_status: StatusManifesto,
    observacao: str | None = None,
) -> None:
    """Muda o status do manifesto, validando e registrando a mudanca.

    Unico ponto do sistema que altera `manifesto.status`. Toda transicao passa
    por aqui, e por isso as regras RN02 e RN03 valem sempre, sem depender de
    cada rota se lembrar de aplica-las.

    A movimentacao e gravada na mesma sessao da mudanca de status: as duas vao
    para o banco no mesmo `commit`, ou nenhuma vai. Nao existe status alterado
    sem registro no historico.
    """
    destinos_permitidos = TRANSICOES.get(manifesto.status, {})

    # Regra RN02.
    if novo_status not in destinos_permitidos:
        if not destinos_permitidos:
            detalhe = (
                f"O manifesto {manifesto.numero} está {manifesto.status.value}, "
                f"que é um estado final, e não admite novas alterações."
            )
        else:
            possiveis = ", ".join(sorted(status.value for status in destinos_permitidos))
            detalhe = (
                f"O manifesto {manifesto.numero} está {manifesto.status.value} e não "
                f"pode ir para {novo_status.value}. Transições possíveis: {possiveis}."
            )
        raise TransicaoInvalida(detalhe)

    # Regra RN01.
    _exigir_papel(usuario, manifesto, destinos_permitidos[novo_status])

    status_anterior = manifesto.status
    manifesto.status = novo_status

    # Regra RN03.
    sessao.add(
        Movimentacao(
            manifesto_id=manifesto.id,
            status_anterior=status_anterior,
            status_novo=novo_status,
            usuario_id=usuario.id,
            observacao=observacao,
        )
    )


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------


def _consulta_completa() -> Select:
    """Consulta de manifesto com os relacionamentos ja carregados.

    `selectinload` busca os relacionados em poucas consultas adicionais, em
    vez de uma consulta por manifesto (o problema conhecido como N+1).
    """
    return select(Manifesto).options(
        selectinload(Manifesto.gerador),
        selectinload(Manifesto.transportador),
        selectinload(Manifesto.destinador),
        selectinload(Manifesto.itens).selectinload(ItemManifesto.tipo_residuo),
    )


def buscar(sessao: Session, usuario: Usuario, manifesto_id: int) -> Manifesto:
    """Carrega um manifesto, conferindo a visibilidade (RN07)."""
    manifesto = sessao.scalar(_consulta_completa().where(Manifesto.id == manifesto_id))
    if manifesto is None:
        raise RecursoNaoEncontrado(f"Manifesto {manifesto_id} não encontrado.")

    _exigir_visibilidade(usuario, manifesto)
    return manifesto


def buscar_por_token(sessao: Session, usuario: Usuario, token: str) -> Manifesto:
    """Resolve o token impresso no QR code para o manifesto correspondente."""
    manifesto = sessao.scalar(_consulta_completa().where(Manifesto.qr_token == token))
    if manifesto is None:
        raise RecursoNaoEncontrado("QR code não corresponde a nenhum manifesto.")

    _exigir_visibilidade(usuario, manifesto)
    return manifesto


def _inicio_do_dia_em_utc(dia: date) -> datetime:
    """Converte uma data local no instante UTC em que aquele dia comeca.

    Os filtros de periodo chegam como data ("2026-10-01"), mas as datas sao
    gravadas em UTC. Sem esta conversao, um manifesto emitido as 22h de
    Goiania (01h do dia seguinte em UTC) cairia no dia errado do filtro.
    """
    local = datetime.combine(dia, time.min, tzinfo=ZoneInfo(config.fuso_local))
    return local.astimezone(timezone.utc)


def montar_consulta(
    usuario: Usuario,
    *,
    status: StatusManifesto | None = None,
    inicio: date | None = None,
    fim: date | None = None,
    participante_id: int | None = None,
    numero: str | None = None,
) -> Select:
    """Monta a consulta da listagem, com a visibilidade ja aplicada.

    Devolve a consulta em vez de executa-la para que a rota possa pagina-la.
    O recorte da regra RN07 e feito em SQL, e nao filtrando o resultado depois:
    assim a contagem total da paginacao tambem respeita a regra.
    """
    consulta = _consulta_completa()

    # Regra RN07, aplicada antes de qualquer filtro opcional.
    if not usuario.e_admin:
        propria = usuario.organizacao_id
        consulta = consulta.where(
            or_(
                Manifesto.gerador_id == propria,
                Manifesto.transportador_id == propria,
                Manifesto.destinador_id == propria,
            )
        )

    if status is not None:
        consulta = consulta.where(Manifesto.status == status)

    if inicio is not None:
        consulta = consulta.where(Manifesto.emitido_em >= _inicio_do_dia_em_utc(inicio))

    if fim is not None:
        # O dia final entra inteiro: compara-se com o inicio do dia seguinte.
        consulta = consulta.where(
            Manifesto.emitido_em < _inicio_do_dia_em_utc(fim + timedelta(days=1))
        )

    if participante_id is not None:
        consulta = consulta.where(
            or_(
                Manifesto.gerador_id == participante_id,
                Manifesto.transportador_id == participante_id,
                Manifesto.destinador_id == participante_id,
            )
        )

    if numero:
        consulta = consulta.where(Manifesto.numero.ilike(f"%{numero.strip()}%"))

    return consulta.order_by(Manifesto.emitido_em.desc())


def historico(sessao: Session, usuario: Usuario, manifesto_id: int) -> list[Movimentacao]:
    """Linha do tempo do manifesto, da emissao ao estado atual."""
    manifesto = buscar(sessao, usuario, manifesto_id)

    return list(
        sessao.scalars(
            select(Movimentacao)
            .options(selectinload(Movimentacao.usuario))
            .where(Movimentacao.manifesto_id == manifesto.id)
            .order_by(Movimentacao.data_hora, Movimentacao.id)
        )
    )


def consultar_por_numero(sessao: Session, numero: str, cnpj_consultante: str) -> Manifesto:
    """Localiza um manifesto pelo numero, conferindo se quem pergunta participa dele.

    Usada pelo servico SOAP. E a mesma regra de visibilidade da RN07, aplicada
    sobre o CNPJ em vez do usuario autenticado, porque o consumidor SOAP se
    identifica pelo CNPJ.

    A entrada e normalizada (espacos, maiusculas e pontuacao do CNPJ) porque o
    numero costuma ser digitado a partir de um documento impresso.
    """
    numero_normalizado = numero.strip().upper()

    manifesto = sessao.scalar(_consulta_completa().where(Manifesto.numero == numero_normalizado))
    if manifesto is None:
        raise RecursoNaoEncontrado(f"Manifesto {numero_normalizado} não encontrado.")

    cnpj = apenas_digitos(cnpj_consultante)
    participantes = {
        manifesto.gerador.cnpj,
        manifesto.transportador.cnpj,
        manifesto.destinador.cnpj,
    }

    if cnpj not in participantes:
        raise PermissaoNegada(
            f"O CNPJ {formatar_cnpj(cnpj)} não participa do manifesto "
            f"{numero_normalizado} e por isso não pode consultá-lo."
        )

    return manifesto


# ---------------------------------------------------------------------------
# Emissao
# ---------------------------------------------------------------------------


def ha_divergencia(quantidade_declarada: float, quantidade_recebida: float) -> bool:
    """Diz se a diferenca entre declarado e recebido passa da tolerancia (RN05).

    Em funcao propria para que o recebimento e a carga de dados de
    demonstracao apliquem exatamente o mesmo critario.
    """
    diferenca = abs(quantidade_recebida - quantidade_declarada)
    return (diferenca / quantidade_declarada) > TOLERANCIA_DIVERGENCIA


def numero_do_manifesto(manifesto: Manifesto) -> str:
    """Monta o numero no formato RGO-AAAA-NNNNNN.

    O sequencial e o proprio id da linha, o que garante unicidade sem nenhum
    controle de concorrencia: o banco nunca entrega o mesmo id duas vezes. O
    ano usa o fuso local, para que um manifesto emitido a noite do dia 31 de
    dezembro nao receba o numero do ano seguinte.
    """
    ano = manifesto.emitido_em.astimezone(ZoneInfo(config.fuso_local)).year
    return f"RGO-{ano}-{manifesto.id:06d}"


def _carregar_tipos_de_residuo(sessao: Session, dados: ManifestoCriar) -> None:
    """Confere que todos os tipos de residuo informados existem.

    Verificar antes de gravar permite apontar quais codigos estao errados, em
    vez de deixar o banco recusar com uma mensagem de chave estrangeira.
    """
    pedidos = {item.tipo_residuo_id for item in dados.itens}
    encontrados = set(
        sessao.scalars(select(TipoResiduo.id).where(TipoResiduo.id.in_(pedidos)))
    )

    faltando = sorted(pedidos - encontrados)
    if faltando:
        raise RegraDeNegocio(
            "Tipo de resíduo não encontrado no catálogo: "
            + ", ".join(str(identificador) for identificador in faltando)
        )


def emitir(sessao: Session, usuario: Usuario, dados: ManifestoCriar) -> Manifesto:
    """Emite um manifesto. E a unica forma de criar um.

    Aplica a regra RN04 nos tres participantes antes de gravar qualquer coisa:
    emitir um manifesto para uma transportadora sem licenca valida produziria
    um documento que nao comprova nada.

    A exigencia de ao menos um item com quantidade positiva (RN08) ja foi
    validada pelo schema `ManifestoCriar`.
    """
    gerador = _organizacao_do_usuario(sessao, usuario)

    # O gerador e verificado como os demais: quem emite tambem precisa estar
    # ativo e com licenca valida.
    servico_organizacoes.exigir_apta(gerador, PapelOrganizacao.GERADOR, "gerador")

    transportador = servico_organizacoes.buscar(sessao, dados.transportador_id)
    servico_organizacoes.exigir_apta(
        transportador, PapelOrganizacao.TRANSPORTADOR, "transportador"
    )

    destinador = servico_organizacoes.buscar(sessao, dados.destinador_id)
    servico_organizacoes.exigir_apta(destinador, PapelOrganizacao.DESTINADOR, "destinador")

    _carregar_tipos_de_residuo(sessao, dados)

    manifesto = Manifesto(
        gerador_id=gerador.id,
        transportador_id=transportador.id,
        destinador_id=destinador.id,
        status=StatusManifesto.EMITIDO,
        observacoes=dados.observacoes,
    )
    sessao.add(manifesto)

    # `flush` envia o INSERT e preenche o id, sem encerrar a transacao. O id e
    # necessario para montar o numero e para vincular os itens.
    sessao.flush()
    manifesto.numero = numero_do_manifesto(manifesto)

    for item in dados.itens:
        sessao.add(
            ItemManifesto(
                manifesto_id=manifesto.id,
                tipo_residuo_id=item.tipo_residuo_id,
                quantidade_declarada=item.quantidade_declarada,
                unidade=item.unidade,
                acondicionamento=item.acondicionamento,
            )
        )

    # A emissao tambem e uma movimentacao, com status anterior nulo. Sem ela, a
    # linha do tempo do manifesto comecaria vazia.
    sessao.add(
        Movimentacao(
            manifesto_id=manifesto.id,
            status_anterior=None,
            status_novo=StatusManifesto.EMITIDO,
            usuario_id=usuario.id,
            observacao="Manifesto emitido.",
        )
    )

    sessao.commit()
    sessao.refresh(manifesto)
    return manifesto


# ---------------------------------------------------------------------------
# Transicoes
# ---------------------------------------------------------------------------


def confirmar_coleta(
    sessao: Session, usuario: Usuario, manifesto_id: int, dados: ColetaEntrada
) -> Manifesto:
    """O transportador assume a carga: EMITIDO -> EM_TRANSPORTE."""
    manifesto = buscar(sessao, usuario, manifesto_id)

    _aplicar_transicao(
        sessao, usuario, manifesto, StatusManifesto.EM_TRANSPORTE, dados.observacao
    )

    manifesto.placa_veiculo = dados.placa_veiculo.strip().upper()
    manifesto.motorista_nome = dados.motorista_nome.strip()
    manifesto.coletado_em = agora_utc()

    sessao.commit()
    sessao.refresh(manifesto)
    return manifesto


def registrar_recebimento(
    sessao: Session, usuario: Usuario, manifesto_id: int, dados: RecebimentoEntrada
) -> Manifesto:
    """O destinador confere a carga: EM_TRANSPORTE -> RECEBIDO.

    Implementa a regra RN05. Todos os itens precisam ser conferidos, e cada um
    recebe a marca de divergente quando a diferenca entre o declarado e o
    recebido passa da tolerancia. A divergencia nao impede o recebimento: ela
    e registrada, aparece na tela e entra no relatorio.
    """
    manifesto = buscar(sessao, usuario, manifesto_id)

    _aplicar_transicao(sessao, usuario, manifesto, StatusManifesto.RECEBIDO, dados.observacao)

    itens_do_manifesto = {item.id: item for item in manifesto.itens}
    informados = {item.item_id for item in dados.itens}

    desconhecidos = sorted(informados - itens_do_manifesto.keys())
    if desconhecidos:
        raise RegraDeNegocio(
            "Estes itens não pertencem a este manifesto: "
            + ", ".join(str(identificador) for identificador in desconhecidos)
        )

    nao_conferidos = sorted(itens_do_manifesto.keys() - informados)
    if nao_conferidos:
        raise RegraDeNegocio(
            "Informe a quantidade recebida de todos os itens. Faltaram os itens: "
            + ", ".join(str(identificador) for identificador in nao_conferidos)
        )

    for informado in dados.itens:
        item = itens_do_manifesto[informado.item_id]
        item.quantidade_recebida = informado.quantidade_recebida

        item.divergente = ha_divergencia(
            item.quantidade_declarada, informado.quantidade_recebida
        )

    manifesto.recebido_em = agora_utc()

    sessao.commit()
    sessao.refresh(manifesto)
    return manifesto


def recusar(
    sessao: Session, usuario: Usuario, manifesto_id: int, dados: RecusaEntrada
) -> Manifesto:
    """O destinador rejeita a carga: EM_TRANSPORTE -> RECUSADO.

    O motivo e obrigatorio (regra RN06, validada no schema) e fica gravado no
    manifesto, nao apenas no historico: e ele que justifica o retorno da carga.
    """
    manifesto = buscar(sessao, usuario, manifesto_id)

    _aplicar_transicao(
        sessao, usuario, manifesto, StatusManifesto.RECUSADO, dados.motivo_recusa
    )
    manifesto.motivo_recusa = dados.motivo_recusa.strip()

    sessao.commit()
    sessao.refresh(manifesto)
    return manifesto


def informar_destinacao(
    sessao: Session, usuario: Usuario, manifesto_id: int, dados: DestinacaoEntrada
) -> Manifesto:
    """O destinador encerra o ciclo: RECEBIDO -> DESTINADO.

    `destinado_em` e a data que os relatorios de massa destinada usam como
    referencia, por ser a data do fato ambiental - e nao a da emissao, que e
    apenas a data do documento.
    """
    manifesto = buscar(sessao, usuario, manifesto_id)

    _aplicar_transicao(sessao, usuario, manifesto, StatusManifesto.DESTINADO, dados.observacao)

    manifesto.tipo_destinacao = dados.tipo_destinacao
    manifesto.destinado_em = agora_utc()

    sessao.commit()
    sessao.refresh(manifesto)
    return manifesto


def cancelar(
    sessao: Session, usuario: Usuario, manifesto_id: int, dados: CancelamentoEntrada
) -> Manifesto:
    """O gerador desiste da operacao: EMITIDO -> CANCELADO.

    Possivel apenas antes da coleta. Depois que a carga esta na estrada, o
    caminho e a recusa pelo destinador, que deixa registro de onde o residuo
    esteve - cancelar nesse ponto apagaria o rastro.
    """
    manifesto = buscar(sessao, usuario, manifesto_id)

    _aplicar_transicao(sessao, usuario, manifesto, StatusManifesto.CANCELADO, dados.observacao)

    sessao.commit()
    sessao.refresh(manifesto)
    return manifesto
