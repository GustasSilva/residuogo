/**
 * As peças que todas as telas repetem: título, estados de carregamento e erro,
 * e paginação.
 *
 * Nada aqui tem lógica de negócio. A razão de existirem como componentes é que
 * "carregando" e "deu erro" apareceriam escritos de uma forma diferente em
 * cada tela — e o erro, em especial, precisa ser exibido sempre com a mesma
 * informação, inclusive o código técnico que o backend devolve.
 */

import type { ReactNode } from "react";
import type { ErroDaApi } from "../api/cliente";

export function TituloDaPagina({
  titulo,
  legenda,
  children,
}: {
  titulo: string;
  legenda?: string;
  /** Botões de ação da tela, alinhados à direita do título. */
  children?: ReactNode;
}) {
  return (
    <header className="cabecalho-da-pagina">
      <div>
        <h1>{titulo}</h1>
        {legenda !== undefined && <p className="legenda">{legenda}</p>}
      </div>
      {children !== undefined && <div className="acoes-da-pagina">{children}</div>}
    </header>
  );
}

export function Carregando({ texto = "Carregando…" }: { texto?: string }) {
  return <p className="carregando">{texto}</p>;
}

export function Vazio({ children }: { children: ReactNode }) {
  return <p className="vazio">{children}</p>;
}

/**
 * Um erro da API como o usuário o vê.
 *
 * Mostra a mensagem, os campos recusados que não pertencem a nenhum campo
 * visível do formulário e o `codigo` interno. O código é técnico de propósito:
 * é o que permite descrever o problema com precisão ao pedir ajuda, e junto
 * com o `X-Request-Id` do log do servidor identifica a requisição exata.
 */
export function AvisoDeErro({ erro }: { erro: ErroDaApi }) {
  return (
    <div className="aviso aviso-erro" role="alert">
      <div>{erro.message}</div>

      {erro.erros.length > 0 && (
        <ul>
          {erro.erros.map((campo) => (
            <li key={campo.campo}>
              <strong>{campo.campo}</strong>: {campo.mensagem}
            </li>
          ))}
        </ul>
      )}

      <div className="aviso-codigo">
        {erro.codigo}
        {erro.status > 0 && ` · HTTP ${erro.status}`}
      </div>
    </div>
  );
}

export function Paginacao({
  pagina,
  paginas,
  total,
  aoTrocar,
}: {
  pagina: number;
  paginas: number;
  total: number;
  aoTrocar: (pagina: number) => void;
}) {
  return (
    <div className="paginacao">
      <span>
        {total === 0
          ? "Nenhum registro"
          : `${total} ${total === 1 ? "registro" : "registros"} · página ${pagina} de ${paginas}`}
      </span>

      <div className="paginacao-botoes">
        <button
          type="button"
          className="botao"
          disabled={pagina <= 1}
          onClick={() => aoTrocar(pagina - 1)}
        >
          Anterior
        </button>
        <button
          type="button"
          className="botao"
          disabled={pagina >= paginas}
          onClick={() => aoTrocar(pagina + 1)}
        >
          Próxima
        </button>
      </div>
    </div>
  );
}
