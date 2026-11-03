"""De onde a pessoa esta buscando: municipios (IBGE), CEP (ViaCEP) e coordenadas (Nominatim)."""

import re
import unicodedata

from app import config
from app.erros import DadosInvalidos, NaoEncontrado, ServicoIndisponivel
from app.externo import FalhaExterna, com_cache, consultar_nominatim, obter_json

# Codigo do estado que o Nominatim devolve em `ISO3166-2-lvl4`.
GOIAS = "BR-GO"


def sem_acentos(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).casefold()


def em_goias(lugar: dict) -> bool:
    """Le o estado em um resultado do Nominatim pedido com `addressdetails`."""
    return lugar.get("address", {}).get("ISO3166-2-lvl4") == GOIAS


# --- IBGE ---


def municipios() -> list[dict[str, str]]:
    """Municipios de Goias com a regiao intermediaria do IBGE, em ordem alfabetica."""
    return com_cache("municipios-go", config.VALIDADE_ENDERECOS, "IBGE", _consultar_municipios)


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
    return sorted(lista, key=lambda municipio: sem_acentos(municipio["nome"]))


def _municipio_pelo_nome(nome: str) -> dict | None:
    try:
        lista = municipios()
    except ServicoIndisponivel:
        return None  # sem o IBGE, o Nominatim ainda acha a cidade como um lugar qualquer
    procurado = sem_acentos(nome)
    return next((municipio for municipio in lista if sem_acentos(municipio["nome"]) == procurado), None)


def contorno_de_goias() -> dict:
    """Contorno oficial do estado, em GeoJSON, para desenhar no mapa."""
    return com_cache(
        "contorno-go",
        config.VALIDADE_ENDERECOS,
        "IBGE",
        lambda: obter_json(
            config.URL_CONTORNO_GOIAS,
            "IBGE",
            {"formato": "application/vnd.geo+json", "qualidade": "intermediaria"},
        ),
    )


# --- CEP ---


def _limpar_cep(cep: str) -> str:
    digitos = re.sub(r"\D", "", cep)
    if len(digitos) != 8:
        raise DadosInvalidos("O CEP precisa ter 8 dígitos.")
    return digitos


def _endereco_do_cep(cep: str) -> dict:
    endereco = com_cache(
        f"cep:{cep}",
        config.VALIDADE_ENDERECOS,
        "ViaCEP",
        lambda: obter_json(config.URL_VIACEP.format(cep=cep), "ViaCEP"),
    )
    cep_formatado = f"{cep[:5]}-{cep[5:]}"
    if not isinstance(endereco, dict) or endereco.get("erro"):
        raise NaoEncontrado(f"O CEP {cep_formatado} não foi encontrado.")
    if endereco.get("uf") != "GO":
        raise DadosInvalidos(f"O CEP {cep_formatado} não é de Goiás.")
    return endereco


# --- Coordenadas (Nominatim) ---


def _coordenadas(**busca: str) -> list[float] | None:
    """Coordenadas de uma busca por rua, bairro ou cidade, ou None se nada foi achado em Goias."""
    # O Nominatim recusa `q` junto com campos estruturados como `state`.
    filtros = busca if "q" in busca else {**busca, "state": "Goiás"}
    chave = "endereco:" + "|".join(f"{k}={v}" for k, v in sorted(busca.items()))
    lugares = com_cache(
        chave,
        config.VALIDADE_ENDERECOS,
        "Nominatim",
        lambda: consultar_nominatim("search", {**filtros, "limit": 1, "countrycodes": "br", "addressdetails": 1}),
    )
    if lugares and em_goias(lugares[0]):
        return [float(lugares[0]["lat"]), float(lugares[0]["lon"])]
    return None


def _lugares(texto: str) -> list[dict]:
    """Lugares encontrados para um texto livre, como bairro, endereco ou ponto de referencia."""
    return com_cache(
        f"texto:{sem_acentos(texto)}",
        config.VALIDADE_ENDERECOS,
        "Nominatim",
        lambda: consultar_nominatim(
            "search",
            {
                "q": texto,
                "viewbox": config.CAIXA_DE_GOIAS,
                "bounded": 1,
                "limit": 5,
                "countrycodes": "br",
                "addressdetails": 1,
            },
        ),
    )


# --- Ponto de partida da busca ---


# APS-TRECHO 3: Do texto digitado ate as coordenadas
def origem_por_texto(texto: str) -> dict:
    """Entende o que a pessoa digitou: CEP, municipio ou outro lugar (bairro, endereco...)."""
    texto = texto.strip()
    if re.fullmatch(r"[\d\s.-]+", texto):
        return _origem_por_cep(_limpar_cep(texto))

    municipio = _municipio_pelo_nome(texto)
    if municipio:
        cidade = municipio["nome"]
        return _origem(f"{cidade} - GO", [("município", {"city": cidade})])

    return _origem_por_lugar(texto)


def _origem_por_cep(cep: str) -> dict:
    """O ViaCEP nao informa coordenadas: o Nominatim tenta a rua, depois o bairro, depois a cidade."""
    endereco = _endereco_do_cep(cep)
    cidade = endereco["localidade"]
    rua = endereco.get("logradouro", "")
    bairro = endereco.get("bairro", "")

    tentativas = []
    if rua:
        tentativas.append(("endereço", {"street": rua, "city": cidade}))
    if bairro:
        tentativas.append(("bairro", {"q": f"{bairro}, {cidade}, Goiás"}))
    tentativas.append(("município", {"city": cidade}))

    descricao = ", ".join(parte for parte in (rua, bairro, f"{cidade} - GO") if parte)
    return _origem(descricao, tentativas)


def _origem_por_lugar(texto: str) -> dict:
    for lugar in _lugares(texto):
        if em_goias(lugar):
            # O nome vem como "Setor Bueno, Goiânia, Goiás, Região Centro-Oeste, 74215-315, Brasil".
            descricao = lugar["display_name"].split(", Goiás, Região")[0] + " - GO"
            latitude, longitude = float(lugar["lat"]), float(lugar["lon"])
            return {"descricao": descricao, "latitude": latitude, "longitude": longitude, "precisao": "lugar"}
    raise NaoEncontrado(f'Não encontramos "{texto}" em Goiás. Tente incluir a cidade, como "Setor Bueno, Goiânia".')


def _origem(descricao: str, tentativas: list[tuple[str, dict]]) -> dict:
    """Usa a primeira tentativa que o Nominatim encontrar em Goias."""
    for precisao, busca in tentativas:
        coordenadas = _coordenadas(**busca)
        if coordenadas:
            latitude, longitude = coordenadas
            return {"descricao": descricao, "latitude": latitude, "longitude": longitude, "precisao": precisao}
    raise NaoEncontrado(f"Não encontramos {descricao} no mapa.")
# APS-FIM


def origem_por_coordenadas(latitude: float | None, longitude: float | None) -> dict:
    """Ponto clicado no mapa. O Nominatim informa em que estado ele fica."""
    if latitude is None or longitude is None:
        raise DadosInvalidos("Informe a latitude e a longitude do ponto.")
    if not _no_retangulo_de_goias(latitude, longitude):
        raise DadosInvalidos("Esse local fica fora de Goiás. Escolha um ponto dentro do estado.")

    lugar = com_cache(
        f"estado:{latitude},{longitude}",
        config.VALIDADE_ENDERECOS,
        "Nominatim",
        lambda: consultar_nominatim("reverse", {"lat": latitude, "lon": longitude, "zoom": 5}),
    )
    if not em_goias(lugar):
        raise DadosInvalidos("Esse local fica fora de Goiás. Escolha um ponto dentro do estado.")
    return {"descricao": "Ponto escolhido no mapa", "latitude": latitude, "longitude": longitude, "precisao": "mapa"}


def _no_retangulo_de_goias(latitude: float, longitude: float) -> bool:
    """Descarta sem consultar a API o que esta claramente longe (e tambem NaN e infinito)."""
    oeste, norte, leste, sul = map(float, config.CAIXA_DE_GOIAS.split(","))
    return sul <= latitude <= norte and oeste <= longitude <= leste
