"""Exporta os contratos dos dois web services para a pasta `docs/`.

Gera dois arquivos que sao insumos diretos do trabalho escrito:

* `openapi.json`   - contrato do servico REST, como o Swagger o publica;
* `manifesto.wsdl` - contrato do servico SOAP.

Roda sem servidor no ar: os dois contratos sao derivados do proprio codigo.

Uso, a partir da pasta `backend`:

    python -m scripts.exportar_docs
"""

import json
from pathlib import Path

from app.main import app
from app.soap.wsdl import gerar_wsdl

# A pasta docs/ fica na raiz do repositorio, um nivel acima de backend/.
PASTA_DOCS = Path(__file__).resolve().parents[2] / "docs"

# Endereco usado no WSDL exportado. E o endereco de desenvolvimento; o WSDL
# servido pela aplicacao usa sempre a URL real da requisicao.
URL_SOAP = "http://127.0.0.1:8000/soap/manifesto"


def exportar() -> None:
    PASTA_DOCS.mkdir(exist_ok=True)

    destino_openapi = PASTA_DOCS / "openapi.json"
    destino_openapi.write_text(
        json.dumps(app.openapi(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    destino_wsdl = PASTA_DOCS / "manifesto.wsdl"
    destino_wsdl.write_bytes(gerar_wsdl(URL_SOAP))

    for arquivo in (destino_openapi, destino_wsdl):
        tamanho = arquivo.stat().st_size / 1024
        print(f"{arquivo.relative_to(PASTA_DOCS.parent)} ({tamanho:.1f} KB)")


if __name__ == "__main__":
    exportar()
