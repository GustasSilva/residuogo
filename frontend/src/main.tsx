/**
 * Ponto de entrada do front-end: liga a aplicação React à página.
 *
 * `StrictMode` é um modo de desenvolvimento do React que monta cada componente
 * duas vezes para denunciar efeitos que não suportam ser repetidos. Fica
 * ligado de propósito: é ele que cobra o cancelamento das consultas em
 * `usarCarregamento`. Em produção o React o ignora.
 */

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./estilos.css";

const raiz = document.getElementById("root");
if (raiz === null) throw new Error('O elemento <div id="root"> não existe no index.html.');

createRoot(raiz).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
