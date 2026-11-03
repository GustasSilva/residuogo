"""Web service do ResiduoGO e pagina que o consome.

Para executar, a partir da raiz do projeto:

    uvicorn app.main:app --reload

* http://127.0.0.1:8000       - pagina de consulta
* http://127.0.0.1:8000/docs  - documentacao da API
"""

import csv
import io
import logging

from fastapi import Depends, FastAPI, Query, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import config, localizacao, pontos
from app.erros import DadosInvalidos, registrar_handlers
from app.materiais import MATERIAIS, para_saida
from app.schemas import Material, Municipio, RespostaPontos

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


# APS-TRECHO 1: As rotas do web service
def _consultar(
    local: str | None = Query(None, description="CEP, município, bairro ou endereço em Goiás.", examples=["74230-010"]),
    lat: float | None = Query(None, description="Latitude de um ponto em Goiás, junto com lon."),
    lon: float | None = Query(None, description="Longitude de um ponto em Goiás, junto com lat."),
    raio_km: int = Query(10, description="Distância máxima, em km."),
    material: str | None = Query(None, description="Chave de um item de /api/materiais."),
) -> dict:
    """Valida os parametros e faz a busca. Serve as rotas em JSON e em CSV."""
    tem_local = bool(local and local.strip())
    if tem_local == (lat is not None or lon is not None):
        raise DadosInvalidos("Informe um local ou um ponto no mapa, um dos dois.")
    if not config.RAIO_MINIMO_KM <= raio_km <= config.RAIO_MAXIMO_KM:
        raise DadosInvalidos(
            f"A distância precisa ficar entre {config.RAIO_MINIMO_KM} e {config.RAIO_MAXIMO_KM} km."
        )
    if material and material not in MATERIAIS:
        raise DadosInvalidos(f"O material {material} não existe. Veja a lista em /api/materiais.")

    if tem_local:
        origem = localizacao.origem_por_texto(local)
    else:
        origem = localizacao.origem_por_coordenadas(lat, lon)

    busca = pontos.buscar(origem["latitude"], origem["longitude"], raio_km, material)
    return {
        "origem": origem,
        "raio_km": raio_km,
        "material": material or None,
        "total": len(busca["pontos"]),
        **busca,
    }


@app.get("/api/pontos", response_model=RespostaPontos, summary="Pontos de coleta perto de um local ou ponto no mapa")
def buscar_pontos(resultado: dict = Depends(_consultar)) -> dict:
    return resultado


@app.get("/api/pontos.csv", summary="Mesma busca de /api/pontos, em planilha CSV")
def exportar_pontos(resultado: dict = Depends(_consultar)) -> Response:
    return Response(
        content=_planilha(resultado["pontos"]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="pontos-de-coleta.csv"'},
    )


@app.get("/api/municipios", response_model=list[Municipio], summary="Municípios de Goiás e suas regiões")
def listar_municipios() -> list[dict]:
    return localizacao.municipios()


@app.get("/api/materiais", response_model=list[Material], summary="Materiais aceitos no filtro da busca")
def listar_materiais() -> list[dict]:
    return para_saida(list(MATERIAIS))


@app.get("/api/goias", summary="Contorno oficial de Goiás (IBGE), em GeoJSON")
def contorno_de_goias() -> JSONResponse:
    return JSONResponse(localizacao.contorno_de_goias(), media_type="application/geo+json")
# APS-FIM


def _planilha(encontrados: list[dict]) -> str:
    saida = io.StringIO()
    # O Excel em portugues separa colunas por ponto e virgula e decimais por virgula.
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(["Nome", "Tipo", "Endereço", "Materiais", "Distância (km)", "Latitude", "Longitude"])
    for ponto in encontrados:
        materiais = ", ".join(item["rotulo"] for item in ponto["materiais"]) or "Não informado"
        escritor.writerow(
            [
                _celula_segura(ponto["nome"]),
                ponto["tipo"],
                _celula_segura(ponto["endereco"]),
                materiais,
                _decimal(ponto["distancia_km"]),
                _decimal(ponto["latitude"]),
                _decimal(ponto["longitude"]),
            ]
        )
    # O BOM faz o Excel reconhecer os acentos.
    return "﻿" + saida.getvalue()


def _decimal(numero: float) -> str:
    return str(numero).replace(".", ",")


def _celula_segura(texto: str) -> str:
    """Os nomes vem de um mapa aberto: impede que o Excel execute um deles como formula."""
    return f"'{texto}" if texto[:1] in ("=", "+", "-", "@") else texto


# Fica por ultimo para nao encobrir as rotas /api e /docs.
app.mount("/", StaticFiles(directory=config.PASTA_WEB, html=True), name="web")
