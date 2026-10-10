# Trechos de código para o relatório impresso

Gerado por `scripts/exportar_trechos.py` a partir das marcas `APS-TRECHO`
deixadas no código-fonte. Não editar à mão: a próxima execução sobrescreve.

**6 trechos, 299 linhas de código.** O relatório admite cerca de 380 linhas (10 páginas em Arial 12, espaçamento 1,5), então ainda cabem comentários de abertura e as legendas de cada trecho.

| # | Trecho | Onde | Linhas |
|---|---|---|---|
| 1 | Rotas REST — cada transição é um POST para um sub-recurso | `backend/app/routers/manifestos.py` | 35 |
| 2 | A máquina de estados do manifesto | `backend/app/services/manifestos.py` | 63 |
| 3 | Todo erro responde no formato RFC 7807 | `backend/app/errors.py` | 36 |
| 4 | Serviço SOAP escrito à mão — leitura do envelope e SOAP Fault | `backend/app/soap/envelope.py` | 81 |
| 5 | Consumo do serviço SOAP com zeep — nenhum XML no código | `clients/soap_client.py` | 41 |
| 6 | Integração externa — cache, queda tratada e procedência do dado | `backend/app/integrations/externo.py` | 43 |

---

## 1. Rotas REST — cada transição é um POST para um sub-recurso

`backend/app/routers/manifestos.py`, linhas 41 a 53

```python
@router.post(
    "",
    response_model=ManifestoSaida,
    status_code=status.HTTP_201_CREATED,
    summary="Emite um manifesto (GERADOR)",
)
def emitir(dados: ManifestoCriar, sessao: Sessao, usuario: UsuarioAtual) -> Manifesto:
    """Emite um manifesto em nome da organização do usuário.

    O gerador não é informado no corpo: é a organização de quem emite. Os
    participantes são validados quanto a papel, situação e licença (RN04).
    """
    return servico.emitir(sessao, usuario, dados)
```

`backend/app/routers/manifestos.py`, linhas 182 a 203

```python
@router.post(
    "/{manifesto_id}/coleta",
    response_model=ManifestoSaida,
    summary="Confirma a coleta (TRANSPORTADOR)",
)
def confirmar_coleta(
    manifesto_id: int, dados: ColetaEntrada, sessao: Sessao, usuario: UsuarioAtual
) -> Manifesto:
    """EMITIDO → EM_TRANSPORTE, registrando veículo e motorista."""
    return servico.confirmar_coleta(sessao, usuario, manifesto_id, dados)


@router.post(
    "/{manifesto_id}/recebimento",
    response_model=ManifestoSaida,
    summary="Registra o recebimento da carga (DESTINADOR)",
)
def registrar_recebimento(
    manifesto_id: int, dados: RecebimentoEntrada, sessao: Sessao, usuario: UsuarioAtual
) -> Manifesto:
    """EM_TRANSPORTE → RECEBIDO, conferindo a quantidade de cada item (RN05)."""
    return servico.registrar_recebimento(sessao, usuario, manifesto_id, dados)
```

---

## 2. A máquina de estados do manifesto

`backend/app/services/manifestos.py`, linhas 67 a 79

```python
TRANSICOES: dict[StatusManifesto, dict[StatusManifesto, PapelOrganizacao]] = {
    StatusManifesto.EMITIDO: {
        StatusManifesto.EM_TRANSPORTE: PapelOrganizacao.TRANSPORTADOR,
        StatusManifesto.CANCELADO: PapelOrganizacao.GERADOR,
    },
    StatusManifesto.EM_TRANSPORTE: {
        StatusManifesto.RECEBIDO: PapelOrganizacao.DESTINADOR,
        StatusManifesto.RECUSADO: PapelOrganizacao.DESTINADOR,
    },
    StatusManifesto.RECEBIDO: {
        StatusManifesto.DESTINADO: PapelOrganizacao.DESTINADOR,
    },
}
```

`backend/app/services/manifestos.py`, linhas 166 a 215

```python
def _aplicar_transicao(
    sessao: Session,
    usuario: Usuario,
    manifesto: Manifesto,
    novo_status: StatusManifesto,
    observacao: str | None = None,
) -> None:
    """Muda o status do manifesto, validando e registrando a mudanca.

    Unico ponto do sistema que altera `manifesto.status`. Toda transicao passa
    por aqui, e por isso as regras RN02 e RN03 valem sempre, sem depender de
    cada rota se lembrar de aplica-las.

    A movimentacao e gravada na mesma sessao da mudanca de status: as duas vao
    para o banco no mesmo `commit`, ou nenhuma vai. Nao existe status alterado
    sem registro no historico.
    """
    destinos_permitidos = TRANSICOES.get(manifesto.status, {})

    # Regra RN02.
    if novo_status not in destinos_permitidos:
        if not destinos_permitidos:
            detalhe = (
                f"O manifesto {manifesto.numero} está {manifesto.status.value}, "
                f"que é um estado final, e não admite novas alterações."
            )
        else:
            possiveis = ", ".join(sorted(status.value for status in destinos_permitidos))
            detalhe = (
                f"O manifesto {manifesto.numero} está {manifesto.status.value} e não "
                f"pode ir para {novo_status.value}. Transições possíveis: {possiveis}."
            )
        raise TransicaoInvalida(detalhe)

    # Regra RN01.
    _exigir_papel(usuario, manifesto, destinos_permitidos[novo_status])

    status_anterior = manifesto.status
    manifesto.status = novo_status

    # Regra RN03.
    sessao.add(
        Movimentacao(
            manifesto_id=manifesto.id,
            status_anterior=status_anterior,
            status_novo=novo_status,
            usuario_id=usuario.id,
            observacao=observacao,
        )
    )
```

---

## 3. Todo erro responde no formato RFC 7807

`backend/app/errors.py`, linhas 172 a 195

```python
def _resposta_problema(
    request: Request,
    *,
    status: int,
    codigo: str,
    titulo: str,
    detalhe: str,
    erros: list[dict] | None = None,
) -> JSONResponse:
    """Monta a resposta de erro no formato RFC 7807.

    Unico ponto do projeto que constroi corpo de erro. Centralizar aqui e o
    que garante que todas as respostas tenham a mesma forma.
    """
    corpo = {
        "type": _uri_do_tipo(codigo),
        "title": titulo,
        "status": status,
        "detail": detalhe,
        "instance": request.url.path,
        "codigo": codigo,
        "erros": erros or [],
    }
    return JSONResponse(status_code=status, content=corpo, media_type=MIDIA_PROBLEMA)
```

`backend/app/errors.py`, linhas 241 a 252

```python
    @app.exception_handler(ErroDominio)
    async def _dominio(request: Request, exc: ErroDominio) -> JSONResponse:
        """Erros previstos: a mensagem vai inteira para o cliente."""
        logger.info("[%s] %s - %s", request.url.path, exc.codigo, exc.detalhe)
        return _resposta_problema(
            request,
            status=exc.status,
            codigo=exc.codigo,
            titulo=exc.titulo,
            detalhe=exc.detalhe,
            erros=exc.erros,
        )
```

---

## 4. Serviço SOAP escrito à mão — leitura do envelope e SOAP Fault

`backend/app/soap/envelope.py`, linhas 44 a 96

```python
def _leitor_seguro() -> etree.XMLParser:
    """Cria o leitor de XML com as defesas necessarias ligadas.

    XML aceita declarar entidades que o leitor expande ao processar o
    documento. Um atacante pode usar isso para fazer o servidor ler arquivos
    locais ou abrir conexoes de rede - os ataques conhecidos como XXE
    (XML External Entity) e "billion laughs".

    Como este endpoint recebe XML de fora, as tres defesas sao obrigatorias:
    nao resolver entidades, nao carregar DTD e nao acessar a rede.
    """
    return etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)


def extrair_operacao(mensagem: bytes) -> tuple[str, dict[str, str]]:
    """Le o envelope recebido e devolve o nome da operacao e seus parametros.

    Devolve, para o exemplo do inicio do modulo:

        ("ConsultarStatusManifesto",
         {"numero": "RGO-2026-000001", "cnpj_consultante": "11222333000181"})

    A operacao e identificada pelo nome do elemento dentro do `Body`, e nao
    pelo cabecalho HTTP `SOAPAction`: o cabecalho e opcional em muitos
    clientes, enquanto o elemento esta sempre presente.
    """
    try:
        envelope = etree.fromstring(mensagem, parser=_leitor_seguro())
    except etree.XMLSyntaxError as erro:
        raise EnvelopeInvalido(f"XML mal formado: {erro}") from erro

    if etree.QName(envelope).localname != "Envelope":
        raise EnvelopeInvalido("O elemento raiz da mensagem deve ser soap:Envelope.")

    corpo = envelope.find(f"{{{NS_SOAP}}}Body")
    if corpo is None:
        raise EnvelopeInvalido("O envelope não contém soap:Body.")

    # `len()` em um elemento lxml conta os filhos, nao caracteres.
    elementos = [filho for filho in corpo if isinstance(filho.tag, str)]
    if not elementos:
        raise EnvelopeInvalido("O soap:Body está vazio: nenhuma operação foi informada.")

    chamada = elementos[0]
    operacao = etree.QName(chamada).localname

    parametros = {
        etree.QName(parametro).localname: (parametro.text or "").strip()
        for parametro in chamada
        if isinstance(parametro.tag, str)
    }

    return operacao, parametros
```

`backend/app/soap/envelope.py`, linhas 131 a 158

```python
def montar_falha(mensagem: str, codigo: str, *, culpa_do_cliente: bool = True) -> bytes:
    """Monta um SOAP Fault, a forma padrao de relatar erro em SOAP.

    O `faultcode` tem valores definidos pela especificacao: `soap:Client`
    quando a mensagem recebida esta errada (manifesto inexistente, CNPJ sem
    permissao) e `soap:Server` quando a falha e do servidor. E o equivalente a
    diferenca entre os codigos HTTP 4xx e 5xx.

    Os tres elementos `faultcode`, `faultstring` e `detail` nao levam
    namespace: no SOAP 1.1 eles sao deliberadamente sem qualificacao.

    Dentro de `detail` vai o codigo interno do erro, o mesmo vocabulario
    usado pelas respostas REST (`codigo` na RFC 7807), para que os dois
    servicos relatem o mesmo problema com o mesmo nome.
    """
    envelope, corpo = _novo_envelope()
    falha = etree.SubElement(corpo, f"{{{NS_SOAP}}}Fault")

    # O conteudo e um QName: o prefixo "soap" ja esta declarado no envelope.
    etree.SubElement(falha, "faultcode").text = "soap:Client" if culpa_do_cliente else "soap:Server"
    etree.SubElement(falha, "faultstring").text = mensagem

    detalhe = etree.SubElement(falha, "detail")
    erro = etree.SubElement(detalhe, f"{{{NS_SERVICO}}}ManifestoFault")
    etree.SubElement(erro, f"{{{NS_SERVICO}}}codigo").text = codigo
    etree.SubElement(erro, f"{{{NS_SERVICO}}}mensagem").text = mensagem

    return _serializar(envelope)
```

---

## 5. Consumo do serviço SOAP com zeep — nenhum XML no código

`clients/soap_client.py`, linhas 32 a 72

```python
def consultar(url_wsdl: str, numero: str, cnpj: str) -> int:
    """Consulta um manifesto e imprime o resultado.

    Devolve o codigo de saida do processo: 0 em caso de sucesso e 1 em caso de
    falha, para que o script possa ser usado dentro de outro automatismo.
    """
    print(f"Lendo o contrato em {url_wsdl}")

    try:
        cliente = Client(url_wsdl)
    except Exception as erro:
        print(f"\nNão foi possível ler o WSDL: {erro}", file=sys.stderr)
        print("O servidor está rodando? (uvicorn app.main:app)", file=sys.stderr)
        return 1

    print(f"Consultando o manifesto {numero} como o CNPJ {cnpj}\n")

    try:
        # Chamada da operacao descrita no WSDL. Os nomes dos argumentos sao os
        # mesmos declarados no XML Schema do contrato.
        resposta = cliente.service.ConsultarStatusManifesto(
            numero=numero,
            cnpj_consultante=cnpj,
        )
    except Fault as falha:
        # Um SOAP Fault chega ao Python como excecao. `message` traz o
        # `faultstring` e `code`, o `faultcode` - o equivalente SOAP de um
        # erro 4xx/5xx do REST.
        print("O serviço respondeu com um SOAP Fault:")
        print(f"  código   : {falha.code}")
        print(f"  mensagem : {falha.message}")
        return 1

    print("Manifesto encontrado:")
    print(f"  número          : {resposta.numero}")
    print(f"  status          : {resposta.status}")
    print(f"  gerador         : {resposta.gerador_razao_social}")
    print(f"  destinador      : {resposta.destinador_razao_social}")
    print(f"  tipo destinação : {resposta.tipo_destinacao or '(ainda não destinado)'}")
    print(f"  atualizado em   : {resposta.atualizado_em}")
    return 0
```

---

## 6. Integração externa — cache, queda tratada e procedência do dado

`backend/app/integrations/externo.py`, linhas 130 a 172

```python
def obter_com_cache(
    *,
    cache: CacheComValidade,
    chave: str,
    ttl_segundos: int,
    servico: str,
    consultar: Callable[[], Dado],
) -> tuple[Dado, Fonte]:
    """Devolve o dado e a sua procedencia, nesta ordem de preferencia:

    1. cache dentro da validade, sem chamar a API;
    2. resposta nova da API, que passa a ser o cache;
    3. ultimo cache guardado, mesmo vencido, quando a API falha;
    4. erro 503, quando a API falha e nao ha nada guardado.

    `consultar` e a funcao que faz a chamada e converte a resposta para o
    formato do sistema - e esse formato convertido que vai para o cache, nao o
    JSON cru do terceiro.

    Erros de dominio levantados por `consultar` atravessam esta funcao sem
    tratamento. Um CEP inexistente, por exemplo, nao e falha de comunicacao: a
    API respondeu, e a resposta correta foi "nao existe". Servir cache naquele
    caso esconderia uma informacao verdadeira.
    """
    guardado = cache.obter(chave)
    if guardado is not None:
        return guardado, Fonte.CACHE

    try:
        dado = consultar()
    except FalhaDeComunicacao as falha:
        reserva = cache.obter_ultimo(chave)
        if reserva is None:
            raise ServicoExternoIndisponivel(
                f"{servico} está indisponível e não há dado guardado em cache "
                "para responder. Tente novamente em alguns instantes."
            ) from falha

        logger.warning("%s indisponível (%s); servindo cache vencido.", servico, falha)
        return reserva, Fonte.CACHE_EXPIRADO

    cache.guardar(chave, dado, ttl_segundos)
    return dado, Fonte.API
```
