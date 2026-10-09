/**
 * O hook que carrega dados da API.
 *
 * Toda tela deste sistema faz a mesma coisa ao abrir: dispara uma consulta,
 * mostra "Carregando", e depois mostra o dado ou o erro. Escrito à mão em cada
 * tela, isso seriam três estados repetidos sete vezes — e, pior, a mesma
 * armadilha repetida sete vezes: a resposta que chega depois de o componente
 * ter saído da tela, ou depois de um filtro novo ter sido aplicado.
 *
 * A solução aqui é o resultado **guardar a qual consulta ele pertence**. Se a
 * chave gravada no resultado não é a chave atual, a tela ainda está
 * carregando — e não existe instante em que o resultado de um filtro apareça
 * como se fosse de outro. Isso também evita o estado "carregando" separado,
 * que precisaria ser ligado e desligado à mão em todos os caminhos.
 *
 * O nome começa com `use`, em inglês, apesar de todo o resto do código estar em
 * português: o prefixo faz parte do contrato do React. É por ele que as
 * ferramentas — o verificador de regras dos hooks, o depurador — reconhecem a
 * função como um hook e conferem se ela está sendo usada corretamente.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { comoErroDaApi } from "./api/cliente";
import type { ErroDaApi } from "./api/cliente";

export interface Carregamento<Dado> {
  dado: Dado | null;
  carregando: boolean;
  erro: ErroDaApi | null;
  /** Repete a consulta — usado depois de uma ação que muda o dado exibido. */
  recarregar: () => void;
}

/** O que voltou de uma consulta, junto com a identificação dela. */
interface Resultado<Dado> {
  chave: string;
  tentativa: number;
  dado: Dado | null;
  erro: ErroDaApi | null;
}

export function useCarregamento<Dado>(
  buscar: () => Promise<Dado>,
  /**
   * O que identifica esta consulta: quando a chave muda, consulta de novo.
   *
   * É um texto, e não uma lista de dependências como em `useEffect`, por dois
   * motivos: a tela costuma ter um único valor que define a consulta (o id da
   * rota, os filtros do endereço), e um texto pode ser conferido pelas
   * ferramentas de análise, que não conseguem verificar uma lista montada
   * dinamicamente. Uma consulta que roda só na abertura usa chave vazia.
   */
  chave: string,
): Carregamento<Dado> {
  const [resultado, setResultado] = useState<Resultado<Dado> | null>(null);
  // Mudar este número é o que força o efeito a rodar de novo em `recarregar`.
  const [tentativa, setTentativa] = useState(0);

  const recarregar = useCallback(() => setTentativa((anterior) => anterior + 1), []);

  // A função de busca é recriada a cada renderização, porque as telas a
  // escrevem no próprio JSX. Se ela entrasse na lista de dependências do
  // efeito, a consulta se repetiria indefinidamente; guardá-la em uma
  // referência deixa o efeito usar sempre a versão mais recente sem depender
  // da identidade dela.
  const buscarAtual = useRef(buscar);
  useEffect(() => {
    buscarAtual.current = buscar;
  });

  useEffect(() => {
    // `cancelado` cuida do componente que sai da tela antes da resposta:
    // guardar um resultado depois disso seria trabalho jogado fora.
    let cancelado = false;

    buscarAtual
      .current()
      .then((dado) => {
        if (!cancelado) setResultado({ chave, tentativa, dado, erro: null });
      })
      .catch((falha: unknown) => {
        if (!cancelado) {
          setResultado({ chave, tentativa, dado: null, erro: comoErroDaApi(falha) });
        }
      });

    return () => {
      cancelado = true;
    };
  }, [chave, tentativa]);

  // O resultado guardado responde à consulta atual? Enquanto não, a tela está
  // carregando — inclusive na primeira renderização, quando não há resultado.
  const atual =
    resultado !== null && resultado.chave === chave && resultado.tentativa === tentativa
      ? resultado
      : null;

  return {
    dado: atual?.dado ?? null,
    erro: atual?.erro ?? null,
    carregando: atual === null,
    recarregar,
  };
}
