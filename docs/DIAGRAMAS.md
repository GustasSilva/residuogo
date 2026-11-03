# Diagramas

Em Mermaid: o GitHub desenha direto, e em [mermaid.live](https://mermaid.live) dá para exportar a imagem para o relatório.

## Componentes

```mermaid
flowchart LR
    pagina["Página web<br/>HTML, CSS e JavaScript"]

    subgraph servico["Web service REST (FastAPI)"]
        main["main.py<br/>rotas"]
        pontos["pontos.py<br/>a busca"]
        localizacao["localizacao.py"]
        overpass["overpass.py"]
        externo["externo.py<br/>HTTP e cache"]
        cache[("cache.db<br/>SQLite")]
        dados["dados/<br/>ecopontos, cópia<br/>e contorno de Goiás"]
    end

    ibge["IBGE"]
    viacep["ViaCEP"]
    nominatim["Nominatim"]
    apiOverpass["Overpass"]
    tiles["Mapa do OpenStreetMap"]

    pagina -- "JSON e CSV" --> main
    pagina -- "imagens do mapa" --> tiles
    main --> localizacao
    main --> pontos
    pontos --> overpass
    pontos --> dados
    localizacao --> dados
    overpass --> dados
    localizacao --> externo
    overpass --> externo
    externo --> cache
    externo --> ibge
    externo --> viacep
    externo --> nominatim
    externo --> apiOverpass
```

## Busca por CEP

```mermaid
sequenceDiagram
    actor Pessoa
    participant P as Página web
    participant S as Web service
    participant V as ViaCEP
    participant N as Nominatim
    participant O as Overpass

    Pessoa->>P: digita o CEP, escolhe material e distância
    P->>S: GET /api/pontos?cep=...&raio_km=...&material=...
    S->>V: endereço do CEP
    V-->>S: rua, bairro, cidade e código IBGE
    S->>N: coordenadas do endereço
    N-->>S: latitude e longitude
    S->>O: pontos de coleta em volta
    O-->>S: elementos do mapa
    S->>S: junta os ecopontos, tira o que está fora de Goiás e as duplicatas, filtra e ordena
    S-->>P: origem, pontos e avisos (JSON)
    P-->>Pessoa: lista e mapa
```

## De onde vêm os pontos

```mermaid
flowchart TD
    inicio["Busca em uma coordenada"] --> cache{"Tem consulta<br/>de menos de 1 dia?"}
    cache -- sim --> usar["Usa a consulta guardada"]
    cache -- não --> falhou{"Overpass falhou<br/>nos últimos 2 minutos?"}
    falhou -- não --> perguntar["Pergunta a 3 servidores<br/>e espera até 8 s"]
    perguntar --> respondeu{"Algum respondeu?"}
    respondeu -- sim --> guardar["Guarda no cache e usa"]
    respondeu -- não --> copia["Usa a cópia de Goiás<br/>e avisa a data"]
    falhou -- sim --> copia
    usar --> final["Junta com os ecopontos de Goiânia<br/>e mantém só o que está em Goiás"]
    guardar --> final
    copia --> final
    final --> raio{"Tem ponto na<br/>distância escolhida?"}
    raio -- sim --> lista["Mostra os pontos do raio"]
    raio -- não --> proximos["Mostra os 3 mais próximos do estado"]
```

## Do CEP até as coordenadas

```mermaid
flowchart TD
    cep["CEP"] --> viacep["ViaCEP: rua, bairro e cidade"]
    viacep --> rua{"Nominatim achou a rua?"}
    rua -- sim --> r1["Precisão: endereço"]
    rua -- não --> bairro{"Achou o bairro?"}
    bairro -- sim --> r2["Precisão: bairro"]
    bairro -- não --> cidade{"Achou a cidade?"}
    cidade -- sim --> r3["Precisão: município"]
    cidade -- não --> ibge["Centro do município, pelo IBGE"]
    ibge --> r3
```
