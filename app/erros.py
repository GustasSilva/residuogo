"""Erros previstos e respostas de erro no formato da RFC 7807."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("residuogo")


class ErroDaBusca(Exception):
    status = 400
    titulo = "Erro na requisição"

    def __init__(self, detalhe: str) -> None:
        super().__init__(detalhe)
        self.detalhe = detalhe


class DadosInvalidos(ErroDaBusca):
    status = 422
    titulo = "Dados inválidos"


class NaoEncontrado(ErroDaBusca):
    status = 404
    titulo = "Não encontrado"


class ServicoIndisponivel(ErroDaBusca):
    status = 503
    titulo = "Serviço externo indisponível"


# APS-TRECHO 7: Todas as respostas de erro no mesmo formato (RFC 7807)
def _problema(request: Request, status: int, titulo: str, detalhe: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "title": titulo,
            "status": status,
            "detail": detalhe,
            "instance": request.url.path,
        },
    )


def registrar_handlers(app: FastAPI) -> None:
    @app.exception_handler(ErroDaBusca)
    async def _erro_da_busca(request: Request, exc: ErroDaBusca) -> JSONResponse:
        return _problema(request, exc.status, exc.titulo, exc.detalhe)

    @app.exception_handler(RequestValidationError)
    async def _validacao(request: Request, exc: RequestValidationError) -> JSONResponse:
        campos = ", ".join(str(erro["loc"][-1]) for erro in exc.errors())
        return _problema(request, 422, "Dados inválidos", f"Valor inválido em: {campos}.")

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return _problema(request, 404, "Não encontrado", "Este endereço não existe.")
        return _problema(request, exc.status_code, "Erro na requisição", "A requisição não foi aceita.")

    @app.exception_handler(Exception)
    async def _inesperado(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Falha inesperada em %s", request.url.path)
        return _problema(request, 500, "Erro interno", "Ocorreu uma falha inesperada no servidor.")
# APS-FIM
