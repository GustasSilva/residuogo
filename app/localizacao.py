"""De onde a pessoa esta buscando: municipios (IBGE), CEP (ViaCEP) e coordenadas (Nominatim)."""

import json
import re
import time
import unicodedata
from functools import lru_cache

from app import config
from app.erros import DadosInvalidos, NaoEncontrado, ServicoIndisponivel
from app.externo import FalhaExterna, com_cache, obter_json

# --- Limite de Goias ---


@lru_cache(maxsize=1)
def limite_de_goias() -> list[list[float]]:
    """Contorno oficial do estado, baixado da API de malhas do IBGE."""
    malha = json.loads(config.ARQUIVO_LIMITE_GOIAS.read_text("utf-8"))
    return malha["features"][0]["geometry"]["coordinates"][0]


def dentro_de_goias(latitude: float, longitude: float) -> bool:
    """Traca uma linha a partir do ponto e conta os cruzamentos com o contorno: impar e dentro."""
    contorno = limite_de_goias()
    dentro = False
    for (lon1, lat1), (lon2, lat2) in zip(contorno, contorno[1:]):
        if (lat1 > latitude) != (lat2 > latitude):
            cruzamento = lon1 + (latitude - lat1) * (lon2 - lon1) / (lat2 - lat1)
            if longitude < cruzamento:
                dentro = not dentro
    return dentro


# --- Municipios ---


def sem_acentos(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).casefold()


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


# --- Coordenadas ---


def _coordenadas_nominatim(**busca: str) -> list[float] | None:
    """Coordenadas da busca, ou None se o Nominatim nao achou nada dentro de Goias."""

    def consultar() -> list[float]:
        time.sleep(1)  # o Nominatim pede no maximo uma chamada por segundo
        # Ele recusa `q` junto com campos estruturados como `state`.
        filtros = busca if "q" in busca else {**busca, "state": "Goiás"}
        params = {**filtros, "format": "jsonv2", "limit": 1, "countrycodes": "br"}
        resultado = obter_json(config.URL_NOMINATIM, "Nominatim", params)
        return [float(resultado[0]["lat"]), float(resultado[0]["lon"])] if resultado else []

    chave = "nominatim:" + "|".join(f"{k}={v}" for k, v in sorted(busca.items()))
    coordenadas = com_cache(chave, config.VALIDADE_ENDERECOS, "Nominatim", consultar)
    return coordenadas if coordenadas and dentro_de_goias(*coordenadas) else None


def _lugares_nominatim(texto: str) -> list[list]:
    """Lugares encontrados para um texto livre, como [latitude, longitude, nome]."""

    def consultar() -> list[list]:
        time.sleep(1)  # o Nominatim pede no maximo uma chamada por segundo
        params = {
            "q": texto,
            "viewbox": config.CAIXA_DE_GOIAS,
            "bounded": 1,
            "format": "jsonv2",
            "limit": 5,
            "countrycodes": "br",
        }
        resultado = obter_json(config.URL_NOMINATIM, "Nominatim", params)
        return [[float(lugar["lat"]), float(lugar["lon"]), lugar["display_name"]] for lugar in resultado]

    return com_cache(f"lugar:{sem_acentos(texto)}", config.VALIDADE_ENDERECOS, "Nominatim", consultar)


def _centro_do_municipio(codigo: str) -> list[float]:
    def consultar() -> list[float]:
        bruto = obter_json(config.URL_METADADOS_MUNICIPIO.format(codigo=codigo), "IBGE")
        try:
            centro = bruto[0]["centroide"]
            return [centro["latitude"], centro["longitude"]]
        except (KeyError, IndexError, TypeError) as erro:
            raise FalhaExterna("IBGE: metadados em formato inesperado") from erro

    return com_cache(f"centro-ibge:{codigo}", config.VALIDADE_ENDERECOS, "IBGE", consultar)


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
        return _origem(f"{cidade} - GO", [("município", {"city": cidade})], municipio["codigo"])

    return _origem_por_lugar(texto)


def _origem_por_cep(cep: str) -> dict:
    """Tenta a rua, depois o bairro, depois a cidade."""
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
    return _origem(descricao, tentativas, endereco["ibge"])


def _origem_por_lugar(texto: str) -> dict:
    for latitude, longitude, nome in _lugares_nominatim(texto):
        if dentro_de_goias(latitude, longitude):
            # O nome vem como "Setor Bueno, Goiânia, Goiás, Região Centro-Oeste, 74215-315, Brasil".
            descricao = nome.split(", Goiás, Região")[0] + " - GO"
            return {"descricao": descricao, "latitude": latitude, "longitude": longitude, "precisao": "lugar"}
    raise NaoEncontrado(f'Não encontramos "{texto}" em Goiás. Tente incluir a cidade, como "Setor Bueno, Goiânia".')


def _origem(descricao: str, tentativas: list[tuple[str, dict]], codigo_ibge: str) -> dict:
    """Usa a primeira coordenada encontrada; sem nenhuma, o centro do municipio pelo IBGE."""
    coordenadas, precisao = None, "município"
    for precisao_da_busca, busca in tentativas:
        try:
            coordenadas = _coordenadas_nominatim(**busca)
        except ServicoIndisponivel:
            break
        if coordenadas:
            precisao = precisao_da_busca
            break

    latitude, longitude = coordenadas or _centro_do_municipio(codigo_ibge)
    return {"descricao": descricao, "latitude": latitude, "longitude": longitude, "precisao": precisao}
# APS-FIM


def origem_por_coordenadas(latitude: float | None, longitude: float | None) -> dict:
    if latitude is None or longitude is None:
        raise DadosInvalidos("Informe a latitude e a longitude do ponto.")
    if not dentro_de_goias(latitude, longitude):
        raise DadosInvalidos("Esse local fica fora de Goiás. Escolha um ponto dentro do estado.")
    return {"descricao": "Ponto escolhido no mapa", "latitude": latitude, "longitude": longitude, "precisao": "mapa"}
