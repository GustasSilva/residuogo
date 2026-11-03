"""Baixa os pontos de coleta de Goias do Overpass e salva a copia de reserva.

O estado e dividido em quadros porque os servidores publicos costumam derrubar
consultas grandes. Um quadro baixado fica guardado, entao rodar de novo continua
de onde parou.

    python -m scripts.atualizar_copia_osm
"""

import json
import sys
import time
from datetime import date

from app import config
from app.externo import FalhaExterna, enviar_consulta
from app.localizacao import dentro_de_goias, limite_de_goias
from app.overpass import elementos_da_resposta

TAMANHO_DO_QUADRO = 2.0  # graus
RODADAS = 12
ESPERA_ENTRE_RODADAS = 45  # segundos
ETIQUETAS_MANTIDAS = ("amenity", "name", "operator", "recycling_type", "access", "phone", "contact:phone", "opening_hours")
PROGRESSO = config.RAIZ / "copia_osm_em_andamento.json"

CONSULTA = (
    "[out:json][timeout:60];("
    'nwr["amenity"="recycling"]({caixa});'
    'nwr["amenity"="waste_transfer_station"]({caixa});'
    ");out tags center;"
)


def quadros() -> list[str]:
    """Divide o retangulo em volta de Goias."""
    longitudes, latitudes = zip(*limite_de_goias())
    caixas = []
    lat = min(latitudes)
    while lat < max(latitudes):
        lon = min(longitudes)
        while lon < max(longitudes):
            caixas.append(f"{lat:.2f},{lon:.2f},{lat + TAMANHO_DO_QUADRO:.2f},{lon + TAMANHO_DO_QUADRO:.2f}")
            lon += TAMANHO_DO_QUADRO
        lat += TAMANHO_DO_QUADRO
    return caixas


def reduzir(elemento: dict) -> dict:
    """Guarda so o que a busca usa, para o arquivo ficar pequeno."""
    centro = elemento.get("center", {})
    return {
        "id": f'{elemento["type"]}/{elemento["id"]}',
        "lat": elemento.get("lat", centro.get("lat")),
        "lon": elemento.get("lon", centro.get("lon")),
        "tags": {
            chave: valor
            for chave, valor in elemento.get("tags", {}).items()
            if chave in ETIQUETAS_MANTIDAS or chave.startswith(("recycling:", "addr:"))
        },
    }


def main() -> int:
    baixados: dict[str, list] = json.loads(PROGRESSO.read_text("utf-8")) if PROGRESSO.exists() else {}
    caixas = quadros()

    for rodada in range(RODADAS):
        faltando = [caixa for caixa in caixas if caixa not in baixados]
        if not faltando:
            break
        print(f"Rodada {rodada + 1}: faltam {len(faltando)} de {len(caixas)} quadros", flush=True)
        for indice, caixa in enumerate(faltando):
            servidor = config.SERVIDORES_OVERPASS[(rodada + indice) % len(config.SERVIDORES_OVERPASS)]
            try:
                resposta = enviar_consulta(servidor, "Overpass", {"data": CONSULTA.format(caixa=caixa)}, 75)
                baixados[caixa] = [reduzir(elemento) for elemento in elementos_da_resposta(resposta)]
            except FalhaExterna as falha:
                print(f"  {caixa}: {falha}", flush=True)
                continue
            PROGRESSO.write_text(json.dumps(baixados, ensure_ascii=False), "utf-8")
            print(f"  {caixa}: {len(baixados[caixa])} pontos", flush=True)
        if any(caixa not in baixados for caixa in caixas):
            time.sleep(ESPERA_ENTRE_RODADAS)

    if any(caixa not in baixados for caixa in caixas):
        print("Incompleto, a copia nao foi trocada. Rode de novo para continuar.", flush=True)
        return 1

    em_goias = {
        elemento["id"]: elemento
        for lista in baixados.values()
        for elemento in lista
        if elemento["lat"] is not None and dentro_de_goias(elemento["lat"], elemento["lon"])
    }
    copia = {"gerado_em": date.today().isoformat(), "elementos": list(em_goias.values())}
    config.ARQUIVO_COPIA_OSM.write_text(json.dumps(copia, ensure_ascii=False, indent=0), "utf-8")
    PROGRESSO.unlink()
    print(f"Copia salva com {len(em_goias)} pontos em {config.ARQUIVO_COPIA_OSM}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
