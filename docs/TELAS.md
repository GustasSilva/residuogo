# Telas

## Tela inicial

O mapa já abre com o contorno de Goiás, que vem da API de malhas do IBGE. A pessoa digita um CEP, município, bairro ou endereço, ou clica no mapa. Ao digitar, o campo sugere os municípios de Goiás.

![Tela inicial](imagens/01-inicio.jpg)

## Resultado da busca

Pontos do mais perto para o mais longe, com o mesmo número na lista e no mapa. O título mostra o lugar que foi entendido. O círculo mostra a distância escolhida.

![Resultado da busca por bairro](imagens/02-resultado.jpg)

## Filtro por material e seleção de um ponto

Mudar o material refaz a busca. Com "Eletrônicos e eletrodomésticos", a central de embalagens de agrotóxicos sai da lista. Quem não informa os materiais continua aparecendo, com um aviso para confirmar antes de ir. Clicar no nome destaca o ponto na lista e no mapa.

![Filtro por material e ponto selecionado](imagens/03-filtro-e-selecao.jpg)

## Clique no mapa

Clicar no mapa procura a partir daquele lugar. Sem nenhum ponto na distância escolhida, a lista mostra os 3 mais próximos em até 250 km, com um aviso, e o mapa se ajusta para mostrar todos.

![Busca a partir de um clique no mapa](imagens/04-clique-no-mapa.jpg)

## Tratamento de erro

A mensagem de erro vem da API e diz o que fazer. A lista anterior continua na tela. No exemplo, um bairro de Brasília, que fica fora de Goiás.

![Local não encontrado em Goiás](imagens/05-erro.jpg)
