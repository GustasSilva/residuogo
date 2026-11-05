"""Web service do ResíduoGO e página que o consome.

Para executar, a partir da raiz do projeto:

    uvicorn app.main:app --reload

* http://127.0.0.1:8000       - página de consulta
* http://127.0.0.1:8000/docs  - documentação da API

O código fica em tres camadas, e cada uma só chama a de baixo:

* rotas/     recebe as requisições e responde em JSON, CSV ou PDF
* servicos/  as regras: de onde a pessoa busca e quais pontos mostrar
* apis/      um arquivo por API externa (IBGE, ViaCEP e Nominatim), todas com cache
"""

import logging

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from app import config
from app.erros import registrar_handlers
from app.rotas import api

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s", datefmt="%H:%M:%S")

app = FastAPI(
    title="ResíduoGO",
    version="2.0.0",
    description=(
        "Consulta de pontos de coleta de resíduos no estado de Goiás. Reúne dados do IBGE, "
        "do ViaCEP e do OpenStreetMap (pelo Nominatim). Os erros seguem a RFC 9457."
    ),
)
registrar_handlers(app)
app.include_router(api.router)


@app.middleware("http")
async def marcar_cache(request: Request, seguir) -> Response:
    """Diz ao cliente se a resposta pode ser reaproveitada, como pede a restrição de cache do REST."""
    resposta = await seguir(request)
    if request.url.path.startswith("/api/"):
        resposta.headers["Cache-Control"] = "public, max-age=3600" if resposta.status_code == 200 else "no-store"
    return resposta



# Fica por último para não encobrir as rotas /api e /docs.
app.mount("/", StaticFiles(directory=config.PASTA_WEB, html=True), name="web")
