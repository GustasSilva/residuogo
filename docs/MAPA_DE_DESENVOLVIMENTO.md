# Mapa de desenvolvimento do ResíduoGO

Registro do que foi construído, por quê, e o que deu errado no caminho. Serve
de complemento ao trabalho escrito: o README descreve o sistema **pronto**,
este documento descreve as **decisões** que levaram a ele e os problemas que as
provocaram.

Cada decisão está escrita no formato contexto → decisão → consequência, porque
é a consequência que justifica a escolha em uma arguição. Os problemas estão
com sintoma, causa e correção, para que possam ser citados como evidência de
depuração e não apenas como anedota.

---

## 1. Linha do tempo

| Fase | Entrega | Commit | Situação |
|---|---|---|---|
| F1 | Base: modelos, autenticação JWT, erros RFC 7807, cadastros, `/health`, SOAP com WSDL e cliente `zeep` | `65d81b3` | concluída |
| F2 | Manifesto, itens, máquina de estados, histórico, regras RN01–RN08, seed com 40 manifestos | `8362570` | concluída |
| F3 | Integrações IBGE e ViaCEP, cache em memória, tratamento de indisponibilidade | `6f99b98` | concluída |
| F4 | PDF do manifesto com QR code, relatórios em PDF e CSV, painel de indicadores | `54d0881` | concluída |
| F5 | Front-end (React + Vite) | — | a fazer |
| F6 | Acabamento: README final, diagramas e prints em `docs/` | — | a fazer |

Contagem de testes ao fim de cada fase: F1 e F2, 140 testes; F3, 155 testes; F4, 183 testes.

**O SOAP foi construído na F1, e não na F3 como previa o escopo original.** Era
o ponto de maior risco técnico do projeto — a tecnologia menos usada hoje, com
menos material atualizado e nenhuma biblioteca viva em Python 3.13. Deixá-lo
para o meio do cronograma significaria descobrir o problema tarde. A decisão se
provou certa: o risco se materializou (ver problema 2.1) e foi resolvido com o
cronograma inteiro ainda disponível.

---

## 2. Decisões de arquitetura

### 2.1 SOAP escrito à mão, sem framework

**Contexto.** O trabalho exige um web service SOAP com WSDL. A biblioteca
padrão para isso em Python é o `spyne`, indicada no escopo original.

**O que aconteceu.** O `spyne` 2.14 não funciona em Python 3.13. Duas causas
independentes, ambas confirmadas no código da biblioteca:

- o `six` embutido nele chama `find_module`, removido do Python 3.12;
- `spyne/protocol/soap/soap11.py` e `spyne/server/wsgi.py` importam o módulo
  `cgi`, removido do Python 3.13.

**Decisão.** Escrever o envelope e o WSDL à mão: `lxml` para ler e montar o XML
e um WSDL 1.1 estático (document/literal), servidos como rotas comuns do
FastAPI. São cerca de 250 linhas em `app/soap/`.

**Consequência.** Nenhuma dependência extra, compatibilidade garantida com a
versão atual do Python e — o ganho que mais importa no contexto acadêmico —
cada parte do envelope e do contrato é explicável, porque foi escrita, não
gerada. O capítulo obrigatório de fundamentos de web services tem material
direto: `Envelope`, `Body`, `Fault`, namespace de serviço, `document/literal`.

**Não reverter.** Instalar o `spyne` de novo reintroduz a incompatibilidade.

### 2.2 Stack simples por decisão explícita

O escopo original previa Docker Compose, PostgreSQL e Alembic. Foram
descartados a pedido: o projeto deve ser simples e funcional, e o que é avaliado
são a API REST, o serviço SOAP e as regras de negócio.

| Previsto | Entregue | Por quê |
|---|---|---|
| PostgreSQL em contêiner | SQLite em arquivo | não exige servidor de banco instalado; o avaliador roda o projeto com um clone e um `pip install` |
| Alembic (migrações) | `create_all()` na subida | o banco é um arquivo descartável; migração só se justifica quando há dados em produção para preservar |
| Docker Compose | `venv` + `uvicorn` | menos uma camada entre o avaliador e o código |

**Consequência.** A troca para PostgreSQL continua sendo uma linha de
configuração (`database_url`), porque todo o acesso ao banco passa pelo
SQLAlchemy. O custo real da escolha é a ausência de histórico de migrações.

### 2.3 Datas sempre em UTC, garantido pelo tipo da coluna

**Contexto.** O SQLite não tem tipo nativo de data com fuso.

**O que foi medido.** Um script de teste gravou um `datetime` com fuso e o leu
de volta: voltou `tzinfo = None`. O banco aceita o valor e descarta
silenciosamente a informação de fuso — o pior tipo de falha, porque não dá erro.

**Decisão.** Um `TypeDecorator` chamado `DataHoraUTC` converte para UTC na
gravação e recoloca o fuso na leitura. Toda coluna de data e hora do sistema usa
esse tipo.

**Consequência.** Nenhum ponto do código precisa se lembrar de converter fuso:
é impossível gravar uma data sem fuso por esquecimento. O horário local aparece
apenas onde é parte da regra — o ano do número do manifesto e o período dos
relatórios — usando o fuso `America/Sao_Paulo`.

### 2.4 A máquina de estados é um dado, não uma sequência de condicionais

**Decisão.** As transições são declaradas em um dicionário que diz, para cada
estado, quais estados o sucedem e qual papel pode efetuar a mudança:

```python
TRANSICOES = {
    EMITIDO:       {EM_TRANSPORTE: TRANSPORTADOR, CANCELADO: GERADOR},
    EM_TRANSPORTE: {RECEBIDO: DESTINADOR, RECUSADO: DESTINADOR},
    RECEBIDO:      {DESTINADO: DESTINADOR},
}
```

**Consequência.** O diagrama de estados do trabalho escrito e o código são a
mesma informação, lida do mesmo lugar. Acrescentar uma transição é acrescentar
uma linha. Os estados finais são exatamente os que não aparecem como chave, sem
precisar de uma lista separada que poderia divergir.

Além disso, uma única função — `_aplicar_transicao` — é o único ponto do sistema
que atribui `manifesto.status`. É isso que faz as regras RN02 (transição válida)
e RN03 (gravar movimentação) valerem **sempre**, em vez de depender de cada rota
se lembrar delas.

### 2.5 Cada transição é um POST para um sub-recurso

**Alternativa descartada.** `PUT /manifestos/{id}` com o novo status no corpo.

**Decisão.** `POST /manifestos/{id}/coleta`, `/recebimento`, `/recusa`,
`/destinacao`, `/cancelamento`.

**Por quê.** O cliente descreve **o que aconteceu**; o servidor decide o status
resultante. Com o PUT, o cliente proporia o estado final e a máquina de estados
poderia ser contornada por uma requisição montada à mão. Também é o desenho que
permite que cada ação exija os seus próprios campos — placa e motorista na
coleta, quantidades no recebimento, motivo na recusa — o que seria impossível em
uma rota única.

### 2.6 Regras de negócio nos serviços, validação de formato nos schemas

Seis das oito regras ficam em `services/`; duas ficam nos schemas de entrada:

| Regra | Onde | Por quê |
|---|---|---|
| RN01 papel correto | `_exigir_papel` | depende do banco (quem participa do manifesto) |
| RN02 transição válida | `_aplicar_transicao` | depende do estado atual |
| RN03 histórico | `_aplicar_transicao` | precisa estar na mesma transação |
| RN04 participantes aptos | `emitir` | depende do cadastro e da data |
| RN05 divergência de 5% | `registrar_recebimento` | depende do valor declarado |
| RN06 motivo e destinação obrigatórios | schemas | é exigência de formato da requisição |
| RN07 visibilidade | `montar_consulta` | é um filtro aplicado em SQL |
| RN08 ao menos um item | schema `ManifestoCriar` | é exigência de formato da requisição |

**Consequência.** RN06 e RN08 validadas no schema devolvem o erro apontando o
campo exato, no formato RFC 7807, antes de qualquer acesso ao banco. As outras
seis não poderiam estar ali, porque dependem de informação que só o banco tem.

A regra prática é: o que está em `services/` é compartilhado por REST e SOAP. É
por isso que as duas interfaces têm exatamente o mesmo comportamento e diferem
apenas no formato da mensagem.

### 2.7 Um único formato de erro, inclusive para os erros do framework

**Decisão.** Toda resposta de erro segue a RFC 7807
(`application/problem+json`), com duas extensões próprias: `codigo`, para o
front-end reagir sem depender do texto, e `erros[]`, com `campo` e `mensagem`
para os erros de validação.

Quatro tradutores cobrem todas as origens possíveis de erro: exceções do
domínio, erros de validação do Pydantic, exceções do próprio framework (404 de
rota, 405 de método) e qualquer exceção não prevista.

**Consequência.** Não existe resposta de erro fora do padrão — nem as que o
framework levanta sozinho. O erro inesperado devolve uma mensagem genérica com
o identificador da requisição, sem rastro de pilha: detalhe técnico em resposta
de erro é informação útil para quem quer atacar o sistema. O diagnóstico
completo vai para o log, ligado ao mesmo identificador pelo cabeçalho
`X-Request-Id`.

### 2.8 A definição de "organização apta" existe em um só lugar

**Contexto.** A tela de novo manifesto precisa listar transportadores e
destinadores disponíveis; a emissão precisa recusar os inaptos (RN04). São o
mesmo critério aplicado em dois momentos.

**Decisão.** `services/organizacoes.py` expõe `condicoes_apta` (para usar em
SQL, na listagem) e `exigir_apta` (para aplicar a um objeto já carregado, na
emissão), derivadas da mesma definição.

**Consequência.** É impossível o front-end oferecer um participante que o
back-end depois recusaria. Duplicar a regra nos dois lugares seria o caminho
natural e produziria exatamente esse defeito.

### 2.9 O número do manifesto vem do id da linha

**Decisão.** `RGO-{ano}-{id:06d}`, com o ano no fuso local e o id da linha
preenchido com zeros.

**Por quê.** A alternativa é uma tabela de sequência por ano, que exige
controle de concorrência. Derivar do id dispensa esse controle: o próprio banco
garante a unicidade.

**Custo assumido.** A numeração não reinicia a cada ano. O manifesto
`RGO-2027-000500` pode ser o primeiro de 2027. Para o escopo do trabalho isso é
irrelevante; em um sistema sob norma legal, a numeração sequencial por exercício
poderia ser exigida, e aí a tabela de sequência se justificaria.

### 2.10 Cache em memória, não tabela

**Previsto no escopo.** Uma tabela `CacheExterno` com a última resposta válida
do IBGE e do ViaCEP.

**Decisão.** Cache em memória, com validade por entrada: 30 dias para a lista de
municípios, 7 dias para cada CEP.

**Por quê.** O volume é pequeno (246 municípios e os CEP consultados no dia) e o
dado é descartável: se o processo reiniciar, basta consultar de novo. Uma tabela
exigiria modelo, criação e limpeza para guardar o que não faz falta.

**Custo assumido, e declarado no código.** O cache não sobrevive a um reinício e
não é compartilhado entre vários processos do servidor. Em produção com várias
instâncias, cada uma teria o seu — o que torna o cache menos eficiente, mas não
incorreto.

**Detalhe técnico.** A validade usa `time.monotonic()`, que só anda para frente,
e não o relógio de parede: um ajuste de horário do sistema operacional faria o
cache vencer cedo ou tarde demais.

### 2.11 Falha de serviço externo não derruba tela nossa

A política está escrita **uma vez** em `integrations/externo.py` e é usada pelas
duas integrações, para que não possam divergir:

1. toda chamada tem tempo limite de 5 s;
2. falha de rede e erro 5xx são tentados mais uma vez; um 4xx não, porque a
   resposta seria a mesma;
3. a resposta boa vai para o cache;
4. se a API falhar, serve-se o último cache guardado, mesmo vencido;
5. só quando não há nada em cache o problema chega ao usuário, como
   `503 SERVICO_EXTERNO_INDISPONIVEL`.

O número de tentativas é deliberadamente baixo: com tempo limite de 5 s, duas
tentativas já podem fazer a rota levar 10 s. Insistir mais pioraria a espera de
quem está na tela em troca de uma chance pequena — o cache cobre melhor esse
caso.

Toda resposta informa a procedência do dado no cabeçalho `X-Fonte`: `api`
(consultado agora), `cache` (dentro da validade, sem chamar o terceiro) ou
`cache-expirado` (a API está fora do ar e este é o último dado que havia). O
escopo pedia apenas `cache`; os três valores permitem ao front-end avisar o
usuário de que o dado pode estar desatualizado.

### 2.12 "O CEP não existe" é 404; "o ViaCEP caiu" é 503

**Contexto.** As duas situações chegam ao código pelo mesmo caminho — uma
consulta que não produziu endereço.

**Decisão.** Um CEP inexistente levanta `RecursoNaoEncontrado` (404) e
**atravessa** o mecanismo de cache sem ser tratado. Só falha de comunicação
ativa o cache de reserva.

**Por quê.** O ViaCEP respondeu corretamente, e a resposta correta foi "não
existe". Servir cache nesse caso esconderia uma informação verdadeira. Também
não se guarda a resposta negativa: o CEP pode passar a existir.

**Particularidade do serviço.** O ViaCEP sinaliza o CEP inexistente com HTTP
**200** e `{"erro": "true"}` no corpo. Sem tratar isso explicitamente, o
endereço voltaria vazio e o usuário não saberia por quê.

### 2.13 `/health` não consulta serviços de terceiros

**Decisão.** A rota verifica o banco com a consulta mais barata possível
(`SELECT 1`) e informa **quantas** respostas externas estão em cache — sem
chamar o IBGE nem o ViaCEP.

**Por quê.** Um diagnóstico que chama terceiros faz a saúde da nossa aplicação
depender da saúde deles. Um balanceador de carga tiraria o sistema do ar por
causa de uma queda que não é nossa e que o cache já cobre.

**Como isso é provado.** No teste, apenas a rota de municípios está registrada
no simulador de HTTP. Se o `/health` tentasse consultar qualquer API externa, a
chamada não estaria simulada e o teste falharia. A resposta 200 é a prova.

### 2.14 Decisões menores, com motivo

| Decisão | Motivo |
|---|---|
| Enums gravados como texto com restrição `CHECK`, não como tipo nativo | o banco fica legível em qualquer ferramenta: a coluna mostra `EM_TRANSPORTE`, não um número |
| Quantidades em `Numeric(12, 3)` | resíduo é medido em kg, t, L e m³, com três casas; `float` acumularia erro de arredondamento em relatório somado |
| Custo do bcrypt configurável | o padrão 12 é o recomendado para uso real, e a suíte de testes o reduz (ver problema 3.7) |
| `qr_token` como UUID separado do id | quem recebe o QR code não precisa descobrir quantos manifestos existem no sistema |
| Identificadores do domínio em português sem acento | `manifesto`, `gerador`, `transportador` são o vocabulário do negócio; sem acento porque identificador acentuado é fonte de erro de codificação. Mensagens e textos para o usuário usam acento normalmente |
| `X-Request-Id` em toda resposta | quando um usuário relata um erro, esse código é o que permite achar a requisição exata no log |

---

## 3. Problemas e defeitos encontrados

### 3.1 O `spyne` não roda em Python 3.13

**Sintoma.** `ModuleNotFoundError: No module named 'spyne.util.six.moves'` na
importação.

**Causa.** Duas, independentes: o `six` embutido usa `find_module` (removido no
3.12) e dois módulos do `spyne` importam `cgi` (removido no 3.13).

**Correção.** SOAP escrito à mão (decisão 2.1). Esta é a mudança de maior
impacto em todo o projeto.

### 3.2 O SQLite descartava o fuso horário das datas

**Sintoma.** Datas gravadas com fuso voltavam da leitura sem fuso, sem erro.

**Causa.** O SQLite não tem tipo de data com fuso; o valor é convertido para
texto e a informação de fuso é perdida.

**Correção.** O `TypeDecorator` `DataHoraUTC` (decisão 2.3). Verificado com um
script dedicado antes de escrever o resto dos modelos.

### 3.3 Nenhum usuário do seed conseguia entrar

**Sintoma.** O cadastro dos usuários de demonstração falhava na validação de
e-mail: "The part after the @-sign is a special-use or reserved name".

**Causa.** O domínio escolhido era `@residuogo.test`, e `.test` é um domínio
reservado por norma (RFC 2606), recusado pela biblioteca de validação.

**Correção.** Domínio de demonstração trocado para `@residuogo.com.br` em todo
o projeto.

### 3.4 A API respondia em inglês nos erros do framework

**Sintoma.** Uma rota inexistente devolvia `detail: "Not Found"`, em inglês, no
meio de uma API em português.

**Causa.** Quando o framework levanta o erro por conta própria, ele usa a frase
padrão do código HTTP.

**Correção.** Uma tabela de tradução dos códigos comuns (401, 403, 404, 405,
422). O tradutor compara o texto recebido com a frase padrão do código e, se
forem iguais, substitui pela versão em português — assim uma mensagem específica
escrita por nós nunca é sobrescrita.

### 3.5 Cinquenta testes quebraram por causa do fuso horário

**Sintoma.** `ZoneInfoNotFoundError: 'No time zone found with key
America/Sao_Paulo'`.

**Causa.** O Windows não traz o banco de dados de fusos IANA que o `zoneinfo`
consulta. Em Linux e macOS o sistema já o fornece, e o problema não apareceria.

**Correção.** O pacote `tzdata` nas dependências, com comentário explicando
por que ele existe ali.

### 3.6 Erro de sessão ao imprimir o resumo do seed

**Sintoma.** `DetachedInstanceError` ao listar os usuários de cada organização.

**Causa.** O relacionamento `organizacao.usuarios` era acessado depois de a
sessão fechar. Por padrão, o SQLAlchemy busca um relacionamento apenas quando
ele é acessado, e fora da sessão essa busca é impossível.

**Correção.** Toda a impressão passou para dentro do bloco da sessão, e os
usuários são carregados junto das organizações com `selectinload`.

### 3.7 A suíte de testes levava 131 segundos

**Sintoma.** 140 testes em 131 s, sem nenhum teste lento isoladamente.

**Causa.** O custo 12 do bcrypt, aplicado em cada um dos muitos logins da suíte.
O custo alto é **desejável** em produção: cada unidade dobra o tempo de cálculo,
e é o que torna inviável testar senhas em massa.

**Correção.** O custo virou configuração (`bcrypt_custo`) e os testes o reduzem
para 4. A suíte caiu para 4,4 s. A configuração não existe só para o teste:
ajustar o custo do hash conforme o hardware é uma decisão real de produção.

### 3.8 O seed sobrescreveria as datas históricas dos manifestos

**Sintoma.** Encontrado em revisão, antes de rodar: os 40 manifestos
retroativos teriam todos a mesma data de atualização.

**Causa.** A coluna `atualizado_em` tem `onupdate`, que recalcula o valor em
qualquer UPDATE. O script grava o número do manifesto em um segundo passo —
UPDATE que acionaria o `onupdate` e apagaria a data histórica.

**Correção.** As datas de atualização são aplicadas no fim, com um UPDATE que
informa o valor explicitamente, o que desativa o `onupdate` daquela coluna.

### 3.9 Um teste afirmava a regra errada

**Sintoma.** O teste "transportadora de fora não confirma a coleta" esperava a
mensagem da RN01 ("não indicado neste manifesto") e recebia a da RN07 ("não
participa deste manifesto").

**Causa.** O comportamento estava correto: a visibilidade (RN07) é verificada
antes do papel (RN01), porque o manifesto é buscado antes de a ação ser
avaliada. A expectativa do teste é que estava errada.

**Correção.** Asserção e nome do teste ajustados para a regra que de fato atua.
Na mesma revisão, corrigi um comentário meu em `_exigir_papel` que afirmava mais
do que o código faz: a segunda condição não impede que qualquer transportadora
assuma qualquer carga — ela é uma rede de segurança, porque a RN07 já barrou
antes.

### 3.10 Quatro dos seis CEP do seed não existiam

**Sintoma.** Consultar o CEP de uma organização cadastrada pela própria rota do
sistema devolvia 404.

**Causa.** Os CEP do seed eram plausíveis, mas inventados. Isso era inofensivo
até a F3, quando o sistema passou a consultar o ViaCEP de verdade.

**Correção.** CEP reais das mesmas cidades, escolhidos para preservar o sentido
de cada endereço — o aterro de Catalão continua na BR-050, o frigorífico de Rio
Verde na GO-174, a cooperativa de Itumbiara ficou no distrito agroindustrial.
Conferidos um por um: os seis resolvem no sistema e devolvem exatamente o
logradouro, o bairro e o município gravados.

**Lição registrada.** Dado de demonstração inventado passa despercebido até o
sistema confrontá-lo com a realidade.

### 3.11 Cada consulta externa criava um cliente HTTP novo

**Sintoma.** A suíte saltou de 4,6 s para 9,7 s quando os 15 testes de
integração entraram, sem nenhum deles acessar a rede.

**Causa.** Não era o simulador de HTTP. Cada `httpx.Client()` monta um contexto
TLS e carrega a lista de autoridades certificadoras do sistema. Medido neste
ambiente: 0,25 s por cliente criado.

**Correção.** Um único cliente compartilhado pelo processo, fechado no
encerramento da aplicação. A suíte voltou a 4,4 s e uma consulta real caiu de
0,65 s para 0,14 s, porque o aperto de mão TLS também passou a ser reaproveitado.

**Observação.** A primeira versão do comentário no código afirmava o contrário —
que reaproveitar o cliente não valeria a complexidade. A medição desmentiu, e o
comentário foi corrigido para registrar os números.

### 3.12 Mensagens de validação com prefixo em inglês

**Sintoma.** O erro de campo chegava como "Value error, CEP deve ter 8 dígitos."

**Causa.** O Pydantic prefixa com `Value error, ` a mensagem de todo validador
próprio.

**Correção.** O prefixo é removido ao montar a lista `erros[]`. As mensagens já
estão escritas em português e vão direto para a tela.

---

## 4. Pontos que o escopo deixou abertos, e como foram fechados

O escopo original deixou quatro questões de projeto sem resposta. Todas foram
decididas e implementadas:

**Massa e volume não se somam.** Os relatórios separam kg, t, L e m³ em vez de
converter tudo para kg. Converter exigiria arbitrar uma densidade por tipo de
resíduo — um número inventado que contaminaria todos os indicadores. Preferi um
relatório com mais colunas e nenhum dado fabricado.

**A data de referência dos relatórios é `destinado_em`.** Um manifesto conta
para o mês em que a destinação foi informada, não em que foi emitido. É a data
em que o resíduo efetivamente teve um destino, que é o que o indicador ambiental
mede.

**Recuperação é reciclagem, compostagem e coprocessamento.** Disposição é aterro
e incineração. O indicador de desvio de aterro é a razão entre o primeiro grupo
e o total. O coprocessamento foi classificado como recuperação porque o resíduo
substitui matéria-prima ou combustível em vez de ser descartado.

**A numeração não reinicia por ano.** Decisão 2.9, com o custo declarado.

---

## 5. Como cada entrega foi verificada

Verificação é diferente de teste automatizado: os testes provam que o código
atende ao que se espera dele; a verificação confronta o sistema com o mundo.

| O que | Como |
|---|---|
| Serviço SOAP | consumido pelo cliente `zeep`, que lê o WSDL e monta a chamada sozinho — se o contrato estivesse mal formado, o cliente não geraria a chamada |
| Códigos IBGE dos municípios do seed | conferidos na API do IBGE, um por um, em vez de confiados à memória |
| CEP do seed | conferidos no ViaCEP pela própria rota do sistema, comparando campo a campo com o registro gravado |
| Fluxo completo do manifesto | execução de ponta a ponta contra o servidor no ar, com os três usuários, incluindo as recusas esperadas (transição inválida, estado final, falta de permissão) |
| Coerência dos 40 manifestos do seed | script dedicado: nenhum sem número, nenhum destinado sem tipo de destinação, nenhuma data fora de ordem, contagem de movimentações certa em todos |
| Cache das integrações | medido ao vivo: 2,19 s na primeira consulta de municípios, 0,003 s na segunda |
| Indisponibilidade das APIs externas | simulada nos testes: tempo limite, erro 500 seguido de sucesso, 4xx sem nova tentativa, formato de resposta alterado e queda total |

Dados gerados pelo seed, usados como referência dos relatórios: **63,9% de
desvio de aterro** e **16 de 57 itens** com divergência entre o declarado e o
recebido.

---

## 6. O que falta

**No código.** F4 (PDF do manifesto com QR code, relatórios em PDF e CSV,
dashboard de indicadores), F5 (front-end) e F6 (acabamento e insumos em
`docs/`).

**No trabalho escrito, fora do código.** A proposta de uma a duas páginas para
o coordenador auxiliar; a divisão do trabalho entre os três alunos; o capítulo
de 4 a 8 páginas sobre fundamentos de web services (sem dependência do código);
a dissertação sobre formação e interdisciplinaridade; a bibliografia; a ficha
cronológica da APS; e a confirmação das margens com o orientador.

**Sobre o relatório de código.** O limite é de 10 páginas em Arial 12 com
espaçamento 1,5, o que corresponde a cerca de 380 linhas. Por isso a convenção
de marcar no máximo seis trechos com `# APS-TRECHO`, escolhidos entre os mais
representativos: um endpoint, a máquina de estados, o tradutor de erros, o
serviço SOAP, o cliente `zeep` e a integração com cache.
