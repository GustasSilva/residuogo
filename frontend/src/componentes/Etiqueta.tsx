/**
 * A etiqueta de status do manifesto, e a versão genérica usada em cadastros.
 *
 * Cada status tem a sua cor, definida em `estilos.css` pela classe
 * `etiqueta-<status em minúsculas>`. Cor é reforço, não a informação: o texto
 * do status está sempre escrito, para quem não distingue as cores e para a
 * leitura em impressão em preto e branco.
 */

import type { ReactNode } from "react";
import type { StatusManifesto } from "../api/tipos";
import { STATUS } from "../rotulos";

export function Etiqueta({ status }: { status: StatusManifesto }) {
  return (
    <span className={`etiqueta etiqueta-${status.toLowerCase()}`}>{STATUS[status]}</span>
  );
}

export function Marcador({
  tom = "neutra",
  children,
}: {
  tom?: "neutra" | "positiva" | "alerta" | "negativa";
  children: ReactNode;
}) {
  return <span className={`etiqueta etiqueta-${tom}`}>{children}</span>;
}
