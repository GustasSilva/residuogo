# Diagramas do ResíduoGO

Os cinco diagramas do sistema, escritos em [Mermaid](https://mermaid.js.org).
O código de cada um está logo abaixo da figura correspondente e é a fonte de
verdade: as imagens em `imagens/` foram exportadas destes blocos.

**Como ver e exportar.** O GitHub e o VS Code (painel de pré-visualização do
Markdown) desenham os diagramas direto deste arquivo. Para gerar uma imagem
nova — depois de mudar alguma coisa no sistema —, cole o bloco em
<https://mermaid.live> e use *Actions → PNG*.

---

## 1. Arquitetura

> Imagem: `imagens/diagrama-1-arquitetura.png`

Quem fala com quem. Os dois web services exigidos pelo trabalho — REST e
SOAP — estão na mesma aplicação e compartilham a camada de serviços, que é
onde moram as regras de negócio. É isso que impede os dois de divergirem: um
manifesto consultado por SOAP passou pelas mesmas regras de um consultado por
REST.

```mermaid
flowchart LR
    subgraph clientes["Clientes"]
        direction TB
        navegador["Navegador<br>React + Vite"]
        swagger["Swagger / curl"]
        zeep["Cliente SOAP<br>zeep"]
    end

    subgraph aplicacao["Aplicação FastAPI"]
        direction TB
        rest["Rotas REST<br>/api/v1"]
        soap["Serviço SOAP<br>/soap/manifesto"]
        documentos["Documentos<br>PDF, CSV e QR code"]
        integracoes["Integrações<br>com cache em memória"]
        servicos["Serviços<br>regras RN01 a RN08"]
    end

    subgraph externos["Serviços externos"]
        direction TB
        ibge["API do IBGE"]
        viacep["ViaCEP"]
    end

    banco[("SQLite<br>residuogo.db")]

    navegador --> rest
    swagger --> rest
    zeep --> soap

    rest --> servicos
    soap --> servicos
    rest --> documentos
    documentos --> servicos
    rest --> integracoes

    integracoes --> ibge
    integracoes --> viacep
    servicos --> banco
```

---

## 2. Modelo de dados

> Imagem: `imagens/diagrama-2-modelo-de-dados.png`

Seis tabelas. As três ligações entre `manifesto` e `organizacao` são os três
papéis do ciclo do resíduo — gerador, transportador e destinador —, e é por
elas que a regra de visibilidade (RN07) decide o que cada usuário enxerga.

A tabela `movimentacao` só recebe inserções: é o histórico de auditoria exigido
pela regra RN03.

```mermaid
erDiagram
    ORGANIZACAO ||--o{ USUARIO : "emprega"
    ORGANIZACAO ||--o{ MANIFESTO : "gera"
    ORGANIZACAO ||--o{ MANIFESTO : "transporta"
    ORGANIZACAO ||--o{ MANIFESTO : "destina"
    MANIFESTO ||--|{ ITEM_MANIFESTO : "contém"
    MANIFESTO ||--o{ MOVIMENTACAO : "registra"
    TIPO_RESIDUO ||--o{ ITEM_MANIFESTO : "classifica"
    USUARIO ||--o{ MOVIMENTACAO : "executa"

    ORGANIZACAO {
        int id PK
        string razao_social
        string cnpj UK
        enum papel "GERADOR, TRANSPORTADOR, DESTINADOR"
        string municipio_ibge_codigo
        string licenca_numero
        date licenca_validade
        bool ativo
    }

    USUARIO {
        int id PK
        string nome
        string email UK
        string senha_hash
        enum perfil "ADMIN, USUARIO"
        int organizacao_id FK "nulo para ADMIN"
        bool ativo
    }

    TIPO_RESIDUO {
        int id PK
        string codigo UK
        string descricao
        enum classe "I, IIA, IIB"
        enum unidade_padrao "KG, T, L, M3"
    }

    MANIFESTO {
        int id PK
        string numero UK "RGO-AAAA-NNNNNN"
        int gerador_id FK
        int transportador_id FK
        int destinador_id FK
        enum status "EMITIDO ... DESTINADO"
        string placa_veiculo
        string motorista_nome
        enum tipo_destinacao
        string motivo_recusa
        string qr_token UK
        datetime emitido_em
        datetime coletado_em
        datetime recebido_em
        datetime destinado_em
    }

    ITEM_MANIFESTO {
        int id PK
        int manifesto_id FK
        int tipo_residuo_id FK
        decimal quantidade_declarada
        decimal quantidade_recebida
        enum unidade
        enum acondicionamento
        bool divergente "RN05"
    }

    MOVIMENTACAO {
        int id PK
        int manifesto_id FK
        int usuario_id FK
        enum status_anterior
        enum status_novo
        datetime data_hora
        string observacao
    }
```

---

## 3. Ciclo de vida do manifesto

> Imagem: `imagens/diagrama-3-ciclo-do-manifesto.png`

A máquina de estados. Cada seta diz quem tem autoridade para percorrê-la
(regra RN01), e o que não está desenhado é recusado com `409` (RN02). Os três
estados finais não admitem nenhuma alteração posterior.

No código, este diagrama é um dicionário — `TRANSICOES`, em
`services/manifestos.py` —, e não uma sequência de condicionais: acrescentar
uma transição nova é acrescentar uma linha.

```mermaid
stateDiagram-v2
    [*] --> EMITIDO: gerador emite
    EMITIDO --> EM_TRANSPORTE: transportador coleta
    EMITIDO --> CANCELADO: gerador cancela
    EM_TRANSPORTE --> RECEBIDO: destinador recebe
    EM_TRANSPORTE --> RECUSADO: destinador recusa
    RECEBIDO --> DESTINADO: destinador destina
    DESTINADO --> [*]
    RECUSADO --> [*]
    CANCELADO --> [*]
```

---

## 4. Uma transição, do clique ao banco

> Imagem: `imagens/diagrama-4-sequencia-da-transicao.png`

O caminho de "confirmar coleta", que é o mesmo das outras quatro transições. O
que importa nele: a tela **não** envia o status novo, apenas o fato ocorrido; o
status resultante é decidido pelo servidor, em um único ponto do sistema. Por
isso a máquina de estados não pode ser contornada pela interface.

```mermaid
sequenceDiagram
    actor usuario as Transportador
    participant tela as Tela (React)
    participant rota as POST /manifestos/{id}/coleta
    participant servico as Serviço do manifesto
    participant banco as SQLite

    usuario->>tela: informa placa e motorista
    tela->>rota: POST com os dados da coleta
    rota->>servico: confirmar_coleta(...)
    servico->>banco: carrega o manifesto
    servico->>servico: visibilidade (RN07) e papel (RN01)
    servico->>servico: transição permitida? (RN02)

    alt transição válida
        servico->>banco: status = EM_TRANSPORTE
        servico->>banco: grava a movimentação (RN03)
        servico-->>rota: manifesto atualizado
        rota-->>tela: 200 com o manifesto
        tela-->>usuario: nova situação e histórico
    else transição recusada
        servico-->>rota: TransicaoInvalida
        rota-->>tela: 409 application/problem+json
        tela-->>usuario: mensagem e código do erro
    end
```

---

## 5. Consulta a um serviço externo

> Imagem: `imagens/diagrama-5-integracao-externa.png`

A política de indisponibilidade, escrita uma vez em `integrations/externo.py` e
usada pelas duas integrações. Ela responde à pergunta que todo sistema que
depende de terceiro precisa responder: o que acontece quando o terceiro cai.

Repare na diferença entre as duas saídas de erro. "O CEP não existe" é uma
resposta **correta** do ViaCEP e vira `404 RECURSO_NAO_ENCONTRADO`, sem passar
pelo cache; "o ViaCEP não respondeu" é falha de comunicação, e aí o sistema
serve o último dado que tem, mesmo vencido, antes de admitir o
`503 SERVICO_EXTERNO_INDISPONIVEL`.

```mermaid
flowchart TD
    inicio([Consulta ao IBGE ou ViaCEP]) --> cache{"Cache<br>dentro da validade?"}
    cache -- sim --> servecache["Responde do cache<br>X-Fonte: cache"]
    cache -- não --> chamada["Chama a API externa<br>limite de 5 s"]

    chamada --> resultado{Resultado}
    resultado -- "resposta boa" --> guarda["Guarda no cache"] --> serveapi["Responde<br>X-Fonte: api"]
    resultado -- "não existe" --> naoexiste["404 — não encontrado<br>não vai para o cache"]
    resultado -- "erro de rede ou 5xx" --> retenta{"Já tentou<br>duas vezes?"}

    retenta -- não --> chamada
    retenta -- sim --> vencido{"Existe cache<br>vencido?"}

    vencido -- sim --> servevencido["Responde o dado antigo<br>X-Fonte: cache-expirado"]
    vencido -- não --> indisponivel["503 — serviço externo<br>indisponível"]
```
