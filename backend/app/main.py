"""Web service do ResiduoGO e pagina que o consome.

Para executar, a partir da pasta `backend`:

    uvicorn app.main:app --reload

* http://127.0.0.1:8000       - pagina de consulta
* http://127.0.0.1:8000/docs  - documentacao da API
"""

import csv
import io
import logging

from fastapi import FastAPI, Query, Response
from fastapi.staticfiles import StaticFiles

from app import config, localizacao, pontos
from app.errors import DadosInvalidos, registrar_handlers
from app.materiais import MATERIAIS, para_saida
from app.schemas import Material, Municipio, RespostaPontos

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s", datefmt="%H:%M:%S")

app = FastAPI(
    title="ResíduoGO",
    version="2.0.0",
    description=(
        "Consulta de pontos de coleta de resíduos no estado de Goiás. Reúne dados do IBGE, "
        "do ViaCEP e do OpenStreetMap (Nominatim e Overpass). Os erros seguem a RFC 7807."
    ),
)
registrar_handlers(app)


# APS-TRECHO 6: As rotas do web service
def _consultar(cep: str | None, municipio: str | None, raio_km: int, material: str | None) -> dict:
    if bool(cep) == bool(municipio):
        raise DadosInvalidos("Informe o CEP ou o município, um dos dois.")
    if not config.RAIO_MINIMO_KM <= raio_km <= config.RAIO_MAXIMO_KM:
        raise DadosInvalidos(
            f"A distância precisa ficar entre {config.RAIO_MINIMO_KM} e {config.RAIO_MAXIMO_KM} km."
        )
    if material and material not in MATERIAIS:
        raise DadosInvalidos(f"O material {material} não existe. Veja a lista em /api/materiais.")

    if cep:
        origem = localizacao.origem_por_cep(localizacao.limpar_cep(cep))
    else:
        origem = localizacao.origem_por_municipio(municipio)

    encontrados, avisos = pontos.buscar(origem["latitude"], origem["longitude"], raio_km, material)
    return {
        "origem": origem,
        "raio_km": raio_km,
        "material": material or None,
        "total": len(encontrados),
        "pontos": encontrados,
        "avisos": avisos,
    }


@app.get("/api/municipios", response_model=list[Municipio], summary="Municípios de Goiás e suas regiões")
def listar_municipios() -> list[dict]:
    return localizacao.municipios()


@app.get("/api/materiais", response_model=list[Material], summary="Materiais aceitos no filtro da busca")
def listar_materiais() -> list[dict]:
    return para_saida(list(MATERIAIS))


@app.get("/api/pontos", response_model=RespostaPontos, summary="Pontos de coleta perto de um CEP ou município")
def buscar_pontos(
    cep: str | None = Query(None, description="CEP de Goiás, com ou sem traço.", examples=["74230-010"]),
    municipio: str | None = Query(None, description="Código IBGE do município.", examples=["5208707"]),
    raio_km: int = Query(10, description="Distância máxima, em km."),
    material: str | None = Query(None, description="Chave de um item de /api/materiais."),
) -> dict:
    return _consultar(cep, municipio, raio_km, material)
# APS-FIM


@app.get("/api/pontos.csv", summary="Mesma busca de /api/pontos, em planilha CSV")
def exportar_pontos(
    cep: str | None = None,
    municipio: str | None = None,
    raio_km: int = 10,
    material: str | None = None,
) -> Response:
    resultado = _consultar(cep, municipio, raio_km, material)

    saida = io.StringIO()
    # O Excel em portugues separa colunas por ponto e virgula.
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(["Nome", "Tipo", "Endereço", "Materiais", "Distância (km)", "Latitude", "Longitude", "Fonte"])
    for ponto in resultado["pontos"]:
        materiais = ", ".join(item["rotulo"] for item in ponto["materiais"]) or "Não informado"
        escritor.writerow(
            [
                _celula_segura(ponto["nome"]),
                ponto["tipo"],
                _celula_segura(ponto["endereco"]),
                materiais,
                str(ponto["distancia_km"]).replace(".", ","),
                ponto["latitude"],
                ponto["longitude"],
                ponto["fonte"],
            ]
        )
    # O BOM faz o Excel reconhecer os acentos.
    return Response(
        content="﻿" + saida.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="pontos-de-coleta.csv"'},
    )


def _celula_segura(texto: str) -> str:
    """Os nomes vem de um mapa aberto: impede que o Excel execute um deles como formula."""
    return f"'{texto}" if texto[:1] in ("=", "+", "-", "@") else texto


# Fica por ultimo para nao encobrir as rotas /api e /docs.
app.mount("/", StaticFiles(directory=config.PASTA_WEB, html=True), name="web")
