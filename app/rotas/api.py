"""As rotas do web service: o que a pagina, ou qualquer outro cliente, pode pedir."""

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import JSONResponse

from app import config
from app.apis import ibge
from app.erros import DadosInvalidos
from app.rotas import exportacao
from app.rotas.schemas import Material, Municipio, RespostaPontos
from app.servicos import localizacao, pontos
from app.servicos.materiais import MATERIAIS, para_saida

router = APIRouter(prefix="/api")


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


@router.get("/pontos", response_model=RespostaPontos, summary="Pontos de coleta perto de um local ou ponto no mapa")
def buscar_pontos(resultado: dict = Depends(_consultar)) -> dict:
    return resultado


@router.get(
    "/pontos.csv",
    summary="Mesma busca de /api/pontos, em planilha CSV",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "Planilha separada por ponto e vírgula"}},
)
def exportar_pontos(resultado: dict = Depends(_consultar)) -> Response:
    return Response(
        content=exportacao.planilha(resultado["pontos"]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="pontos-de-coleta.csv"'},
    )


@router.get(
    "/pontos.pdf",
    summary="Mesma busca de /api/pontos, em relatório PDF",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "Relatório da busca"}},
)
def relatorio_pontos(resultado: dict = Depends(_consultar)) -> Response:
    return Response(
        content=exportacao.relatorio_pdf(resultado),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="pontos-de-coleta.pdf"'},
    )


@router.get("/municipios", response_model=list[Municipio], summary="Municípios de Goiás e suas regiões")
def listar_municipios() -> list[dict]:
    return localizacao.municipios()


@router.get("/materiais", response_model=list[Material], summary="Materiais aceitos no filtro da busca")
def listar_materiais() -> list[dict]:
    return para_saida(list(MATERIAIS))


@router.get("/goias", summary="Contorno oficial de Goiás (IBGE), em GeoJSON")
def contorno_de_goias() -> JSONResponse:
    # Nao tem regra no meio: o contorno vai do IBGE direto para a pagina.
    return JSONResponse(ibge.contorno_de_goias(), media_type="application/geo+json")
# APS-FIM
