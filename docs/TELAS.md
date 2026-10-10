# Telas do sistema

As sete capturas em `imagens/`, feitas com o sistema rodando sobre os dados de
demonstração. Cada legenda abaixo pode ser usada como a legenda da figura no
trabalho escrito.

Os dados são fictícios, criados pela carga de demonstração (`scripts/seed.py`),
e as pessoas e empresas que aparecem não existem.

| Arquivo | Legenda sugerida |
|---|---|
| `tela-1-login.jpg` | Tela de entrada. Os acessos de demonstração listados abaixo do formulário existem para a apresentação: cada papel do ciclo do resíduo precisa ser demonstrado em sequência. |
| `tela-2-painel.jpg` | Painel inicial do administrador. Os números do mês, a série dos últimos seis meses, a taxa de desvio de aterro (78,2%) e os manifestos que aguardam ação vêm de uma única consulta ao servidor. |
| `tela-3-manifestos.jpg` | Listagem de manifestos com filtros por número, status, período e participante. O usuário comum vê apenas os manifestos da própria organização (regra RN07); o administrador vê todos. |
| `tela-4-detalhe-do-manifesto.jpg` | Detalhe de um manifesto em transporte, visto pelo destinador. O QR code impresso no documento abre esta mesma tela. O cartão "Conferir a carga" aparece porque o status e o papel do usuário permitem a ação (regra RN01). |
| `tela-5-emissao.jpg` | Emissão de um manifesto pelo gerador. A lista de transportadores traz apenas organizações com licença ambiental válida (regra RN04) — é por isso que a transportadora com licença vencida não aparece. A unidade é sugerida pelo catálogo de resíduos. |
| `tela-6-relatorios.jpg` | Relatório do período. Massa e volume aparecem em colunas separadas, porque somá-los exigiria arbitrar a densidade de cada resíduo. O total no rodapé é o mesmo nos três agrupamentos. |
| `tela-7-cadastro-de-organizacao.jpg` | Cadastro de organização. O CEP preencheu logradouro, bairro e município pela consulta ao ViaCEP; o município foi selecionado na lista oficial dos 246 municípios de Goiás, obtida da API do IBGE. |

## Como refazer as capturas

Com o backend e o front-end no ar (ver o README), abra <http://localhost:5173>,
entre com o acesso indicado na legenda e capture a janela do navegador. As
imagens atuais foram feitas em uma janela de 1920 × 889 pixels.

Para que os números batam com as legendas, carregue os dados de demonstração
antes: `python -m scripts.seed --recriar`. O sorteio usa semente fixa, então os
valores se repetem a cada execução.
