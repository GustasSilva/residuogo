/**
 * Monta a sessão e a entrega às telas.
 *
 * Fica em contexto do React porque praticamente toda tela precisa do dado: a
 * navegação decide o que mostrar, as telas de manifesto decidem quais ações
 * oferecer, e a barra lateral mostra o nome. Passar isso por propriedade desde
 * a raiz atravessaria componentes que não têm nada a ver com autenticação.
 *
 * O contrato e os hooks de leitura estão em `sessao.ts`.
 */

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api } from "./api/api";
import { definirToken, quandoPerderSessao, temToken } from "./api/cliente";
import type { UsuarioLogado } from "./api/tipos";
import { ContextoDeSessao } from "./sessao";

export function ProvedorDeSessao({ children }: { children: ReactNode }) {
  const [usuario, setUsuario] = useState<UsuarioLogado | null>(null);
  // Só há o que conferir se existir um token guardado de uma visita anterior.
  const [conferindo, setConferindo] = useState(temToken());

  useEffect(() => {
    // O cliente HTTP avisa aqui quando o servidor recusa o token. Derrubar a
    // sessão é o suficiente: as rotas reagem à ausência de usuário e levam ao
    // login sozinhas.
    quandoPerderSessao(() => {
      definirToken(null);
      setUsuario(null);
    });
  }, []);

  useEffect(() => {
    if (!temToken()) return;

    // O token guardado pode ter expirado enquanto a aba estava fechada. A única
    // forma de saber é perguntar ao servidor — e é o que `/auth/me` responde.
    // Até a resposta chegar, a aplicação mostra "Carregando", em vez de piscar
    // a tela de login para quem já estava logado.
    let cancelado = false;

    api
      .eu()
      .then((encontrado) => {
        if (!cancelado) setUsuario(encontrado);
      })
      .catch(() => {
        definirToken(null);
      })
      .finally(() => {
        if (!cancelado) setConferindo(false);
      });

    return () => {
      cancelado = true;
    };
  }, []);

  async function entrar(email: string, senha: string): Promise<void> {
    const resposta = await api.entrar(email, senha);
    definirToken(resposta.token);

    // O login devolve só o token. Quem está por trás dele — perfil, papel da
    // organização — vem de `/auth/me`, a mesma rota usada ao recarregar a
    // página, de modo que exista um único caminho para montar a sessão.
    setUsuario(await api.eu());
  }

  function sair(): void {
    definirToken(null);
    setUsuario(null);
  }

  return (
    <ContextoDeSessao.Provider value={{ usuario, conferindo, entrar, sair }}>
      {children}
    </ContextoDeSessao.Provider>
  );
}
