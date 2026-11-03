"""De onde a pessoa esta buscando: CEP, municipio, texto livre ou clique no mapa."""

import re
import unicodedata

from app import config
from app.apis import ibge, nominatim, viacep
from app.erros import DadosInvalidos, NaoEncontrado, ServicoIndisponivel
from app.servicos.geo import no_retangulo


def sem_acentos(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).casefold()


# --- Municipios ---


def municipios() -> list[dict[str, str]]:
    """Municipios de Goias em ordem alfabetica, sem levar os acentos em conta."""
    return sorted(ibge.municipios(), key=lambda municipio: sem_acentos(municipio["nome"]))


def _municipio_pelo_nome(nome: str) -> dict | None:
    try:
        lista = ibge.municipios()
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
    endereco = viacep.endereco(cep)
    cep_formatado = f"{cep[:5]}-{cep[5:]}"
    if endereco is None:
        raise NaoEncontrado(f"O CEP {cep_formatado} não foi encontrado.")
    if endereco.get("uf") != "GO":
        raise DadosInvalidos(f"O CEP {cep_formatado} não é de Goiás.")
    return endereco


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
    for lugar in nominatim.lugares(texto):
        if nominatim.em_goias(lugar):
            # O nome vem como "Setor Bueno, Goiânia, Goiás, Região Centro-Oeste, 74215-315, Brasil".
            descricao = lugar["display_name"].split(", Goiás, Região")[0] + " - GO"
            latitude, longitude = float(lugar["lat"]), float(lugar["lon"])
            return {"descricao": descricao, "latitude": latitude, "longitude": longitude, "precisao": "lugar"}
    raise NaoEncontrado(f'Não encontramos "{texto}" em Goiás. Tente incluir a cidade, como "Setor Bueno, Goiânia".')


def _origem(descricao: str, tentativas: list[tuple[str, dict]]) -> dict:
    """Usa a primeira tentativa que o Nominatim encontrar em Goias."""
    for precisao, busca in tentativas:
        coordenadas = nominatim.coordenadas(**busca)
        if coordenadas:
            latitude, longitude = coordenadas
            return {"descricao": descricao, "latitude": latitude, "longitude": longitude, "precisao": precisao}
    raise NaoEncontrado(f"Não encontramos {descricao} no mapa.")
# APS-FIM


def origem_por_coordenadas(latitude: float | None, longitude: float | None) -> dict:
    """Ponto clicado no mapa. O retangulo descarta sem consultar a API o que esta claramente longe."""
    if latitude is None or longitude is None:
        raise DadosInvalidos("Informe a latitude e a longitude do ponto.")
    if not no_retangulo(latitude, longitude, config.CAIXA_DE_GOIAS) or not nominatim.fica_em_goias(latitude, longitude):
        raise DadosInvalidos("Esse local fica fora de Goiás. Escolha um ponto dentro do estado.")
    return {"descricao": "Ponto escolhido no mapa", "latitude": latitude, "longitude": longitude, "precisao": "mapa"}
