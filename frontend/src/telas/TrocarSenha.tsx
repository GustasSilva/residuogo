/**
 * Troca da própria senha, disponível para qualquer usuário.
 *
 * O servidor exige a senha atual: sem ela, quem encontrasse a sessão aberta em
 * um computador poderia trocar a senha e tomar a conta.
 *
 * A confirmação da senha nova é conferida só aqui. Ela existe para pegar erro
 * de digitação, não é regra do sistema — por isso não vai para o servidor.
 */

import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../api/api";
import { Campo } from "../componentes/Campo";
import { AvisoDeErro, TituloDaPagina } from "../componentes/Pagina";
import { useAcao } from "../useAcao";

export function TrocarSenha() {
  const [senhaAtual, setSenhaAtual] = useState("");
  const [novaSenha, setNovaSenha] = useState("");
  const [confirmacao, setConfirmacao] = useState("");
  const [trocada, setTrocada] = useState(false);
  const envio = useAcao();

  const confirmacaoDiferente = confirmacao !== "" && confirmacao !== novaSenha;

  async function enviar(evento: FormEvent): Promise<void> {
    evento.preventDefault();
    setTrocada(false);

    const certo = await envio.executar(() =>
      api.trocarMinhaSenha({ senha_atual: senhaAtual, nova_senha: novaSenha }),
    );

    if (certo) {
      setTrocada(true);
      setSenhaAtual("");
      setNovaSenha("");
      setConfirmacao("");
    }
  }

  return (
    <>
      <TituloDaPagina
        titulo="Trocar senha"
        legenda="A sessão continua aberta; a senha nova vale a partir do próximo login."
      />

      <section className="cartao">
        <div className="cartao-corpo">
          <form className="pilha" onSubmit={enviar}>
            <div className="grade tres">
              <Campo rotulo="Senha atual" erro={envio.erro?.doCampo("senha_atual")}>
                <input
                  type="password"
                  value={senhaAtual}
                  onChange={(evento) => setSenhaAtual(evento.target.value)}
                  autoComplete="current-password"
                  required
                />
              </Campo>

              <Campo
                rotulo="Nova senha"
                ajuda="Mínimo de 8 caracteres."
                erro={envio.erro?.doCampo("nova_senha")}
              >
                <input
                  type="password"
                  value={novaSenha}
                  onChange={(evento) => setNovaSenha(evento.target.value)}
                  minLength={8}
                  maxLength={72}
                  autoComplete="new-password"
                  required
                />
              </Campo>

              <Campo
                rotulo="Repita a nova senha"
                erro={confirmacaoDiferente ? "As duas senhas não são iguais." : undefined}
              >
                <input
                  type="password"
                  value={confirmacao}
                  onChange={(evento) => setConfirmacao(evento.target.value)}
                  autoComplete="new-password"
                  required
                />
              </Campo>
            </div>

            {trocada && <div className="aviso aviso-sucesso">Senha trocada com sucesso.</div>}
            {envio.erro !== null && <AvisoDeErro erro={envio.erro} />}

            <div className="rodape-do-formulario">
              <button
                type="submit"
                className="botao botao-principal"
                disabled={envio.executando || confirmacaoDiferente}
              >
                {envio.executando ? "Salvando…" : "Trocar senha"}
              </button>
            </div>
          </form>
        </div>
      </section>
    </>
  );
}
