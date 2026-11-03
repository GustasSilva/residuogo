"""Enderecos das APIs externas, caminhos, prazos e tempos limite."""

from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA_WEB = RAIZ / "web"
ARQUIVO_CACHE = RAIZ / "cache.db"

# O Nominatim exige um User-Agent que identifique a aplicacao.
USER_AGENT = "ResiduoGO/2.0 (trabalho academico UNIP)"

URL_MUNICIPIOS = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/GO/municipios"
URL_CONTORNO_GOIAS = "https://servicodados.ibge.gov.br/api/v3/malhas/estados/52"
URL_VIACEP = "https://viacep.com.br/ws/{cep}/json/"
URL_NOMINATIM = "https://nominatim.openstreetmap.org"

# Retangulo em volta de Goias (oeste, norte, leste, sul), no formato do Nominatim.
CAIXA_DE_GOIAS = "-53.25,-12.4,-45.9,-19.5"

TEMPO_LIMITE_HTTP = 10  # segundos

DIA = 24 * 60 * 60
VALIDADE_ENDERECOS = 30 * DIA  # municipios, CEP e coordenadas quase nao mudam
VALIDADE_PONTOS = 1 * DIA

RAIO_MINIMO_KM = 1
RAIO_MAXIMO_KM = 50
