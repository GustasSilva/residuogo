"""API do ViaCEP: endereço a partir do CEP."""

from app import config
from app.apis.cache import com_cache, obter_json


def endereco(cep: str) -> dict | None:
    """Rua, bairro, cidade e UF de um CEP (só os 8 dígitos), ou None se ele não existe."""
    dados = com_cache(
        f"cep:{cep}",
        config.VALIDADE_ENDERECOS,
        "ViaCEP",
        lambda: obter_json(config.URL_VIACEP.format(cep=cep), "ViaCEP"),
    )
    # Para um CEP que não existe, o ViaCEP responde 200 com {"erro": "true"}.
    if not isinstance(dados, dict) or dados.get("erro"):
        return None
    return dados
