"""Descobre onde a pessoa esta: municipios (IBGE), CEP (ViaCEP) e coordenadas (Nominatim)."""

import re
import threading
import time
import unicodedata

from app import config
from app.errors import DadosInvalidos, NaoEncontrado, ServicoIndisponivel
from app.externo import FalhaExterna, com_cache, obter_json

_trava_nominatim = threading.Lock()
_ultima_chamada_nominatim = 0.0


def municipios() -> list[dict[str, str]]:
    """Municipios de Goias com a regiao intermediaria do IBGE, em ordem alfabetica."""
    return com_cache("municipios-go", config.VALIDADE_MUNICIPIOS, "IBGE", _consultar_municipios)


def _consultar_municipios() -> list[dict[str, str]]:
    bruto = obter_json(config.URL_MUNICIPIOS, "IBGE")
    try:
        lista = [
            {
                "codigo": str(item["id"]),
                "nome": item["nome"],
                "regiao": item["regiao-imediata"]["regiao-intermediaria"]["nome"],
            }
            for item in bruto
        ]
    except (KeyError, TypeError) as erro:
        raise FalhaExterna("IBGE: resposta em formato inesperado") from erro
    if not lista:
        raise FalhaExterna("IBGE: lista de municipios vazia")
    return sorted(lista, key=lambda municipio: _sem_acentos(municipio["nome"]))


def _sem_acentos(texto: str) -> str:
    """Sem isso, "Água Limpa" cairia no fim da lista em ordem alfabetica."""
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).casefold()


def _nome_do_municipio(codigo: str) -> str:
    for municipio in municipios():
        if municipio["codigo"] == codigo:
            return municipio["nome"]
    raise NaoEncontrado(f"O município {codigo} não existe em Goiás.")


def limpar_cep(cep: str) -> str:
    digitos = re.sub(r"\D", "", cep)
    if len(digitos) != 8:
        raise DadosInvalidos("O CEP precisa ter 8 dígitos.")
    return digitos


def endereco_do_cep(cep: str) -> dict:
    endereco = com_cache(
        f"cep:{cep}",
        config.VALIDADE_CEP,
        "ViaCEP",
        lambda: obter_json(config.URL_VIACEP.format(cep=cep), "ViaCEP"),
    )
    if not isinstance(endereco, dict) or endereco.get("erro"):
        raise NaoEncontrado(f"O CEP {cep[:5]}-{cep[5:]} não foi encontrado.")
    if endereco.get("uf") != "GO":
        raise DadosInvalidos(f"O CEP {cep[:5]}-{cep[5:]} não é de Goiás.")
    return endereco


def _dentro_de_goias(latitude: float, longitude: float) -> bool:
    limites = config.LIMITES_GOIAS
    return (
        limites["lat_min"] <= latitude <= limites["lat_max"]
        and limites["lon_min"] <= longitude <= limites["lon_max"]
    )


def _chamar_nominatim(params: dict) -> list:
    """Respeita o limite de uma chamada por segundo pedido pelo Nominatim."""
    global _ultima_chamada_nominatim
    with _trava_nominatim:
        espera = _ultima_chamada_nominatim + 1.1 - time.monotonic()
        if espera > 0:
            time.sleep(espera)
        _ultima_chamada_nominatim = time.monotonic()
    return obter_json(
        config.URL_NOMINATIM,
        "Nominatim",
        {**params, "format": "jsonv2", "limit": 1, "countrycodes": "br"},
    )


def _geocodificar(**params: str) -> tuple[float, float] | None:
    """Coordenadas da busca, ou None se o Nominatim nao encontrou nada."""
    chave = "nominatim:" + "|".join(f"{k}={v}" for k, v in sorted(params.items()))

    def consultar() -> list:
        # O Nominatim recusa `q` junto com campos estruturados como `state`.
        resultado = _chamar_nominatim(params if "q" in params else {**params, "state": "Goiás"})
        return [float(resultado[0]["lat"]), float(resultado[0]["lon"])] if resultado else []

    coordenadas = com_cache(chave, config.VALIDADE_COORDENADAS, "Nominatim", consultar)
    if coordenadas and _dentro_de_goias(*coordenadas):
        return coordenadas[0], coordenadas[1]
    return None


def _centro_ibge(codigo: str) -> tuple[float, float]:
    def consultar() -> list:
        bruto = obter_json(config.URL_METADADOS_MUNICIPIO.format(codigo=codigo), "IBGE")
        try:
            centro = bruto[0]["centroide"]
            return [centro["latitude"], centro["longitude"]]
        except (KeyError, IndexError, TypeError) as erro:
            raise FalhaExterna("IBGE: metadados em formato inesperado") from erro

    coordenadas = com_cache(f"centro-ibge:{codigo}", config.VALIDADE_COORDENADAS, "IBGE", consultar)
    return coordenadas[0], coordenadas[1]


# APS-TRECHO 2: Do CEP ate as coordenadas, da busca mais precisa para a menos precisa
def origem_por_cep(cep: str) -> dict:
    endereco = endereco_do_cep(cep)
    cidade = endereco["localidade"]
    rua = endereco.get("logradouro", "")
    bairro = endereco.get("bairro", "")

    tentativas = []
    if rua:
        tentativas.append(("endereço", {"street": rua, "city": cidade}))
    if bairro:
        tentativas.append(("bairro", {"q": f"{bairro}, {cidade}, Goiás"}))
    tentativas.append(("município", {"city": cidade}))

    for precisao, params in tentativas:
        try:
            coordenadas = _geocodificar(**params)
        except ServicoIndisponivel:
            # Sem Nominatim, o centro do municipio informado pelo IBGE ainda serve.
            break
        if coordenadas:
            return _origem(_descrever(rua, bairro, cidade), coordenadas, precisao)

    return _origem(_descrever(rua, bairro, cidade), _centro_ibge(endereco["ibge"]), "município")
# APS-FIM


def origem_por_municipio(codigo: str) -> dict:
    if not re.fullmatch(r"52\d{5}", codigo):
        raise DadosInvalidos("O código do município precisa ser um código IBGE de Goiás, com 7 dígitos.")
    cidade = _nome_do_municipio(codigo)
    try:
        coordenadas = _geocodificar(city=cidade)
    except ServicoIndisponivel:
        coordenadas = None
    return _origem(_descrever("", "", cidade), coordenadas or _centro_ibge(codigo), "município")


def _descrever(rua: str, bairro: str, cidade: str) -> str:
    return ", ".join(parte for parte in (rua, bairro, f"{cidade} - GO") if parte)


def _origem(descricao: str, coordenadas: tuple[float, float], precisao: str) -> dict:
    return {
        "descricao": descricao,
        "latitude": coordenadas[0],
        "longitude": coordenadas[1],
        "precisao": precisao,
    }
