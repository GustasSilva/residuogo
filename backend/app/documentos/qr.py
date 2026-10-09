"""QR code do manifesto.

O QR impresso no manifesto carrega o endereco da tela que abre aquele
manifesto, nao o seu identificador: quem recebe a carga aponta a camera e cai
direto na tela de recebimento, sem digitar numero nenhum.

O endereco usa o `qr_token` - um UUID aleatorio - e nao o id da linha. Uma
etiqueta com `/manifestos/41` revelaria quantos manifestos existem no sistema
e permitiria tentar ler o 42.
"""

import io

import qrcode

from app.config import config

# Tamanho de cada modulo (o quadradinho) em pixels, e a borda branca exigida
# pela especificacao do QR code, medida em modulos. Com 8 pixels a imagem sai
# legivel tanto na tela quanto impressa a 2,5 cm.
PIXELS_POR_MODULO = 8
BORDA_EM_MODULOS = 2


def endereco_do_manifesto(qr_token: str) -> str:
    """Endereco da tela que resolve o token (`/qr/<token>` no front-end)."""
    return f"{config.url_do_front.rstrip('/')}/qr/{qr_token}"


def imagem_png(conteudo: str) -> bytes:
    """Gera a imagem do QR code em PNG.

    Devolve os bytes em vez de gravar arquivo: a imagem e usada em dois
    lugares - a rota que a serve e o PDF do manifesto - e em nenhum deles
    precisa existir em disco.
    """
    imagem = qrcode.make(
        conteudo, box_size=PIXELS_POR_MODULO, border=BORDA_EM_MODULOS
    )

    arquivo_em_memoria = io.BytesIO()
    imagem.save(arquivo_em_memoria, format="PNG")
    return arquivo_em_memoria.getvalue()


def imagem_do_manifesto(qr_token: str) -> bytes:
    """Atalho: o QR code pronto de um manifesto, a partir do seu token."""
    return imagem_png(endereco_do_manifesto(qr_token))
