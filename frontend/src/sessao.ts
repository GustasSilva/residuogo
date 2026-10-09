/**
 * O que é a sessão do usuário e como as telas a consultam.
 *
 * O contexto e os dois hooks ficam aqui; o componente que monta a sessão está
 * em `ProvedorDeSessao.tsx`. A separação não é capricho: o recarregamento
 * instantâneo do Vite só funciona em arquivos que exportam apenas componentes,
 * então misturar o provedor com os hooks faria a aplicação inteira recarregar a
 * cada ajuste em qualquer um dos dois.
 *
 * O que vale repetir: o que se decide a partir daqui é **interface**. Esconder
 * um botão não protege nada — a autorização de verdade está no servidor, nas
 * regras RN01 e RN07, e ele recusa a operação mesmo que o botão apareça. O
 * papel desta camada é não oferecer ao usuário uma ação que ele não pode
 * executar.
 */

import { createContext, useContext } from "react";
import type { PapelOrganizacao, UsuarioLogado } from "./api/tipos";

export interface Sessao {
  usuario: UsuarioLogado | null;
  /** Verdadeiro enquanto o token guardado está sendo conferido no servidor. */
  conferindo: boolean;
  entrar: (email: string, senha: string) => Promise<void>;
  sair: () => void;
}

export const ContextoDeSessao = createContext<Sessao | null>(null);

export function useSessao(): Sessao {
  const sessao = useContext(ContextoDeSessao);
  if (sessao === null) {
    throw new Error("useSessao foi usado fora do ProvedorDeSessao.");
  }
  return sessao;
}

/**
 * O papel da organização do usuário, ou nulo para o administrador.
 *
 * O administrador não pertence a nenhuma organização, e é por isso que ele não
 * executa transição nenhuma (RN01): ele supervisiona o sistema inteiro, mas não
 * é gerador, transportador nem destinador de carga alguma.
 */
export function usePapel(): PapelOrganizacao | null {
  const { usuario } = useSessao();
  return usuario?.organizacao?.papel ?? null;
}
