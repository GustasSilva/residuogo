"""Baixa os pontos de coleta de Goias do Overpass e salva a copia de reserva.

A copia e usada quando o Overpass nao responde durante uma busca. O estado e
dividido em quadros porque os servidores publicos costumam recusar ou derrubar
consultas grandes. Um quadro baixado fica guardado, entao rodar de novo continua
de onde parou.

Uso, a partir da pasta `backend`:

    python -m scripts.atualizar_copia_osm
"""

import json
import sys
import time
from datetime import date

from app import config
from app.externo import FalhaExterna, enviar_consulta

TAMANHO_DO_QUADRO = 2.0  # graus
RODADAS = 12
ESPERA_ENTRE_RODADAS = 45  # segundos
ETIQUETAS_MANTIDAS = ("amenity", "name", "operator", "recycling_type", "access", "phone", "contact:phone", "opening_hours")
PROGRESSO = config.PASTA_APP.parent / "copia_osm_em_andamento.json"

CONSULTA = (
    '[out:json][timeout:60];('
    'nwr["amenity"="recycling"]({caixa});'
    'nwr["amenity"="waste_transfer_station"]({caixa});'
    ');out tags center;'
)


def quadros() -> list[str]:
    limites = config.LIMITES_GOIAS
    caixas = []
    lat = limites["lat_min"]
    while lat < limites["lat_max"]:
        lon = limites["lon_min"]
        while lon < limites["lon_max"]:
            lat_fim = min(lat + TAMANHO_DO_QUADRO, limites["lat_max"])
            lon_fim = min(lon + TAMANHO_DO_QUADRO, limites["lon_max"])
            caixas.append(f"{lat:.2f},{lon:.2f},{lat_fim:.2f},{lon_fim:.2f}")
            lon += TAMANHO_DO_QUADRO
        lat += TAMANHO_DO_QUADRO
    return caixas


def reduzir(elemento: dict) -> dict:
    """Guarda so o que a busca usa, para o arquivo ficar pequeno."""
    centro = elemento.get("center", {})
    etiquetas = {
        chave: valor
        for chave, valor in elemento.get("tags", {}).items()
        if chave in ETIQUETAS_MANTIDAS or chave.startswith(("recycling:", "addr:"))
    }
    return {
        "id": f'{elemento["type"]}/{elemento["id"]}',
        "lat": elemento.get("lat", centro.get("lat")),
        "lon": elemento.get("lon", centro.get("lon")),
        "tags": etiquetas,
    }


def main() -> int:
    baixados: dict[str, list] = json.loads(PROGRESSO.read_text("utf-8")) if PROGRESSO.exists() else {}
    caixas = quadros()

    for rodada in range(1, RODADAS + 1):
        faltando = [caixa for caixa in caixas if caixa not in baixados]
        if not faltando:
            break
        print(f"Rodada {rodada}: faltam {len(faltando)} de {len(caixas)} quadros", flush=True)
        for indice, caixa in enumerate(faltando):
            servidor = config.SERVIDORES_OVERPASS[(rodada + indice) % len(config.SERVIDORES_OVERPASS)]
            try:
                resposta = enviar_consulta(servidor, "Overpass", {"data": CONSULTA.format(caixa=caixa)}, 75)
            except FalhaExterna as falha:
                print(f"  {caixa} falhou em {servidor.split('/')[2]}: {falha}", flush=True)
                continue
            baixados[caixa] = [reduzir(elemento) for elemento in resposta["elements"]]
            PROGRESSO.write_text(json.dumps(baixados, ensure_ascii=False), "utf-8")
            print(f"  {caixa}: {len(baixados[caixa])} pontos", flush=True)
        if len(baixados) < len(caixas):
            time.sleep(ESPERA_ENTRE_RODADAS)

    faltando = [caixa for caixa in caixas if caixa not in baixados]
    if faltando:
        print(f"Incompleto, a copia nao foi trocada. Faltam: {faltando}", flush=True)
        return 1

    unicos = {elemento["id"]: elemento for lista in baixados.values() for elemento in lista}
    config.ARQUIVO_COPIA_OSM.write_text(
        json.dumps({"gerado_em": date.today().isoformat(), "elementos": list(unicos.values())}, ensure_ascii=False, indent=0),
        "utf-8",
    )
    PROGRESSO.unlink()
    print(f"Copia salva com {len(unicos)} pontos em {config.ARQUIVO_COPIA_OSM}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
