/**
 * Um campo de formulário: rótulo, controle, texto de ajuda e erro.
 *
 * O controle vem como conteúdo (`children`) em vez de o componente escolher
 * entre `input`, `select` e `textarea` por propriedade. Assim o JSX da tela
 * continua mostrando o controle de verdade, com os seus próprios atributos,
 * e o componente cuida apenas do que é igual em todos: o rótulo associado, o
 * contorno vermelho quando o servidor recusa o valor e a mensagem embaixo.
 *
 * O controle fica **dentro** do `<label>`: é o que associa um ao outro sem
 * precisar inventar um `id` único para cada campo da tela. Clicar no rótulo
 * foca o campo, e o leitor de tela anuncia os dois juntos.
 */

import type { ReactNode } from "react";

export function Campo({
  rotulo,
  erro,
  ajuda,
  children,
}: {
  rotulo: string;
  /** Mensagem vinda de `erros[]` na resposta RFC 7807, quando houver. */
  erro?: string;
  ajuda?: string;
  children: ReactNode;
}) {
  return (
    <label className={erro === undefined ? "campo" : "campo com-erro"}>
      <span className="rotulo">{rotulo}</span>
      {children}
      {ajuda !== undefined && erro === undefined && <span className="ajuda-do-campo">{ajuda}</span>}
      {erro !== undefined && <span className="erro-do-campo">{erro}</span>}
    </label>
  );
}
