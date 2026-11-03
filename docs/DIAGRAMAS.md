# Diagramas

Em Mermaid: o GitHub desenha direto, e em [mermaid.live](https://mermaid.live) dá para exportar a imagem para o relatório.

## Componentes

```mermaid
flowchart LR
    pagina["Página web<br/>HTML, CSS e JavaScript"]

    subgraph servico["Web service REST (FastAPI)"]
        main["main.py<br/>rotas"]
        pontos["pontos.py<br/>a busca dos pontos"]
        localizacao["localizacao.py<br/>o local da busca"]
        externo["externo.py<br/>HTTP e cache"]
        cache[("cache.db<br/>SQLite")]
    end

    ibge["IBGE<br/>municípios e contorno"]
    viacep["ViaCEP"]
    nominatim["Nominatim<br/>(OpenStreetMap)"]
    tiles["Mapa do OpenStreetMap"]

    pagina -- "JSON e CSV" --> main
    pagina -- "imagens do mapa" --> tiles
    main --> localizacao
    main --> pontos
    localizacao --> externo
    pontos --> externo
    externo --> cache
    externo --> ibge
    externo --> viacep
    externo --> nominatim
```

## Busca por CEP

```mermaid
sequenceDiagram
    actor Pessoa
    participant P as Página web
    participant S as Web service
    participant V as ViaCEP
    participant N as Nominatim

    Pessoa->>P: digita o CEP, escolhe material e distância
    P->>S: GET /api/pontos?local=...&raio_km=...&material=...
    S->>V: endereço do CEP
    V-->>S: rua, bairro e cidade
    S->>N: coordenadas da rua
    N-->>S: latitude e longitude
    S->>N: pontos de reciclagem na área e ecopontos do estado
    N-->>S: lugares do mapa, com estado, endereço e etiquetas
    S->>S: mantém os de Goiás que recebem entrega, filtra o material, calcula a distância e ordena
    S-->>P: origem e pontos (JSON)
    P-->>Pessoa: lista e mapa
```

## De onde vêm os pontos

```mermaid
flowchart TD
    inicio["Busca em uma coordenada"] --> cache{"Esta área foi consultada<br/>há menos de 1 dia?"}
    cache -- sim --> usar["Usa a resposta guardada"]
    cache -- não --> perguntar["Nominatim: pontos de reciclagem na área<br/>e ecopontos do estado"]
    perguntar --> respondeu{"Respondeu?"}
    respondeu -- sim --> guardar["Guarda no cache e usa"]
    respondeu -- não --> antiga{"Tem resposta antiga<br/>guardada?"}
    antiga -- sim --> usar
    antiga -- não --> erro["Erro 503"]
    usar --> filtrar["Mantém só os de Goiás que recebem entrega,<br/>filtra o material e calcula a distância"]
    guardar --> filtrar
    filtrar --> raio{"Tem ponto na<br/>distância escolhida?"}
    raio -- sim --> lista["Mostra os pontos do raio"]
    raio -- não --> proximos["Busca de novo em 250 km<br/>e mostra os 3 mais próximos"]
```

## Do texto digitado até as coordenadas

```mermaid
flowchart TD
    texto["Texto digitado"] --> tipo{"O que é?"}
    tipo -- "só números" --> viacep["ViaCEP: rua, bairro e cidade"]
    tipo -- "nome de um município" --> cidade
    tipo -- "outro texto" --> lugar["Nominatim: procura dentro de Goiás"]
    lugar --> achou{"Achou?"}
    achou -- sim --> r4["Precisão: lugar"]
    achou -- não --> erro["Erro 404, com uma dica"]
    viacep --> rua{"Nominatim achou a rua?"}
    rua -- sim --> r1["Precisão: endereço"]
    rua -- não --> bairro{"Achou o bairro?"}
    bairro -- sim --> r2["Precisão: bairro"]
    bairro -- não --> cidade{"Achou a cidade?"}
    cidade -- sim --> r3["Precisão: município"]
    cidade -- não --> erro
```
