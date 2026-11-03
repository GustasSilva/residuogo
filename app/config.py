"""Enderecos das APIs externas, caminhos dos arquivos, prazos e tempos limite."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_WEB = RAIZ / "web"
ARQUIVO_CACHE = RAIZ / "cache.db"
ARQUIVO_ECOPONTOS = RAIZ / "dados" / "ecopontos_goiania.json"
ARQUIVO_COPIA_OSM = RAIZ / "dados" / "osm_goias.json"
ARQUIVO_LIMITE_GOIAS = RAIZ / "dados" / "limite_goias.json"

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
VALIDADE_ENDERECOS = 30 * DIA  # municipios, CEP e coordenadas quase nao mudam
VALIDADE_PONTOS = 1 * DIA

RAIO_MINIMO_KM = 1
RAIO_MAXIMO_KM = 50
