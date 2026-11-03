"""Junta em docs/TRECHOS_DE_CODIGO.md os trechos marcados no codigo para o relatorio.

Assim o relatorio sai sempre do codigo que roda. As marcas sao comentarios
`APS-TRECHO <numero>: <titulo>` e `APS-FIM`.

    python -m scripts.exportar_trechos
"""

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "docs" / "TRECHOS_DE_CODIGO.md"
INICIO = re.compile(r"\s*(?:#|//) APS-TRECHO (\d+): (.+)")
FIM = re.compile(r"\s*(?:#|//) APS-FIM")
LIMITE_DE_LINHAS = 380  # cerca de 10 paginas em Arial 12, espacamento 1,5


def coletar() -> dict[int, tuple[str, Path, list[str]]]:
    trechos = {}
    for arquivo in [*sorted((RAIZ / "app").glob("*.py")), RAIZ / "web" / "app.js"]:
        aberto = None
        for linha in arquivo.read_text("utf-8").splitlines():
            if marca := INICIO.fullmatch(linha):
                aberto = []
                trechos[int(marca[1])] = (marca[2], arquivo, aberto)
            elif FIM.fullmatch(linha):
                aberto = None
            elif aberto is not None:
                aberto.append(linha)
    return trechos


def main() -> None:
    trechos = coletar()
    total = sum(len(linhas) for _, _, linhas in trechos.values())

    partes = [
        "# Trechos de código para o relatório",
        "",
        "Gerado por `scripts/exportar_trechos.py`. Não editar à mão.",
        "",
        f"{len(trechos)} trechos, {total} linhas. O limite é de cerca de {LIMITE_DE_LINHAS} linhas.",
    ]
    for numero, (titulo, arquivo, linhas) in sorted(trechos.items()):
        linguagem = "js" if arquivo.suffix == ".js" else "python"
        partes += ["", f"## {numero}. {titulo}", "", f"`{arquivo.relative_to(RAIZ).as_posix()}`", "", f"```{linguagem}", *linhas, "```"]

    DESTINO.write_text("\n".join(partes) + "\n", "utf-8")
    print(f"{DESTINO.name}: {len(trechos)} trechos, {total} linhas (limite: {LIMITE_DE_LINHAS}).")


if __name__ == "__main__":
    main()
