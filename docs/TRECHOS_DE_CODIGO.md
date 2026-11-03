# Trechos de código para o relatório

Gerado por `scripts/exportar_trechos.py`. Não editar à mão.

8 trechos, 284 linhas. O limite é de cerca de 380 linhas.

## 1. As rotas do web service

`app/main.py`

```python
def _consultar(
    cep: str | None = Query(None, description="CEP de Goiás, com ou sem traço.", examples=["74230-010"]),
    municipio: str | None = Query(None, description="Código IBGE do município.", examples=["5208707"]),
    lat: float | None = Query(None, description="Latitude de um ponto em Goiás, junto com lon."),
    lon: float | None = Query(None, description="Longitude de um ponto em Goiás, junto com lat."),
    raio_km: int = Query(10, description="Distância máxima, em km."),
    material: str | None = Query(None, description="Chave de um item de /api/materiais."),
) -> dict:
    """Valida os parametros e faz a busca. Serve as rotas em JSON e em CSV."""
    ponto_no_mapa = lat is not None or lon is not None
    if sum([bool(cep), bool(municipio), ponto_no_mapa]) != 1:
        raise DadosInvalidos("Informe o CEP, o município ou um ponto no mapa, um dos três.")
    if not config.RAIO_MINIMO_KM <= raio_km <= config.RAIO_MAXIMO_KM:
        raise DadosInvalidos(
            f"A distância precisa ficar entre {config.RAIO_MINIMO_KM} e {config.RAIO_MAXIMO_KM} km."
        )
    if material and material not in MATERIAIS:
        raise DadosInvalidos(f"O material {material} não existe. Veja a lista em /api/materiais.")

    if cep:
        origem = localizacao.origem_por_cep(localizacao.limpar_cep(cep))
    elif municipio:
        origem = localizacao.origem_por_municipio(municipio)
    else:
        origem = localizacao.origem_por_coordenadas(lat, lon)

    busca = pontos.buscar(origem["latitude"], origem["longitude"], raio_km, material)
    return {
        "origem": origem,
        "raio_km": raio_km,
        "material": material or None,
        "total": len(busca["pontos"]),
        **busca,
    }


@app.get("/api/pontos", response_model=RespostaPontos, summary="Pontos de coleta perto de um CEP, município ou ponto no mapa")
def buscar_pontos(resultado: dict = Depends(_consultar)) -> dict:
    return resultado


@app.get("/api/pontos.csv", summary="Mesma busca de /api/pontos, em planilha CSV")
def exportar_pontos(resultado: dict = Depends(_consultar)) -> Response:
    return Response(
        content=_planilha(resultado["pontos"]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="pontos-de-coleta.csv"'},
    )


@app.get("/api/municipios", response_model=list[Municipio], summary="Municípios de Goiás e suas regiões")
def listar_municipios() -> list[dict]:
    return localizacao.municipios()


@app.get("/api/materiais", response_model=list[Material], summary="Materiais aceitos no filtro da busca")
def listar_materiais() -> list[dict]:
    return para_saida(list(MATERIAIS))


@app.get("/api/goias", summary="Contorno oficial de Goiás, em GeoJSON")
def contorno_de_goias() -> FileResponse:
    return FileResponse(config.ARQUIVO_LIMITE_GOIAS, media_type="application/geo+json")
```

## 2. A busca dos pontos de coleta

`app/pontos.py`

```python
def buscar(latitude: float, longitude: float, raio_km: int, material: str | None) -> dict:
    """Pontos dentro do raio. Sem nenhum, os mais proximos de todo o estado."""
    elementos, aviso = overpass.elementos_perto(latitude, longitude, raio_km)
    avisos = [aviso] if aviso else []

    ordenados = _pontos_ordenados(latitude, longitude, elementos, material)
    no_raio = [ponto for ponto in ordenados if ponto["distancia_km"] <= raio_km]
    if no_raio:
        return {"pontos": no_raio, "avisos": avisos, "fora_do_raio": False}

    # Goias tem poucos pontos mapeados, entao um raio vazio e comum.
    todos = _pontos_ordenados(latitude, longitude, overpass.elementos_de_goias(), material)
    return {"pontos": todos[:QUANTOS_MAIS_PROXIMOS], "avisos": avisos, "fora_do_raio": True}
```

## 3. Do CEP ate as coordenadas, da busca mais precisa para a menos precisa

`app/localizacao.py`

```python
def origem_por_cep(cep: str) -> dict:
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
    return _origem(descricao, tentativas, endereco["ibge"])


def origem_por_coordenadas(latitude: float | None, longitude: float | None) -> dict:
    if latitude is None or longitude is None:
        raise DadosInvalidos("Informe a latitude e a longitude do ponto.")
    if not dentro_de_goias(latitude, longitude):
        raise DadosInvalidos("Esse local fica fora de Goiás. Escolha um ponto dentro do estado.")
    return {"descricao": "Ponto escolhido no mapa", "latitude": latitude, "longitude": longitude, "precisao": "mapa"}


def origem_por_municipio(codigo: str) -> dict:
    if not re.fullmatch(r"52\d{5}", codigo):
        raise DadosInvalidos("O código do município precisa ser um código IBGE de Goiás, com 7 dígitos.")
    cidade = _nome_do_municipio(codigo)
    return _origem(f"{cidade} - GO", [("município", {"city": cidade})], codigo)


def _origem(descricao: str, tentativas: list[tuple[str, dict]], codigo_ibge: str) -> dict:
    """Usa a primeira coordenada encontrada; sem nenhuma, o centro do municipio pelo IBGE."""
    coordenadas, precisao = None, "município"
    for precisao_da_busca, busca in tentativas:
        try:
            coordenadas = _coordenadas_nominatim(**busca)
        except ServicoIndisponivel:
            break
        if coordenadas:
            precisao = precisao_da_busca
            break

    latitude, longitude = coordenadas or _centro_do_municipio(codigo_ibge)
    return {"descricao": descricao, "latitude": latitude, "longitude": longitude, "precisao": precisao}
```

## 4. De onde vem os pontos, e o que acontece quando o Overpass cai

`app/overpass.py`

```python
def elementos_perto(latitude: float, longitude: float, raio_km: int) -> tuple[list[dict], str]:
    """Devolve os elementos do mapa e um aviso, quando eles vierem da copia."""
    global _ultima_falha
    celula = round(latitude, 1), round(longitude, 1)
    chave = f"overpass:{celula[0]},{celula[1]},{raio_km}"
    guardado = ler_do_cache(chave)
    if guardado and time.time() - guardado[1] < config.VALIDADE_PONTOS:
        return guardado[0], ""

    # Logo depois de uma falha nao adianta esperar o tempo limite de novo.
    if time.monotonic() - _ultima_falha >= config.ESPERA_APOS_FALHA_OVERPASS:
        try:
            return _perguntar_aos_servidores(chave, *celula, raio_km + FOLGA_DA_CELULA_KM), ""
        except FalhaExterna:
            _ultima_falha = time.monotonic()

    copia = _copia_de_reserva()
    data = date.fromisoformat(copia["gerado_em"]).strftime("%d/%m/%Y")
    return copia["elementos"], f"O OpenStreetMap não respondeu. Estes pontos são da cópia de {data}."
```

## 5. Do dado cru do OpenStreetMap para um ponto de coleta

`app/overpass.py`

```python
def ponto_do_elemento(elemento: dict) -> dict | None:
    """Converte um elemento do mapa, ou devolve None se ele nao recebe entregas."""
    etiquetas = elemento.get("tags", {})
    latitude = elemento.get("lat", elemento.get("center", {}).get("lat"))
    longitude = elemento.get("lon", elemento.get("center", {}).get("lon"))
    nome = etiquetas.get("name") or etiquetas.get("operator") or ""

    if latitude is None or longitude is None:
        return None
    if etiquetas.get("access") in ("private", "no") or NOMES_EXCLUIDOS.search(nome):
        return None
    # Estacao de transbordo costuma ser area de aterro ou de empresa, nao ponto de entrega.
    if etiquetas.get("amenity") == "waste_transfer_station" and "ecoponto" not in nome.casefold():
        return None

    agrotoxico = bool(NOMES_DE_AGROTOXICOS.search(nome))
    tipo = _tipo(nome, etiquetas, agrotoxico)
    return {
        "nome": nome or f"{tipo} (sem nome no mapa)",
        "tipo": tipo,
        "endereco": _endereco(etiquetas),
        "latitude": latitude,
        "longitude": longitude,
        "materiais": ["agrotoxicos"] if agrotoxico else materiais_das_etiquetas(etiquetas),
        "telefone": etiquetas.get("phone") or etiquetas.get("contact:phone") or "",
        "horario": etiquetas.get("opening_hours", ""),
        "observacao": "",
        "fonte": "OpenStreetMap",
    }
```

## 6. Consulta externa com cache e tratamento de queda

`app/externo.py`

```python
def com_cache(chave: str, validade: int, servico: str, consultar: Callable[[], Any]) -> Any:
    """Devolve o dado do cache ou da API; se a API falhar, usa o cache vencido.

    Sem API e sem cache, a busca nao tem como continuar e o cliente recebe 503.
    """
    guardado = ler_do_cache(chave)
    if guardado and time.time() - guardado[1] < validade:
        return guardado[0]

    try:
        dado = consultar()
    except FalhaExterna as falha:
        logger.warning("Falha externa: %s", falha)
        if guardado:
            return guardado[0]
        raise ServicoIndisponivel(
            f"O serviço {servico} não respondeu. Tente novamente em alguns instantes."
        ) from falha

    guardar_no_cache(chave, dado)
    return dado
```

## 7. Todas as respostas de erro no mesmo formato (RFC 7807)

`app/erros.py`

```python
def _problema(request: Request, status: int, titulo: str, detalhe: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "title": titulo,
            "status": status,
            "detail": detalhe,
            "instance": request.url.path,
        },
    )


def registrar_handlers(app: FastAPI) -> None:
    @app.exception_handler(ErroDaBusca)
    async def _erro_da_busca(request: Request, exc: ErroDaBusca) -> JSONResponse:
        return _problema(request, exc.status, exc.titulo, exc.detalhe)

    @app.exception_handler(RequestValidationError)
    async def _validacao(request: Request, exc: RequestValidationError) -> JSONResponse:
        campos = ", ".join(str(erro["loc"][-1]) for erro in exc.errors())
        return _problema(request, 422, "Dados inválidos", f"Valor inválido em: {campos}.")

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return _problema(request, 404, "Não encontrado", "Este endereço não existe.")
        return _problema(request, exc.status_code, "Erro na requisição", "A requisição não foi aceita.")

    @app.exception_handler(Exception)
    async def _inesperado(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Falha inesperada em %s", request.url.path)
        return _problema(request, 500, "Erro interno", "Ocorreu uma falha inesperada no servidor.")
```

## 8. A pagina consumindo o web service

`web/app.js`

```js
async function chamarApi(caminho, opcoes) {
  let resposta;
  try {
    resposta = await fetch(caminho, opcoes);
  } catch (erro) {
    if (erro.name === "AbortError") throw erro;
    throw new Error("O servidor do ResíduoGO não respondeu. Verifique se ele está ligado.");
  }
  const corpo = await resposta.json().catch(() => null);
  if (!resposta.ok) {
    throw new Error(corpo?.detail ?? "A consulta falhou. Tente novamente.");
  }
  return corpo;
}

function parametrosDaBusca(ponto) {
  const parametros = new URLSearchParams({ raio_km: campoRaio.value });
  if (ponto) {
    parametros.set("lat", ponto.lat);
    parametros.set("lon", ponto.lon);
  } else if (campoCep.value) {
    parametros.set("cep", campoCep.value);
  } else if (campoMunicipio.value) {
    parametros.set("municipio", campoMunicipio.value);
  }
  if (campoMaterial.value) parametros.set("material", campoMaterial.value);
  return parametros;
}

async function buscar(ponto = pontoNoMapa) {
  // Uma busca nova cancela a anterior, para a resposta antiga nao sobrescrever a nova.
  buscaEmAndamento?.abort();
  const busca = new AbortController();
  buscaEmAndamento = busca;

  const parametros = parametrosDaBusca(ponto);
  indicarBusca(true);
  mostrarMensagem("Procurando pontos...");
  const demora = setTimeout(() => {
    mostrarMensagem("O OpenStreetMap está demorando. Se ele não responder, usamos os dados guardados.");
  }, 3000);

  try {
    const dados = await chamarApi(`/api/pontos?${parametros}`, { signal: busca.signal });
    if (busca.signal.aborted) return;
    pontoNoMapa = ponto;
    if (ponto) {
      campoCep.value = "";
      campoMunicipio.value = "";
    }
    mostrarMensagem("");
    mostrarResultado(dados, parametros);
  } catch (erro) {
    if (erro.name !== "AbortError") mostrarMensagem(erro.message, true);
  } finally {
    clearTimeout(demora);
    if (buscaEmAndamento === busca) indicarBusca(false);
  }
}
```
