/**
 * O hook das ações que mudam algo no servidor.
 *
 * Toda ação do sistema — emitir, confirmar coleta, cadastrar, exportar — tem o
 * mesmo ciclo: desabilitar o botão, chamar a API, e exibir o erro se vier um.
 * Deixar isso em cada tela significaria dois estados repetidos em mais de dez
 * lugares, com o risco clássico de esquecer de reabilitar o botão quando a
 * chamada falha (aqui, garantido pelo `finally`).
 *
 * `executar` devolve se a ação deu certo, o que permite à tela continuar o
 * trabalho — limpar o formulário, recarregar a lista, navegar — sem ter de
 * capturar o erro de novo.
 *
 * Sobre o nome em inglês: ver a explicação em `useCarregamento.ts`.
 */

import { useState } from "react";
import { comoErroDaApi } from "./api/cliente";
import type { ErroDaApi } from "./api/cliente";

export interface Acao {
  executar: (acao: () => Promise<void>) => Promise<boolean>;
  executando: boolean;
  erro: ErroDaApi | null;
}

export function useAcao(): Acao {
  const [executando, setExecutando] = useState(false);
  const [erro, setErro] = useState<ErroDaApi | null>(null);

  async function executar(acao: () => Promise<void>): Promise<boolean> {
    setExecutando(true);
    setErro(null);

    try {
      await acao();
      return true;
    } catch (falha) {
      setErro(comoErroDaApi(falha));
      return false;
    } finally {
      setExecutando(false);
    }
  }

  return { executar, executando, erro };
}
