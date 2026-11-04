"""Web service do ResiduoGO e pagina que o consome.

Para executar, a partir da raiz do projeto:

    uvicorn app.main:app --reload

* http://127.0.0.1:8000       - pagina de consulta
* http://127.0.0.1:8000/docs  - documentacao da API

O codigo fica em tres camadas, e cada uma so chama a de baixo:

* rotas/     recebe as requisicoes e responde em JSON, CSV ou PDF
* servicos/  as regras: de onde a pessoa busca e quais pontos mostrar
* apis/      um arquivo por API externa (IBGE, ViaCEP e Nominatim), todas com cache
"""

import logging

from fastapi import FastAPI
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
        "do ViaCEP e do OpenStreetMap (pelo Nominatim). Os erros seguem a RFC 7807."
    ),
)
registrar_handlers(app)
app.include_router(api.router)

# Fica por ultimo para nao encobrir as rotas /api e /docs.
app.mount("/", StaticFiles(directory=config.PASTA_WEB, html=True), name="web")
