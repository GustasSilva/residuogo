"""Enderecos das APIs externas, prazos de cache e tempos limite."""

from pathlib import Path

PASTA_APP = Path(__file__).resolve().parent
PASTA_WEB = PASTA_APP / "web"
PASTA_DADOS = PASTA_APP / "dados"

ARQUIVO_CACHE = PASTA_APP.parent / "cache.db"
ARQUIVO_ECOPONTOS = PASTA_DADOS / "ecopontos_goiania.json"
ARQUIVO_COPIA_OSM = PASTA_DADOS / "osm_goias.json"

# O Nominatim exige um User-Agent que identifique a aplicacao.
USER_AGENT = "ResiduoGO/2.0 (trabalho academico UNIP)"

URL_MUNICIPIOS = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/GO/municipios"
URL_METADADOS_MUNICIPIO = "https://servicodados.ibge.gov.br/api/v3/malhas/municipios/{codigo}/metadados"
URL_VIACEP = "https://viacep.com.br/ws/{cep}/json/"
URL_NOMINATIM = "https://nominatim.openstreetmap.org/search"

# Instancias publicas da mesma API. Todas ficam sobrecarregadas com frequencia.
SERVIDORES_OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

TEMPO_LIMITE_HTTP = 6  # segundos, para IBGE, ViaCEP e Nominatim
TEMPO_LIMITE_OVERPASS = 25  # segundos que a busca espera pelo Overpass
ESPERA_APOS_FALHA_OVERPASS = 120  # segundos sem tentar de novo depois de uma falha

DIA = 24 * 60 * 60
VALIDADE_MUNICIPIOS = 30 * DIA
VALIDADE_CEP = 30 * DIA
VALIDADE_COORDENADAS = 30 * DIA
VALIDADE_PONTOS = 1 * DIA

RAIO_MINIMO_KM = 1
RAIO_MAXIMO_KM = 50

# Retangulo em volta de Goias, para recusar uma coordenada obviamente errada.
LIMITES_GOIAS = {"lat_min": -19.6, "lat_max": -12.3, "lon_min": -53.3, "lon_max": -45.8}
