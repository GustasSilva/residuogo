/**
 * As rotas da aplicação.
 *
 * A divisão é por sessão: sem usuário carregado, qualquer endereço leva ao
 * login; com usuário, as telas ficam dentro da moldura (`Layout`), que desenha
 * a barra lateral uma vez e troca apenas o conteúdo.
 *
 * O endereço pretendido é lembrado ao desviar para o login. É o que faz o QR
 * code do manifesto funcionar: quem aponta a câmera para a etiqueta cai em
 * `/qr/<token>`, faz o login e continua para o manifesto que queria ver, em
 * vez de ser largado no painel.
 */

import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Layout } from "./componentes/Layout";
import { Carregando } from "./componentes/Pagina";
import { ProvedorDeSessao } from "./ProvedorDeSessao";
import { useSessao } from "./sessao";
import { Cadastros } from "./telas/cadastros/Cadastros";
import { Organizacoes } from "./telas/cadastros/Organizacoes";
import { TiposDeResiduo } from "./telas/cadastros/TiposDeResiduo";
import { Usuarios } from "./telas/cadastros/Usuarios";
import { DetalheDoManifesto } from "./telas/DetalheDoManifesto";
import { Entrar } from "./telas/Entrar";
import { Manifestos } from "./telas/Manifestos";
import { NovoManifesto } from "./telas/NovoManifesto";
import { Painel } from "./telas/Painel";
import { Relatorios } from "./telas/Relatorios";
import { ResolverQr } from "./telas/ResolverQr";

export function App() {
  return (
    <BrowserRouter>
      <ProvedorDeSessao>
        <Rotas />
      </ProvedorDeSessao>
    </BrowserRouter>
  );
}

function Rotas() {
  const { usuario, conferindo } = useSessao();
  const local = useLocation();

  // Enquanto o token guardado está sendo conferido, nada é decidido: mostrar o
  // login aqui faria a tela piscar a cada recarga de quem já está logado.
  if (conferindo) return <Carregando />;

  if (usuario === null) {
    return (
      <Routes>
        <Route path="/entrar" element={<Entrar />} />
        <Route
          path="*"
          element={
            <Navigate to="/entrar" replace state={{ destino: local.pathname + local.search }} />
          }
        />
      </Routes>
    );
  }

  return (
    <Routes>
      {/* Já logado, o login não tem o que fazer. */}
      <Route path="/entrar" element={<Navigate to="/" replace />} />

      <Route element={<Layout />}>
        <Route path="/" element={<Painel />} />
        <Route path="/manifestos" element={<Manifestos />} />
        <Route path="/manifestos/novo" element={<NovoManifesto />} />
        <Route path="/manifestos/:id" element={<DetalheDoManifesto />} />
        <Route path="/qr/:token" element={<ResolverQr />} />
        <Route path="/relatorios" element={<Relatorios />} />

        <Route path="/cadastros" element={<Cadastros />}>
          <Route index element={<Navigate to="organizacoes" replace />} />
          <Route path="organizacoes" element={<Organizacoes />} />
          <Route path="usuarios" element={<Usuarios />} />
          <Route path="tipos-residuo" element={<TiposDeResiduo />} />
        </Route>

        <Route path="*" element={<NaoEncontrada />} />
      </Route>
    </Routes>
  );
}

function NaoEncontrada() {
  return (
    <div className="cartao">
      <div className="cartao-corpo">
        <h1>Endereço não encontrado</h1>
        <p className="legenda">
          A página que você tentou abrir não existe. <Link to="/">Voltar ao painel</Link>.
        </p>
      </div>
    </div>
  );
}
