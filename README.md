# ResíduoGO

Consulta de pontos de coleta de resíduos no estado de Goiás. A pessoa informa um CEP ou um município, escolhe o material que vai descartar e vê os pontos mais próximos em uma lista e em um mapa.

Trabalho de APS do curso de Ciência da Computação da UNIP. O enunciado pede web services ligados à gestão ambiental, dentro de Goiás, e uma aplicação que os consuma.

## Como funciona

O projeto tem um web service REST próprio, que reúne dados de APIs externas, e uma página web que consome esse serviço.

| API externa | Para que é usada |
|---|---|
| IBGE Localidades | lista dos 246 municípios de Goiás e suas regiões |
| IBGE Malhas | centro do município, quando o Nominatim não responde |
| ViaCEP | endereço a partir do CEP |
| Nominatim (OpenStreetMap) | coordenadas do endereço |
| Overpass (OpenStreetMap) | pontos de coleta perto das coordenadas |

## Como rodar

Precisa de Python 3.12 ou mais novo.

```
cd backend
python -m venv .venv
.venv/Scripts/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

- Página: http://127.0.0.1:8000
- Documentação da API: http://127.0.0.1:8000/docs

## API

| Rota | O que faz |
|---|---|
| `GET /api/pontos` | pontos perto de um CEP ou município |
| `GET /api/pontos.csv` | a mesma busca, em planilha |
| `GET /api/municipios` | municípios de Goiás, com a região |
| `GET /api/materiais` | materiais aceitos no filtro |

Parâmetros de `/api/pontos`: `cep` ou `municipio` (código IBGE), `raio_km` (de 1 a 50, padrão 10) e `material`.

```
GET /api/pontos?cep=74230-010&raio_km=10&material=pneus
```

```json
{
  "origem": {
    "descricao": "Avenida T 15, Setor Bueno, Goiânia - GO",
    "latitude": -16.7068739,
    "longitude": -49.2742207,
    "precisao": "endereço"
  },
  "raio_km": 10,
  "material": "pneus",
  "total": 1,
  "pontos": [
    {
      "nome": "Ecoponto Faiçalville",
      "tipo": "Ecoponto",
      "distancia_km": 5.8,
      "materiais": [{ "chave": "pneus", "rotulo": "Pneus" }]
    }
  ],
  "avisos": []
}
```

Os erros seguem a RFC 7807 e têm a mensagem em `detail`:

| Situação | Resposta |
|---|---|
| CEP, distância ou material inválido, CEP de outro estado | 422 |
| CEP ou município que não existe | 404 |
| IBGE ou ViaCEP fora do ar, sem cache | 503 |

## Quando uma API externa cai

Os servidores públicos do Overpass ficam sobrecarregados com frequência, então a busca foi feita para continuar sem eles:

1. Toda resposta externa fica guardada em um cache em arquivo (`backend/cache.db`).
2. A busca pergunta aos três servidores do Overpass ao mesmo tempo, espera até 12 segundos e usa a primeira resposta.
3. Se nenhum responder, usa a última consulta guardada ou a cópia dos dados de Goiás que fica no projeto, e avisa na tela.
4. Depois de uma falha, passa 2 minutos sem tentar o Overpass, para ninguém esperar os 12 segundos de novo.
5. Sem o Nominatim, as distâncias contam a partir do centro do município, informado pelo IBGE.

Para atualizar a cópia, que fica em `backend/app/dados/osm_goias.json`:

```
cd backend
python -m scripts.atualizar_copia_osm
```

Para a apresentação, vale fazer antes as buscas que serão mostradas: elas ficam no cache e respondem na hora.

## De onde vêm os pontos

- **OpenStreetMap:** o mapa é aberto e feito por voluntários, então pode faltar ponto e a maioria não informa os materiais aceitos. Nesses casos, a tela mostra "Materiais aceitos não informados". Aterros e lixões ficam de fora, porque não recebem entrega de quem procura um ponto. As centrais de embalagens de agrotóxicos são reconhecidas pelo nome.
- **Ecopontos de Goiânia:** os cinco ecopontos permanentes ficam em `backend/app/dados/ecopontos_goiania.json`. Não foi encontrada uma API oficial, então os dados vieram da [Prefeitura de Goiânia](http://gyncoletaseletiva.goiania.go.gov.br/ecoponto/) e da imprensa ([Tribuna do Planalto, 2024](https://tribunadoplanalto.com.br/prefeitura-disponibiliza-ecoponto-para-descarte-na-regiao-oeste/) e [Jornal Opção](https://www.jornalopcao.com.br/ultimas-noticias/entulho-moveis-e-pneus-goiania-podera-ampliar-rede-de-ecopontos-para-23-unidades-846959/)).

As cores dos materiais na tela seguem a Resolução CONAMA 275/2001. Os itens que ela não cobre aparecem em cinza.

## Relação com a gestão ambiental

Dar o destino correto aos resíduos é um dos controles mais comuns na gestão ambiental de uma organização, tema da família ISO 14000. O ResíduoGO ajuda empresas e moradores a encontrar onde entregar cada tipo de resíduo, e a exportação em CSV deixa a lista de opções registrada para quem cuida disso na organização.

## Testes

```
cd backend
pip install -r requirements.txt
python -m pytest
```

Os testes não usam a internet: as APIs externas são simuladas. Cobrem a conversão dos dados, o filtro, as respostas de erro e as quedas de cada serviço.

## Estrutura

```
backend/
  app/
    main.py          rotas do web service
    localizacao.py   CEP, municípios e coordenadas
    pontos.py        busca dos pontos, distância e filtro
    materiais.py     materiais e etiquetas do OpenStreetMap
    externo.py       chamadas HTTP e política de cache
    cache.py         cache em SQLite
    errors.py        respostas de erro (RFC 7807)
    schemas.py       formato das respostas
    config.py        endereços, prazos e tempos limite
    dados/           ecopontos e cópia de reserva
    web/             página (HTML, CSS e JavaScript)
  scripts/           atualização da cópia e extração de trechos
  tests/
docs/                diagramas, telas e trechos para o relatório
```

## Relatório da APS

O relatório de código tem limite de 10 páginas. Os trechos escolhidos são marcados no código com `APS-TRECHO` e reunidos em `docs/TRECHOS_DE_CODIGO.md`:

```
cd backend
python -m scripts.exportar_trechos
```
