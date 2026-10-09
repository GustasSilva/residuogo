/**
 * Moldura das três telas de cadastro.
 *
 * As abas são rotas de verdade, e não estado local: `/cadastros/usuarios` é um
 * endereço que pode ser recarregado e compartilhado, e o botão voltar do
 * navegador se comporta como o usuário espera.
 *
 * Todas as três exigem perfil ADMIN no servidor. O menu já esconde a seção de
 * quem não é administrador — mas é o servidor que recusa, não o menu.
 */

import { NavLink, Outlet } from "react-router-dom";
import { TituloDaPagina } from "../../componentes/Pagina";

const ABAS = [
  { endereco: "organizacoes", texto: "Organizações" },
  { endereco: "usuarios", texto: "Usuários" },
  { endereco: "tipos-residuo", texto: "Tipos de resíduo" },
];

export function Cadastros() {
  return (
    <>
      <TituloDaPagina
        titulo="Cadastros"
        legenda="Participantes do ciclo do resíduo, usuários do sistema e catálogo de resíduos."
      />

      <nav className="abas">
        {ABAS.map((aba) => (
          <NavLink
            key={aba.endereco}
            to={aba.endereco}
            className={({ isActive }) => (isActive ? "ativo" : undefined)}
          >
            {aba.texto}
          </NavLink>
        ))}
      </nav>

      <Outlet />
    </>
  );
}
