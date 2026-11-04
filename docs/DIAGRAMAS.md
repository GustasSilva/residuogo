# Diagramas

Em Mermaid: o GitHub desenha direto, e em [mermaid.live](https://mermaid.live) dá para exportar a imagem.

## Componentes

Cada camada só chama a de baixo. A exceção é o contorno de Goiás, que vai da API do IBGE direto para a rota.

```mermaid
flowchart TB
    pagina["Página web<br/>HTML, CSS e JavaScript"]

    subgraph servico["Web service REST (FastAPI)"]
        subgraph rotas["rotas/"]
            api["api.py<br/>as 6 rotas"]
            exportacao["exportacao.py<br/>CSV e PDF"]
        end
        subgraph servicos["servicos/"]
            localizacao["localizacao.py<br/>o local da busca"]
            pontos["pontos.py<br/>os pontos de coleta"]
            geo["geo.py<br/>Haversine e retângulos"]
        end
        subgraph apis["apis/"]
            ibge["ibge.py"]
            viacep["viacep.py"]
            nominatim["nominatim.py"]
            cache["cache.py<br/>HTTP e cache"]
        end
        banco[("cache.db<br/>SQLite")]
    end

    api_ibge["API do IBGE<br/>municípios e contorno"]
    api_viacep["API do ViaCEP"]
    api_nominatim["API do Nominatim<br/>(OpenStreetMap)"]
    tiles["Mapa do OpenStreetMap"]

    pagina -- "JSON, CSV e PDF" --> api
    pagina -- "imagens do mapa" --> tiles
    api --> exportacao
    api --> localizacao
    api --> pontos
    api -- "contorno" --> ibge
    localizacao --> ibge
    localizacao --> viacep
    localizacao --> nominatim
    pontos --> nominatim
    localizacao --> geo
    pontos --> geo
    ibge --> cache
    viacep --> cache
    nominatim --> cache
    cache --> banco
    cache --> api_ibge
    cache --> api_viacep
    cache --> api_nominatim
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
    raio -- não --> area["Procura numa área maior<br/>(50, depois 100, depois 250 km)<br/>e junta com o que já achou"]
    area --> tres{"Os 3 mais próximos já estão<br/>dentro desta área?"}
    tres -- "não, e ainda há área maior" --> area
    tres -- "sim, ou chegou a 250 km" --> proximos["Mostra os 3 mais próximos"]
```

As áreas menores vêm primeiro porque, numa área grande, os muitos pontos do DF ocupam o limite de 50 resultados do Nominatim e pontos de Goiás podem ficar de fora.

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
