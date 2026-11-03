"""Reune os trechos de codigo marcados no projeto em um unico documento.

O relatorio de codigo da APS tem limite de 10 paginas em Arial 12 com
espacamento 1,5 - cerca de 380 linhas. O projeto inteiro tem muito mais que
isso, entao os trechos que vao para o papel sao escolhidos e marcados no
proprio codigo-fonte:

    # APS-TRECHO 3: Erros no formato RFC 7807
    ... o codigo que vai para o relatorio ...
    # APS-FIM

Este script procura essas marcas em todo o repositorio, monta
`docs/TRECHOS_DE_CODIGO.md` na ordem dos numeros e informa quantas linhas o
conjunto ocupa. Assim o relatorio e sempre montado a partir do codigo que
roda - um trecho copiado a mao envelheceria na primeira correcao.

Trechos com o mesmo numero sao agrupados sob o mesmo titulo, o que permite
reunir partes de arquivos diferentes.

Uso, a partir da pasta `backend`:

    python -m scripts.exportar_trechos
"""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DESTINO = RAIZ / "docs" / "TRECHOS_DE_CODIGO.md"

# Pastas que nao sao codigo do projeto.
IGNORADAS = {".git", ".venv", "__pycache__", ".pytest_cache"}

# Extensoes procuradas e a linguagem usada na marcacao do bloco de codigo.
LINGUAGENS = {".py": "python", ".js": "js"}

# Aceita `#` (Python) e `//` (JavaScript) como inicio do comentario.
INICIO = re.compile(r"^\s*(?:#|//)\s*APS-TRECHO\s+(\d+)\s*:\s*(.+?)\s*$")
FIM = re.compile(r"^\s*(?:#|//)\s*APS-FIM\s*$")

# Estimativa de linhas que cabem no limite de 10 paginas do relatorio.
ORCAMENTO_DE_LINHAS = 380


@dataclass
class Bloco:
    arquivo: str
    primeira_linha: int
    linhas: list[str]
    linguagem: str


@dataclass
class Trecho:
    numero: int
    titulo: str
    blocos: list[Bloco] = field(default_factory=list)

    @property
    def total_de_linhas(self) -> int:
        return sum(len(bloco.linhas) for bloco in self.blocos)


def arquivos_do_projeto():
    """Todos os arquivos de codigo do repositorio, em ordem previsivel.

    Este proprio arquivo fica de fora: a documentacao dele mostra as marcas
    como exemplo, e sem a excecao o script se incluiria no relatorio.
    """
    eu_mesmo = Path(__file__).resolve()

    for caminho in sorted(RAIZ.rglob("*")):
        if caminho.suffix not in LINGUAGENS or not caminho.is_file():
            continue
        if caminho.resolve() == eu_mesmo:
            continue
        if IGNORADAS.intersection(caminho.relative_to(RAIZ).parts):
            continue
        yield caminho


def coletar() -> list[Trecho]:
    """Le as marcas de todos os arquivos e devolve os trechos ordenados."""
    trechos: dict[int, Trecho] = {}

    for caminho in arquivos_do_projeto():
        relativo = caminho.relative_to(RAIZ).as_posix()
        aberto: tuple[int, str, int, list[str]] | None = None

        for numero_da_linha, linha in enumerate(
            caminho.read_text(encoding="utf-8").splitlines(), start=1
        ):
            marca = INICIO.match(linha)

            if marca is not None:
                if aberto is not None:
                    erro(f"{relativo}:{numero_da_linha}: APS-TRECHO dentro de outro.")
                aberto = (int(marca.group(1)), marca.group(2), numero_da_linha + 1, [])
                continue

            if FIM.match(linha):
                if aberto is None:
                    erro(f"{relativo}:{numero_da_linha}: APS-FIM sem APS-TRECHO.")
                numero, titulo, primeira, acumuladas = aberto
                trecho = trechos.setdefault(numero, Trecho(numero, titulo))
                trecho.blocos.append(
                    Bloco(relativo, primeira, acumuladas, LINGUAGENS[caminho.suffix])
                )
                aberto = None
                continue

            if aberto is not None:
                aberto[3].append(linha)

        if aberto is not None:
            erro(f"{relativo}: APS-TRECHO '{aberto[1]}' nao foi fechado com APS-FIM.")

    return [trechos[numero] for numero in sorted(trechos)]


def erro(mensagem: str) -> None:
    """Interrompe a exportacao: marca malformada geraria um documento errado."""
    print(f"ERRO: {mensagem}", file=sys.stderr)
    raise SystemExit(1)


def montar(trechos: list[Trecho]) -> str:
    total = sum(trecho.total_de_linhas for trecho in trechos)

    partes = [
        "# Trechos de código para o relatório impresso",
        "",
        "Gerado por `scripts/exportar_trechos.py` a partir das marcas `APS-TRECHO`",
        "deixadas no código-fonte. Não editar à mão: a próxima execução sobrescreve.",
        "",
        f"**{len(trechos)} trechos, {total} linhas de código.** O relatório admite "
        f"cerca de {ORCAMENTO_DE_LINHAS} linhas (10 páginas em Arial 12, "
        "espaçamento 1,5), então ainda cabem comentários de abertura e as "
        "legendas de cada trecho.",
        "",
        "| # | Trecho | Onde | Linhas |",
        "|---|---|---|---|",
    ]

    for trecho in trechos:
        # `dict.fromkeys` remove repetidos preservando a ordem: um trecho com
        # dois blocos do mesmo arquivo cita o arquivo uma vez só.
        arquivos = "<br>".join(
            f"`{nome}`" for nome in dict.fromkeys(bloco.arquivo for bloco in trecho.blocos)
        )
        partes.append(
            f"| {trecho.numero} | {trecho.titulo} | {arquivos} | {trecho.total_de_linhas} |"
        )

    for trecho in trechos:
        partes += ["", "---", "", f"## {trecho.numero}. {trecho.titulo}"]

        for bloco in trecho.blocos:
            ultima = bloco.primeira_linha + len(bloco.linhas) - 1
            partes += [
                "",
                f"`{bloco.arquivo}`, linhas {bloco.primeira_linha} a {ultima}",
                "",
                f"```{bloco.linguagem}",
                *bloco.linhas,
                "```",
            ]

    partes.append("")
    return "\n".join(partes)


def exportar() -> None:
    trechos = coletar()

    if not trechos:
        erro("Nenhuma marca APS-TRECHO encontrada no projeto.")

    DESTINO.write_text(montar(trechos), encoding="utf-8")

    total = sum(trecho.total_de_linhas for trecho in trechos)
    for trecho in trechos:
        print(f"  {trecho.numero}. {trecho.titulo} — {trecho.total_de_linhas} linhas")

    print(f"\n{DESTINO.relative_to(RAIZ)}: {len(trechos)} trechos, {total} linhas.")

    if total > ORCAMENTO_DE_LINHAS:
        print(
            f"ATENÇÃO: {total - ORCAMENTO_DE_LINHAS} linhas acima do orçamento "
            f"de {ORCAMENTO_DE_LINHAS}.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    exportar()
