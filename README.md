# ResíduoGO

Consulta de pontos de coleta de resíduos no estado de Goiás. A pessoa informa um CEP, escolhe um município ou clica no mapa, e vê os pontos mais próximos em uma lista e no mapa.

Trabalho de APS do curso de Ciência da Computação da UNIP. O enunciado pede web services ligados à gestão ambiental, dentro de Goiás, e uma aplicação que os consuma.

![Tela do ResíduoGO](docs/imagens/02-resultado.jpg)

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

Testado com Python 3.13. No PowerShell, a partir da raiz do projeto:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

- Página: http://127.0.0.1:8000
- Documentação da API: http://127.0.0.1:8000/docs

## Na página

- O CEP busca sozinho quando fica completo, e o município, ao ser escolhido.
- Clicar no mapa procura a partir daquele lugar, desde que seja dentro de Goiás.
- Mudar o material ou a distância refaz a busca atual.
- Passar o mouse em um ponto da lista destaca o ponto no mapa, e clicar em um marcador destaca o ponto na lista.
- "Limpar busca" volta a página ao início.

## API

| Rota | O que faz |
|---|---|
| `GET /api/pontos` | pontos perto de um CEP, município ou ponto no mapa |
| `GET /api/pontos.csv` | a mesma busca, em planilha |
| `GET /api/municipios` | municípios de Goiás, com a região |
| `GET /api/materiais` | materiais aceitos no filtro |
| `GET /api/goias` | contorno oficial de Goiás, em GeoJSON |

Parâmetros de `/api/pontos`: `cep`, `municipio` (código IBGE) ou `lat` e `lon`, mais `raio_km` (de 1 a 50, padrão 10) e `material`.

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
  "avisos": [],
  "fora_do_raio": false
}
```

Se não houver nenhum ponto no raio, a resposta traz os 3 mais próximos do estado, com `fora_do_raio` igual a `true`.

Os erros seguem a RFC 7807 e têm a mensagem em `detail`:

| Situação | Resposta |
|---|---|
| CEP, distância ou material inválido, CEP ou ponto fora de Goiás | 422 |
| CEP ou município que não existe | 404 |
| IBGE ou ViaCEP fora do ar, sem cache | 503 |

## Quando uma API externa cai

Os servidores públicos do Overpass ficam sobrecarregados com frequência, então a busca foi feita para continuar sem eles:

1. As respostas externas ficam guardadas em um cache em arquivo (`cache.db`). Buscas próximas aproveitam a mesma consulta.
2. A busca pergunta aos três servidores do Overpass ao mesmo tempo e espera até 8 segundos.
3. Se nenhum responder a tempo, usa a cópia dos dados de Goiás que fica no projeto e avisa na tela. Uma resposta atrasada ainda entra no cache, para a próxima busca.
4. Depois de uma falha, passa 2 minutos sem tentar o Overpass.
5. Sem o Nominatim, as distâncias contam a partir do centro do município, informado pelo IBGE.

Para atualizar a cópia, que fica em `dados/osm_goias.json`:

```
python -m scripts.atualizar_copia_osm
```

## De onde vêm os pontos

- **OpenStreetMap:** o mapa é aberto e feito por voluntários, então pode faltar ponto e a maioria não informa os materiais aceitos. Nesses casos, a tela mostra "Materiais aceitos não informados". Aterros e lixões ficam de fora, porque não recebem entrega de quem procura um ponto. As centrais de embalagens de agrotóxicos são reconhecidas pelo nome.
- **Ecopontos de Goiânia:** os cinco ecopontos permanentes ficam em `dados/ecopontos_goiania.json`. Não foi encontrada uma API oficial, então os dados vieram da [Prefeitura de Goiânia](http://gyncoletaseletiva.goiania.go.gov.br/ecoponto/) e da imprensa ([Tribuna do Planalto, 2024](https://tribunadoplanalto.com.br/prefeitura-disponibiliza-ecoponto-para-descarte-na-regiao-oeste/) e [Jornal Opção](https://www.jornalopcao.com.br/ultimas-noticias/entulho-moveis-e-pneus-goiania-podera-ampliar-rede-de-ecopontos-para-23-unidades-846959/)). Eles não foram conferidos um a um, e a página pede para confirmar o funcionamento antes de ir.

Só aparecem pontos dentro de Goiás, conferidos com o contorno oficial do estado, da API de malhas do IBGE (`dados/limite_goias.json`).

As cores dos materiais na tela seguem a Resolução CONAMA 275/2001. Os itens que ela não cobre aparecem em cinza.

## Relação com a gestão ambiental

Dar o destino correto aos resíduos é um dos controles mais comuns na gestão ambiental de uma organização, tema da família ISO 14000. O ResíduoGO ajuda empresas e moradores a encontrar onde entregar cada tipo de resíduo, e a exportação em CSV deixa a lista de opções registrada para quem cuida disso na organização.

## Testes

```
python -m pytest
```

Os testes não usam a internet: as APIs externas são simuladas.

## Estrutura

```
app/
  main.py          rotas do web service
  pontos.py        a busca: junta as fontes, filtra e ordena
  overpass.py      pontos do OpenStreetMap
  localizacao.py   CEP, municípios, coordenadas e limite de Goiás
  materiais.py     materiais e etiquetas do OpenStreetMap
  externo.py       chamadas HTTP e cache
  erros.py         respostas de erro (RFC 7807)
  schemas.py       formato das respostas
  config.py        endereços, prazos e tempos limite
web/               página (HTML, CSS e JavaScript)
dados/             ecopontos, cópia do OpenStreetMap e contorno de Goiás
scripts/           atualização da cópia e extração de trechos
tests/
docs/              diagramas, telas e trechos para o relatório
```

## Relatório da APS

O relatório de código tem limite de 10 páginas. Os trechos escolhidos são marcados no código com `APS-TRECHO` e reunidos em `docs/TRECHOS_DE_CODIGO.md`:

```
python -m scripts.exportar_trechos
```
