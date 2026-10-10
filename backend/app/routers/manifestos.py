"""Rotas do manifesto.

Cada rota de transição é um POST para um sub-recurso que nomeia o evento
(`/coleta`, `/recebimento`, `/recusa`, `/destinacao`, `/cancelamento`), em vez
de um PUT que receberia o novo status. A diferença é importante: o cliente
descreve *o que aconteceu* e o servidor decide o status resultante — assim a
máquina de estados não pode ser contornada pela API.

As rotas não contêm regra de negócio: validam o formato pela assinatura e
delegam a `services/manifestos.py`.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.dependencies import PaginaParams, Sessao, UsuarioAtual
from app.documentos import pdf_manifesto, qr
from app.enums import StatusManifesto
from app.models import Manifesto, Movimentacao
from app.paginacao import paginar
from app.schemas import (
    CancelamentoEntrada,
    ColetaEntrada,
    DestinacaoEntrada,
    ManifestoCriar,
    ManifestoResumo,
    ManifestoSaida,
    MovimentacaoSaida,
    Pagina,
    RecebimentoEntrada,
    RecusaEntrada,
)
from app.services import manifestos as servico

router = APIRouter(prefix="/manifestos", tags=["Manifestos"])


# APS-TRECHO 1: Rotas REST — cada transição é um POST para um sub-recurso
@router.post(
    "",
    response_model=ManifestoSaida,
    status_code=status.HTTP_201_CREATED,
    summary="Emite um manifesto (GERADOR)",
)
def emitir(dados: ManifestoCriar, sessao: Sessao, usuario: UsuarioAtual) -> Manifesto:
    """Emite um manifesto em nome da organização do usuário.

    O gerador não é informado no corpo: é a organização de quem emite. Os
    participantes são validados quanto a papel, situação e licença (RN04).
    """
    return servico.emitir(sessao, usuario, dados)
# APS-FIM


@router.get(
    "",
    response_model=Pagina[ManifestoResumo],
    summary="Lista manifestos, com filtros",
)
def listar(
    sessao: Sessao,
    usuario: UsuarioAtual,
    paginacao: PaginaParams,
    status_filtro: Annotated[
        StatusManifesto | None, Query(alias="status", description="Filtra pelo status.")
    ] = None,
    inicio: Annotated[
        date | None, Query(description="Emitidos a partir desta data (inclusive).")
    ] = None,
    fim: Annotated[
        date | None, Query(description="Emitidos até esta data (inclusive).")
    ] = None,
    participante_id: Annotated[
        int | None, Query(description="Manifestos em que esta organização participa.")
    ] = None,
    numero: Annotated[str | None, Query(description="Busca por parte do número.")] = None,
) -> dict:
    """Lista os manifestos visíveis ao usuário.

    A regra RN07 é aplicada antes dos filtros: um usuário comum vê apenas os
    manifestos da própria organização, e o ADMIN vê todos.
    """
    consulta = servico.montar_consulta(
        usuario,
        status=status_filtro,
        inicio=inicio,
        fim=fim,
        participante_id=participante_id,
        numero=numero,
    )
    return paginar(sessao, consulta, paginacao)


@router.get(
    "/qr/{token}",
    response_model=ManifestoSaida,
    summary="Resolve o QR code para o manifesto",
)
def resolver_qr(token: str, sessao: Sessao, usuario: UsuarioAtual) -> Manifesto:
    """Abre o manifesto a partir do token impresso no QR code do documento."""
    return servico.buscar_por_token(sessao, usuario, token)


@router.get(
    "/{manifesto_id}",
    response_model=ManifestoSaida,
    summary="Detalhe do manifesto, com itens",
)
def detalhar(manifesto_id: int, sessao: Sessao, usuario: UsuarioAtual) -> Manifesto:
    return servico.buscar(sessao, usuario, manifesto_id)


@router.get(
    "/{manifesto_id}/historico",
    response_model=list[MovimentacaoSaida],
    summary="Linha do tempo das movimentações",
)
def historico(
    manifesto_id: int, sessao: Sessao, usuario: UsuarioAtual
) -> list[Movimentacao]:
    """Devolve todas as mudanças de status, da emissão ao estado atual."""
    return servico.historico(sessao, usuario, manifesto_id)


@router.get(
    "/{manifesto_id}/pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "Manifesto em PDF"}},
    summary="Manifesto em PDF, com QR code",
)
def documento_em_pdf(
    manifesto_id: int, sessao: Sessao, usuario: UsuarioAtual
) -> Response:
    """Gera o documento que acompanha a carga.

    É o manifesto impresso: participantes, resíduos, etapas e histórico, com
    um QR code que abre este mesmo manifesto na tela do sistema. Buscar pelo
    serviço antes de gerar é o que aplica a visibilidade (RN07) — o PDF de um
    manifesto de outra organização não é gerado.

    Vai como `inline` para abrir no visualizador do navegador: quem pede o
    documento normalmente quer conferi-lo antes de imprimir ou guardar.
    """
    manifesto = servico.buscar(sessao, usuario, manifesto_id)
    movimentacoes = servico.historico(sessao, usuario, manifesto_id)

    return Response(
        content=pdf_manifesto.gerar(manifesto, movimentacoes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="manifesto-{manifesto.numero}.pdf"'
        },
    )


@router.get(
    "/{manifesto_id}/qrcode.png",
    response_class=Response,
    responses={200: {"content": {"image/png": {}}, "description": "Imagem do QR code"}},
    summary="Imagem do QR code do manifesto",
)
def imagem_do_qrcode(
    manifesto_id: int, sessao: Sessao, usuario: UsuarioAtual
) -> Response:
    """Devolve só o QR code, para a tela exibi-lo sem baixar o PDF inteiro.

    O código aponta para o endereço do manifesto no front-end, montado a
    partir do `qr_token`, e não do id — a etiqueta não revela quantos
    manifestos existem no sistema.
    """
    manifesto = servico.buscar(sessao, usuario, manifesto_id)

    return Response(
        content=qr.imagem_do_manifesto(manifesto.qr_token),
        media_type="image/png",
    )


# APS-TRECHO 1: Rotas REST — cada transição é um POST para um sub-recurso
@router.post(
    "/{manifesto_id}/coleta",
    response_model=ManifestoSaida,
    summary="Confirma a coleta (TRANSPORTADOR)",
)
def confirmar_coleta(
    manifesto_id: int, dados: ColetaEntrada, sessao: Sessao, usuario: UsuarioAtual
) -> Manifesto:
    """EMITIDO → EM_TRANSPORTE, registrando veículo e motorista."""
    return servico.confirmar_coleta(sessao, usuario, manifesto_id, dados)


@router.post(
    "/{manifesto_id}/recebimento",
    response_model=ManifestoSaida,
    summary="Registra o recebimento da carga (DESTINADOR)",
)
def registrar_recebimento(
    manifesto_id: int, dados: RecebimentoEntrada, sessao: Sessao, usuario: UsuarioAtual
) -> Manifesto:
    """EM_TRANSPORTE → RECEBIDO, conferindo a quantidade de cada item (RN05)."""
    return servico.registrar_recebimento(sessao, usuario, manifesto_id, dados)
# APS-FIM


@router.post(
    "/{manifesto_id}/recusa",
    response_model=ManifestoSaida,
    summary="Recusa a carga (DESTINADOR)",
)
def recusar(
    manifesto_id: int, dados: RecusaEntrada, sessao: Sessao, usuario: UsuarioAtual
) -> Manifesto:
    """EM_TRANSPORTE → RECUSADO, com motivo obrigatório (RN06)."""
    return servico.recusar(sessao, usuario, manifesto_id, dados)


@router.post(
    "/{manifesto_id}/destinacao",
    response_model=ManifestoSaida,
    summary="Informa a destinação final (DESTINADOR)",
)
def informar_destinacao(
    manifesto_id: int, dados: DestinacaoEntrada, sessao: Sessao, usuario: UsuarioAtual
) -> Manifesto:
    """RECEBIDO → DESTINADO, com o tipo de tratamento aplicado (RN06)."""
    return servico.informar_destinacao(sessao, usuario, manifesto_id, dados)


@router.post(
    "/{manifesto_id}/cancelamento",
    response_model=ManifestoSaida,
    summary="Cancela o manifesto (GERADOR)",
)
def cancelar(
    manifesto_id: int, dados: CancelamentoEntrada, sessao: Sessao, usuario: UsuarioAtual
) -> Manifesto:
    """EMITIDO → CANCELADO. Possível apenas antes da coleta."""
    return servico.cancelar(sessao, usuario, manifesto_id, dados)
