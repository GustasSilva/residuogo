/**
 * Tela de login.
 *
 * O formulário manda e-mail e senha para `/auth/login` e guarda o token que
 * volta; daí em diante toda requisição o leva no cabeçalho `Authorization`.
 *
 * A lista de acessos de demonstração existe porque este é um sistema
 * acadêmico, apresentado com dados fictícios: os quatro papéis do ciclo do
 * resíduo precisam ser demonstrados em sequência, e digitar e-mail e senha a
 * cada troca de papel atrapalharia a apresentação. Em um sistema real ela não
 * existiria.
 */

import { useState } from "react";
import type { FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { comoErroDaApi } from "../api/cliente";
import type { ErroDaApi } from "../api/cliente";
import { Campo } from "../componentes/Campo";
import { AvisoDeErro } from "../componentes/Pagina";
import { useSessao } from "../sessao";

/** Os mesmos usuários criados pelo seed do backend (ver o README). */
const DEMONSTRACAO = [
  { papel: "Administrador", email: "admin@residuogo.com.br", senha: "admin12345" },
  { papel: "Gerador", email: "gerador1@residuogo.com.br", senha: "residuogo123" },
  { papel: "Transportador", email: "transportador1@residuogo.com.br", senha: "residuogo123" },
  { papel: "Destinador", email: "destinador1@residuogo.com.br", senha: "residuogo123" },
];

export function Entrar() {
  const { entrar } = useSessao();
  const navegar = useNavigate();
  const local = useLocation();

  const [email, setEmail] = useState("");
  const [senha, setSenha] = useState("");
  const [erro, setErro] = useState<ErroDaApi | null>(null);
  const [enviando, setEnviando] = useState(false);

  // Endereço que o usuário tentou abrir antes de ser desviado para cá.
  const destino = (local.state as { destino?: string } | null)?.destino ?? "/";

  async function enviar(evento: FormEvent): Promise<void> {
    evento.preventDefault();
    setEnviando(true);
    setErro(null);

    try {
      await entrar(email, senha);
      navegar(destino, { replace: true });
    } catch (falha) {
      setErro(comoErroDaApi(falha));
      setEnviando(false);
    }
  }

  return (
    <div className="entrada">
      <div className="entrada-coluna">
        <div className="entrada-topo">
          <div className="marca-nome">
            Resíduo<em>GO</em>
          </div>
          <div className="marca-legenda">
            Rastreamento de resíduos sólidos no estado de Goiás
          </div>
        </div>

        <div className="cartao">
          <div className="cartao-corpo">
            <form className="entrada-formulario" onSubmit={enviar}>
              <Campo rotulo="E-mail" erro={erro?.doCampo("email")}>
                <input
                  type="email"
                  value={email}
                  onChange={(evento) => setEmail(evento.target.value)}
                  autoComplete="username"
                  required
                  autoFocus
                />
              </Campo>

              <Campo rotulo="Senha" erro={erro?.doCampo("senha")}>
                <input
                  type="password"
                  value={senha}
                  onChange={(evento) => setSenha(evento.target.value)}
                  autoComplete="current-password"
                  required
                />
              </Campo>

              {erro !== null && <AvisoDeErro erro={erro} />}

              <button type="submit" className="botao botao-principal" disabled={enviando}>
                {enviando ? "Entrando…" : "Entrar"}
              </button>
            </form>
          </div>
        </div>

        <div className="cartao">
          <header>
            <h2>Acessos de demonstração</h2>
          </header>
          <div className="cartao-corpo">
            <div className="demonstracao">
              {DEMONSTRACAO.map((acesso) => (
                <button
                  key={acesso.email}
                  type="button"
                  onClick={() => {
                    setEmail(acesso.email);
                    setSenha(acesso.senha);
                  }}
                >
                  <span className="destaque">{acesso.papel}</span>
                  <span className="miudo">{acesso.email}</span>
                </button>
              ))}
            </div>
            <p className="nota">
              Clique em um papel para preencher o formulário. Os dados são fictícios, criados
              pela carga de demonstração.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
