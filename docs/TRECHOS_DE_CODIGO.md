# Trechos de código para o relatório impresso

Gerado por `scripts/exportar_trechos.py` a partir das marcas `APS-TRECHO`
deixadas no código-fonte. Não editar à mão: a próxima execução sobrescreve.

**7 trechos, 231 linhas de código.** O relatório admite cerca de 380 linhas (10 páginas em Arial 12, espaçamento 1,5), então ainda cabem comentários de abertura e as legendas de cada trecho.

| # | Trecho | Onde | Linhas |
|---|---|---|---|
| 1 | De onde vem os pontos, e o que acontece quando o Overpass cai | `backend/app/pontos.py` | 27 |
| 2 | Do CEP ate as coordenadas, da busca mais precisa para a menos precisa | `backend/app/localizacao.py` | 23 |
| 3 | Consulta externa com cache e tratamento de queda | `backend/app/externo.py` | 21 |
| 4 | Do dado cru do OpenStreetMap para um ponto de coleta | `backend/app/pontos.py` | 34 |
| 5 | Todas as respostas de erro no mesmo formato (RFC 7807) | `backend/app/errors.py` | 34 |
| 6 | As rotas do web service | `backend/app/main.py` | 44 |
| 7 | A pagina consumindo o web service | `backend/app/web/app.js` | 48 |

---

## 1. De onde vem os pontos, e o que acontece quando o Overpass cai

`backend/app/pontos.py`, linhas 151 a 177

```python
def _elementos_do_osm(latitude: float, longitude: float, raio_km: int) -> tuple[list[dict], str]:
    """Devolve os elementos do OpenStreetMap e um aviso, se o dado nao for atual."""
    global _ultima_falha_overpass
    chave = f"overpass:{latitude:.3f},{longitude:.3f},{raio_km}"
    guardado = cache.obter(chave)
    if guardado and time.time() - guardado[1] < config.VALIDADE_PONTOS:
        return guardado[0], ""

    # Logo depois de uma falha nao adianta esperar o tempo limite de novo.
    if time.monotonic() - _ultima_falha_overpass >= config.ESPERA_APOS_FALHA_OVERPASS:
        try:
            elementos = _perguntar_ao_overpass(latitude, longitude, raio_km)
            cache.guardar(chave, elementos)
            return elementos, ""
        except FalhaExterna:
            _ultima_falha_overpass = time.monotonic()

    if guardado:
        data = datetime.fromtimestamp(guardado[1]).strftime("%d/%m/%Y")
        return guardado[0], f"O OpenStreetMap não respondeu. Estes pontos são da consulta de {data}."

    copia = _copia_de_reserva()
    if copia is None:
        return [], "O OpenStreetMap não respondeu. Só os pontos da lista do projeto aparecem aqui."

    data = date.fromisoformat(copia["gerado_em"]).strftime("%d/%m/%Y")
    return copia["elementos"], f"O OpenStreetMap não respondeu. Estes pontos são da cópia de {data}."
```

---

## 2. Do CEP ate as coordenadas, da busca mais precisa para a menos precisa

`backend/app/localizacao.py`, linhas 125 a 147

```python
def origem_por_cep(cep: str) -> dict:
    endereco = endereco_do_cep(cep)
    cidade = endereco["localidade"]
    rua = endereco.get("logradouro", "")
    bairro = endereco.get("bairro", "")

    tentativas = []
    if rua:
        tentativas.append(("endereço", {"street": rua, "city": cidade}))
    if bairro:
        tentativas.append(("bairro", {"q": f"{bairro}, {cidade}, Goiás"}))
    tentativas.append(("município", {"city": cidade}))

    for precisao, params in tentativas:
        try:
            coordenadas = _geocodificar(**params)
        except ServicoIndisponivel:
            # Sem Nominatim, o centro do municipio informado pelo IBGE ainda serve.
            break
        if coordenadas:
            return _origem(_descrever(rua, bairro, cidade), coordenadas, precisao)

    return _origem(_descrever(rua, bairro, cidade), _centro_ibge(endereco["ibge"]), "município")
```

---

## 3. Consulta externa com cache e tratamento de queda

`backend/app/externo.py`, linhas 41 a 61

```python
def com_cache(chave: str, validade: int, servico: str, consultar: Callable[[], Any]) -> Any:
    """Devolve o dado do cache ou da API; se a API falhar, usa o cache vencido.

    Sem API e sem cache, a busca nao tem como continuar e o cliente recebe 503.
    """
    guardado = cache.obter(chave)
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

    cache.guardar(chave, dado)
    return dado
```

---

## 4. Do dado cru do OpenStreetMap para um ponto de coleta

`backend/app/pontos.py`, linhas 45 a 78

```python
def ponto_do_elemento(elemento: dict) -> dict | None:
    """Converte um elemento do OpenStreetMap, ou devolve None se ele nao serve."""
    etiquetas = elemento.get("tags", {})
    latitude = elemento.get("lat", elemento.get("center", {}).get("lat"))
    longitude = elemento.get("lon", elemento.get("center", {}).get("lon"))
    nome = etiquetas.get("name") or etiquetas.get("operator") or ""

    if latitude is None or longitude is None:
        return None
    if etiquetas.get("access") in ("private", "no") or NOMES_EXCLUIDOS.search(nome):
        return None
    # A maioria das estacoes de transbordo sem nome e area de aterro, nao ponto de entrega.
    e_transbordo = etiquetas.get("amenity") == "waste_transfer_station"
    if e_transbordo and not nome:
        return None

    materiais = materiais_das_etiquetas(etiquetas)
    agrotoxico = bool(NOMES_DE_AGROTOXICOS.search(nome))
    if agrotoxico:
        materiais = ["agrotoxicos"]

    tipo = _tipo(nome, etiquetas, e_transbordo, agrotoxico)
    return {
        "nome": nome or f"{tipo} (sem nome no mapa)",
        "tipo": tipo,
        "endereco": _endereco(etiquetas),
        "latitude": latitude,
        "longitude": longitude,
        "materiais": materiais,
        "telefone": etiquetas.get("phone") or etiquetas.get("contact:phone") or "",
        "horario": etiquetas.get("opening_hours", ""),
        "observacao": "",
        "fonte": "OpenStreetMap",
    }
```

---

## 5. Todas as respostas de erro no mesmo formato (RFC 7807)

`backend/app/errors.py`, linhas 42 a 75

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

---

## 6. As rotas do web service

`backend/app/main.py`, linhas 37 a 80

```python
def _consultar(cep: str | None, municipio: str | None, raio_km: int, material: str | None) -> dict:
    if bool(cep) == bool(municipio):
        raise DadosInvalidos("Informe o CEP ou o município, um dos dois.")
    if not config.RAIO_MINIMO_KM <= raio_km <= config.RAIO_MAXIMO_KM:
        raise DadosInvalidos(
            f"A distância precisa ficar entre {config.RAIO_MINIMO_KM} e {config.RAIO_MAXIMO_KM} km."
        )
    if material and material not in MATERIAIS:
        raise DadosInvalidos(f"O material {material} não existe. Veja a lista em /api/materiais.")

    if cep:
        origem = localizacao.origem_por_cep(localizacao.limpar_cep(cep))
    else:
        origem = localizacao.origem_por_municipio(municipio)

    encontrados, avisos = pontos.buscar(origem["latitude"], origem["longitude"], raio_km, material)
    return {
        "origem": origem,
        "raio_km": raio_km,
        "material": material or None,
        "total": len(encontrados),
        "pontos": encontrados,
        "avisos": avisos,
    }


@app.get("/api/municipios", response_model=list[Municipio], summary="Municípios de Goiás e suas regiões")
def listar_municipios() -> list[dict]:
    return localizacao.municipios()


@app.get("/api/materiais", response_model=list[Material], summary="Materiais aceitos no filtro da busca")
def listar_materiais() -> list[dict]:
    return para_saida(list(MATERIAIS))


@app.get("/api/pontos", response_model=RespostaPontos, summary="Pontos de coleta perto de um CEP ou município")
def buscar_pontos(
    cep: str | None = Query(None, description="CEP de Goiás, com ou sem traço.", examples=["74230-010"]),
    municipio: str | None = Query(None, description="Código IBGE do município.", examples=["5208707"]),
    raio_km: int = Query(10, description="Distância máxima, em km."),
    material: str | None = Query(None, description="Chave de um item de /api/materiais."),
) -> dict:
    return _consultar(cep, municipio, raio_km, material)
```

---

## 7. A pagina consumindo o web service

`backend/app/web/app.js`, linhas 29 a 76

```js
async function chamarApi(caminho) {
  let resposta;
  try {
    resposta = await fetch(caminho);
  } catch {
    throw new Error("O servidor do ResíduoGO não respondeu. Verifique se ele está ligado.");
  }
  const corpo = await resposta.json().catch(() => null);
  if (!resposta.ok) {
    throw new Error(corpo?.detail ?? "A consulta falhou. Tente novamente.");
  }
  return corpo;
}

function parametrosDaBusca() {
  const parametros = new URLSearchParams({ raio_km: campoRaio.value });
  if (campoCep.value.trim()) parametros.set("cep", campoCep.value.trim());
  if (campoMunicipio.value) parametros.set("municipio", campoMunicipio.value);
  if (campoMaterial.value) parametros.set("material", campoMaterial.value);
  return parametros;
}

async function buscar(evento) {
  evento.preventDefault();

  if (!campoCep.value.trim() && !campoMunicipio.value) {
    mostrarMensagem("Informe um CEP ou escolha um município.", true);
    campoCep.focus();
    return;
  }

  botao.disabled = true;
  botao.textContent = "Buscando...";
  mostrarMensagem("Consultando os pontos. Pode levar alguns segundos.");

  try {
    const parametros = parametrosDaBusca();
    const dados = await chamarApi(`/api/pontos?${parametros}`);
    mostrarMensagem("");
    mostrarResultado(dados, parametros);
  } catch (erro) {
    areaResultado.hidden = true;
    mostrarMensagem(erro.message, true);
  } finally {
    botao.disabled = false;
    botao.textContent = "Buscar pontos";
  }
}
```
