# Como o ResíduoGO funciona

Resumo técnico do sistema, pensado para conferir o trabalho com o enunciado e para preparar a apresentação.

## Em duas frases

O ResíduoGO é um web service REST em Python, feito com FastAPI, que a cada requisição consulta as APIs do IBGE (municípios e contorno do estado), do ViaCEP (endereço a partir do CEP) e do Nominatim, do OpenStreetMap (coordenadas, pontos de reciclagem e estado de cada lugar), e é consumido por uma página em HTML, CSS e JavaScript com mapa Leaflet. Em cada busca, o serviço transforma o local informado em coordenadas, procura os pontos de coleta num retângulo em volta delas, mantém só os de Goiás que recebem entrega, filtra pelo material, calcula a distância pela fórmula de Haversine e devolve a lista ordenada em JSON, CSV ou PDF, usando um cache em SQLite para quando uma API cai e respondendo os erros no padrão RFC 7807.

Ou seja: o sistema é ao mesmo tempo **fornecedor e consumidor de web services**. Ele oferece uma API REST própria e, para responder, consulta três APIs REST públicas.

## 1. O que faz dele um web service

Um site comum entrega páginas para pessoas. Um web service entrega **dados para outros programas**, pela web, seguindo um contrato. No projeto, isso aparece assim:

- **Operações expostas por HTTP.** São 6 endereços em `/api`, chamados com `GET`:

| Endereço | O que devolve |
|---|---|
| `/api/pontos` | os pontos de coleta perto de um local ou ponto no mapa (JSON) |
| `/api/pontos.csv` | a mesma busca, em planilha |
| `/api/pontos.pdf` | a mesma busca, em relatório |
| `/api/municipios` | os municípios de Goiás (JSON) |
| `/api/materiais` | os materiais aceitos no filtro (JSON) |
| `/api/goias` | o contorno do estado (GeoJSON) |

- **Contrato publicado.** O FastAPI gera a especificação **OpenAPI** em `/openapi.json` a partir dos tipos do código e dos modelos em `app/rotas/schemas.py`, e a documentação interativa fica em `/docs`. O contrato diz os parâmetros de cada rota, o formato da resposta e o tipo de arquivo (JSON, CSV ou PDF). É o mesmo papel que o WSDL tem no SOAP.
- **Independente de quem chama.** A página é só um dos clientes. O mesmo endereço funciona no navegador, no curl, no Postman, no Excel (pelo CSV) ou em outro sistema:

  ```
  curl "http://127.0.0.1:8000/api/pontos?local=74230-010&raio_km=10"
  ```

- **Sem estado (stateless).** Cada requisição traz tudo de que precisa (local, raio e material), e o servidor não guarda sessão. O cache só evita repetir consultas externas e não muda a resposta.
- **HTTP usado de verdade:**
  - a URL identifica o recurso, e os parâmetros vão na query string;
  - os códigos de status têm significado: 200 (ok), 404 (local não encontrado), 422 (dado inválido ou fora de Goiás) e 503 (API externa fora do ar);
  - o tipo do conteúdo vai no cabeçalho: `application/json`, `text/csv`, `application/pdf` e `application/problem+json`.
- **Erros padronizados.** Todos seguem a RFC 7807 (Problem Details), um formato de erro que outro programa consegue ler.

Termo técnico útil para o relatório: é uma API **REST de nível 2 no modelo de Richardson**, porque usa recursos identificados por URL e os verbos e códigos do HTTP.

## 2. Os web services que ele consome

| API | O projeto envia | Recebe | Usa para |
|---|---|---|---|
| **IBGE Localidades** | pedido da lista de GO | 246 municípios com código e região | sugestões do campo e reconhecer nome de cidade |
| **IBGE Malhas** | código do estado (52) | contorno em GeoJSON | desenhar Goiás no mapa |
| **ViaCEP** | o CEP | rua, bairro, cidade e UF, sem coordenadas | entender o CEP e recusar CEP de fora de GO |
| **Nominatim** (OpenStreetMap) | endereço, texto ou coordenadas | lugares com latitude, longitude, estado e etiquetas | transformar endereço em coordenada, achar os pontos de reciclagem em volta e dizer se um clique é em Goiás |

Todas são REST e respondem em JSON. Nenhum dado de ponto fica guardado no código: tudo vem dessas consultas.

## 3. Um pedido do começo ao fim (busca por CEP)

1. A página chama `GET /api/pontos?local=74230-010&raio_km=10`.
2. O serviço pergunta ao **ViaCEP** o endereço do CEP.
3. Pergunta ao **Nominatim** as coordenadas da rua. Se ele não achar, tenta o bairro e depois a cidade.
4. Pergunta ao **Nominatim** os pontos de reciclagem num retângulo em volta dessas coordenadas, e os ecopontos do estado pelo nome.
5. Mantém só os pontos de Goiás que recebem entrega, filtra pelo material, calcula a distância em linha reta (Haversine) e ordena.
6. Devolve o JSON, e a página desenha a lista e o mapa. Os links de CSV e PDF repetem a mesma busca em outro formato.

**Sem nenhum ponto no raio**, a busca procura os 3 mais próximos aumentando a área aos poucos (50, 100 e 250 km) e juntando o que achou em cada uma. As áreas menores vêm primeiro porque, numa área grande, os muitos pontos do DF ocupam o limite de 50 resultados do Nominatim, e pontos de Goiás, mesmo perto, podem ficar de fora.

## 4. Como o código está organizado

```
app/
  rotas/      recebe a requisição, valida e responde em JSON, CSV ou PDF
  servicos/   as regras: de onde a pessoa busca e quais pontos mostrar
  apis/       um arquivo por API externa (IBGE, ViaCEP e Nominatim), todos passando pelo cache
```

Cada camada só chama a de baixo: as rotas chamam os serviços, os serviços chamam as APIs. A única exceção é o contorno de Goiás, que não tem regra nenhuma e vai do IBGE direto para a rota.

## 5. Robustez

- As respostas das APIs ficam num cache em SQLite: 30 dias para endereços e 1 dia para pontos.
- Se uma API cai, o sistema usa a última resposta guardada. Sem nada guardado, responde 503 dizendo qual API falhou.
- O projeto respeita as regras de uso do Nominatim: no máximo uma chamada por segundo e identificação da aplicação.
- Nomes vindos do mapa com caracteres que a fonte do PDF não tem (um emoji, por exemplo) viram "?" em vez de derrubar o relatório.
- Testes automatizados simulam as APIs, inclusive fora do ar, e rodam sem internet.

## 6. Conferência com o enunciado

| O enunciado pede | Situação |
|---|---|
| Implementar web services | ✓ API REST própria, com 6 operações e contrato OpenAPI |
| Uma aplicação que os consuma | ✓ a página só conversa com o `/api` |
| Gestão ambiental, em Goiás | ✓ destino correto de resíduos, só pontos de GO |
| Tratamento de erros | ✓ RFC 7807, códigos HTTP e tolerância a queda das APIs |
| Funções extras | ✓ mapa, clique no mapa, filtro de material e os mais próximos quando o raio está vazio |
| Relatórios adicionais | ✓ lista em CSV e relatório em PDF da busca |

## 7. Perguntas prováveis do professor

- **"Por que não SOAP?"** O enunciado não exige SOAP. REST com JSON é o padrão atual das APIs públicas, inclusive das três que o projeto consome. No capítulo de fundamentos vale comparar os dois: SOAP com XML e WSDL, REST com JSON e OpenAPI.
- **"Só tem GET?"** O serviço é de consulta, e REST não obriga ter todas as operações de cadastro (CRUD). `GET` é o verbo certo para leitura: não altera nada e pode ser guardado em cache.
- **"Os dados são confiáveis?"** Vêm do OpenStreetMap, que é colaborativo. Não existe API oficial com esses pontos em Goiás, e o sistema avisa para confirmar o ponto antes de ir.
- **"A distância é de carro?"** Não, é em linha reta (Haversine). O link "Como chegar" de cada ponto abre a rota real.
- **"O PDF comprova a destinação do resíduo?"** Não. Ele é um levantamento de opções, que pode apoiar o PGRS (Lei 12.305/2010) e o controle operacional da ISO 14001 (item 8.1). O comprovante de destinação é outro documento, e o próprio relatório avisa isso.
