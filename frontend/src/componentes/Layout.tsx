/**
 * A moldura das telas autenticadas: barra lateral com a navegação, rodapé com
 * o usuário e a área de conteúdo, onde a rota atual é desenhada.
 *
 * A navegação é montada a partir de uma lista de itens, e cada item diz quem
 * pode vê-lo. Isso mantém em um lugar só a resposta para "quais telas este
 * usuário tem": sem a lista, a condição ficaria espalhada em `if`s pelo JSX, e
 * acrescentar uma tela exigiria lembrar de todos eles.
 *
 * Esconder um item é conveniência, não segurança — o servidor recusa a
 * operação de quem não pode executá-la, independentemente de a tela ter
 * oferecido o caminho.
 */

import { Link, Outlet, useLocation } from "react-router-dom";
import { PAPEL } from "../rotulos";
import { useSessao } from "../sessao";
import type { UsuarioLogado } from "../api/tipos";

interface ItemDeMenu {
  endereco: string;
  texto: string;
  grupo: "Operação" | "Gestão";
  /** Quem vê o item. Sem esta função, o item aparece para todos. */
  visivel?: (usuario: UsuarioLogado) => boolean;
  /** Em quais endereços o item deve aparecer como o atual. */
  atual: (caminho: string) => boolean;
}

const MENU: ItemDeMenu[] = [
  {
    endereco: "/",
    texto: "Painel",
    grupo: "Operação",
    atual: (caminho) => caminho === "/",
  },
  {
    endereco: "/manifestos",
    texto: "Manifestos",
    grupo: "Operação",
    // O detalhe de um manifesto também pertence à listagem, mas a emissão tem
    // item próprio no menu e não deve acender os dois.
    atual: (caminho) => caminho.startsWith("/manifestos") && caminho !== "/manifestos/novo",
  },
  {
    endereco: "/manifestos/novo",
    texto: "Emitir manifesto",
    grupo: "Operação",
    // Só o gerador emite (RN01), e o administrador não pertence a organização
    // nenhuma — para ele a tela não teria em nome de quem emitir.
    visivel: (usuario) => usuario.organizacao?.papel === "GERADOR",
    atual: (caminho) => caminho === "/manifestos/novo",
  },
  {
    endereco: "/relatorios",
    texto: "Relatórios",
    grupo: "Gestão",
    atual: (caminho) => caminho.startsWith("/relatorios"),
  },
  {
    endereco: "/cadastros",
    texto: "Cadastros",
    grupo: "Gestão",
    visivel: (usuario) => usuario.perfil === "ADMIN",
    atual: (caminho) => caminho.startsWith("/cadastros"),
  },
];

export function Layout() {
  const { usuario, sair } = useSessao();
  const { pathname } = useLocation();

  // A moldura só é desenhada dentro de uma rota protegida, que garante o
  // usuário carregado; a verificação existe para o TypeScript.
  if (usuario === null) return null;

  const itens = MENU.filter((item) => item.visivel === undefined || item.visivel(usuario));
  const grupos = ["Operação", "Gestão"] as const;

  return (
    <div className="aplicacao">
      <aside className="barra-lateral">
        <div className="marca">
          <div className="marca-nome">
            Resíduo<em>GO</em>
          </div>
          <div className="marca-legenda">Rastreamento de resíduos sólidos</div>
        </div>

        <nav className="navegacao">
          {grupos.map((grupo) => (
            <div key={grupo}>
              <div className="navegacao-grupo">{grupo}</div>
              {itens
                .filter((item) => item.grupo === grupo)
                .map((item) => (
                  <Link
                    key={item.endereco}
                    to={item.endereco}
                    className={item.atual(pathname) ? "ativo" : undefined}
                  >
                    {item.texto}
                  </Link>
                ))}
            </div>
          ))}
        </nav>

        <div className="usuario-atual">
          <div className="nome">{usuario.nome}</div>
          <div className="miudo">
            {usuario.organizacao === null
              ? "Acesso a todas as organizações"
              : `${usuario.organizacao.razao_social} · ${PAPEL[usuario.organizacao.papel]}`}
          </div>
          <button type="button" className="botao-texto" onClick={sair}>
            Sair
          </button>
        </div>
      </aside>

      <main className="conteudo">
        <Outlet />
      </main>
    </div>
  );
}
