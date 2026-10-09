/**
 * Cadastro de usuários.
 *
 * O formulário reproduz na tela a regra que o schema do backend aplica: um
 * ADMIN não pertence a organização nenhuma, e um usuário comum precisa de uma.
 * Sem o vínculo não haveria como decidir o que ele pode fazer (RN01), e com o
 * vínculo um ADMIN pareceria operar em nome de uma empresa.
 *
 * Por isso o campo de organização é desabilitado — e limpo — quando o perfil
 * escolhido é ADMIN: a combinação impossível não chega a ser digitada.
 */

import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../../api/api";
import type { PerfilUsuario, UsuarioNovo } from "../../api/tipos";
import { Campo } from "../../componentes/Campo";
import { Marcador } from "../../componentes/Etiqueta";
import { AvisoDeErro, Carregando, Paginacao, Vazio } from "../../componentes/Pagina";
import { PERFIL } from "../../rotulos";
import { useAcao } from "../../useAcao";
import { useCarregamento } from "../../useCarregamento";

const VAZIO: UsuarioNovo = {
  nome: "",
  email: "",
  senha: "",
  perfil: "USUARIO",
  organizacao_id: null,
};

export function Usuarios() {
  const [pagina, setPagina] = useState(1);
  const [cadastrando, setCadastrando] = useState(false);
  const [recado, setRecado] = useState<string | null>(null);

  const lista = useCarregamento(() => api.listarUsuarios({ pagina }), String(pagina));
  // A lista de organizações é carregada uma vez e serve a duas coisas: mostrar
  // o nome da organização de cada usuário e preencher o campo do formulário.
  const organizacoes = useCarregamento(() => api.todasAsOrganizacoes(), "");

  function nomeDaOrganizacao(id: number | null): string {
    if (id === null) return "—";
    const encontrada = (organizacoes.dado ?? []).find((organizacao) => organizacao.id === id);
    return encontrada?.razao_social ?? `#${id}`;
  }

  return (
    <div className="pilha">
      <div className="rodape-do-formulario">
        <button
          type="button"
          className="botao botao-principal"
          onClick={() => {
            setCadastrando((atual) => !atual);
            setRecado(null);
          }}
        >
          {cadastrando ? "Fechar formulário" : "Novo usuário"}
        </button>
      </div>

      {recado !== null && <div className="aviso aviso-sucesso">{recado}</div>}

      {cadastrando && (
        <Formulario
          organizacoes={organizacoes.dado ?? []}
          aoCadastrar={(nome) => {
            setCadastrando(false);
            setRecado(`${nome} foi cadastrado.`);
            lista.recarregar();
          }}
        />
      )}

      <section className="cartao">
        {lista.carregando && <Carregando />}
        {lista.erro !== null && (
          <div className="cartao-corpo">
            <AvisoDeErro erro={lista.erro} />
          </div>
        )}

        {lista.dado !== null && lista.dado.itens.length === 0 && (
          <Vazio>Nenhum usuário cadastrado.</Vazio>
        )}

        {lista.dado !== null && lista.dado.itens.length > 0 && (
          <>
            <div className="rolagem-lateral">
              <table className="tabela">
                <thead>
                  <tr>
                    <th>Nome</th>
                    <th>E-mail</th>
                    <th>Perfil</th>
                    <th>Organização</th>
                    <th>Situação</th>
                  </tr>
                </thead>
                <tbody>
                  {lista.dado.itens.map((usuario) => (
                    <tr key={usuario.id}>
                      <td className="destaque">{usuario.nome}</td>
                      <td>{usuario.email}</td>
                      <td>{PERFIL[usuario.perfil]}</td>
                      <td>{nomeDaOrganizacao(usuario.organizacao_id)}</td>
                      <td>
                        {usuario.ativo ? (
                          <Marcador tom="positiva">Ativo</Marcador>
                        ) : (
                          <Marcador>Inativo</Marcador>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <Paginacao
              pagina={lista.dado.pagina}
              paginas={lista.dado.paginas}
              total={lista.dado.total}
              aoTrocar={setPagina}
            />
          </>
        )}
      </section>
    </div>
  );
}

function Formulario({
  organizacoes,
  aoCadastrar,
}: {
  organizacoes: { id: number; razao_social: string }[];
  aoCadastrar: (nome: string) => void;
}) {
  const [dados, setDados] = useState<UsuarioNovo>(VAZIO);
  const envio = useAcao();

  function escolherPerfil(perfil: PerfilUsuario): void {
    setDados((atuais) => ({
      ...atuais,
      perfil,
      // Trocar para ADMIN descarta o vínculo; o servidor recusaria os dois juntos.
      organizacao_id: perfil === "ADMIN" ? null : atuais.organizacao_id,
    }));
  }

  async function enviar(evento: FormEvent): Promise<void> {
    evento.preventDefault();
    const certo = await envio.executar(async () => {
      await api.criarUsuario(dados);
    });
    if (certo) aoCadastrar(dados.nome);
  }

  return (
    <section className="cartao">
      <header>
        <h2>Novo usuário</h2>
      </header>
      <div className="cartao-corpo">
        <form className="pilha" onSubmit={enviar}>
          <div className="grade duas">
            <Campo rotulo="Nome" erro={envio.erro?.doCampo("nome")}>
              <input
                value={dados.nome}
                onChange={(evento) => setDados((atuais) => ({ ...atuais, nome: evento.target.value }))}
                maxLength={120}
                required
              />
            </Campo>

            <Campo rotulo="E-mail" erro={envio.erro?.doCampo("email")}>
              <input
                type="email"
                value={dados.email}
                onChange={(evento) =>
                  setDados((atuais) => ({ ...atuais, email: evento.target.value }))
                }
                required
              />
            </Campo>
          </div>

          <div className="grade tres">
            <Campo
              rotulo="Senha"
              ajuda="Mínimo de 8 caracteres."
              erro={envio.erro?.doCampo("senha")}
            >
              <input
                type="password"
                value={dados.senha}
                onChange={(evento) =>
                  setDados((atuais) => ({ ...atuais, senha: evento.target.value }))
                }
                minLength={8}
                maxLength={72}
                required
              />
            </Campo>

            <Campo rotulo="Perfil" erro={envio.erro?.doCampo("perfil")}>
              <select
                value={dados.perfil}
                onChange={(evento) => escolherPerfil(evento.target.value as PerfilUsuario)}
              >
                <option value="USUARIO">{PERFIL.USUARIO}</option>
                <option value="ADMIN">{PERFIL.ADMIN}</option>
              </select>
            </Campo>

            <Campo
              rotulo="Organização"
              ajuda={
                dados.perfil === "ADMIN"
                  ? "O administrador não pertence a nenhuma organização."
                  : "Em nome de quem este usuário opera."
              }
              erro={envio.erro?.doCampo("organizacao_id") ?? envio.erro?.doCampo("(corpo)")}
            >
              <select
                value={dados.organizacao_id === null ? "" : String(dados.organizacao_id)}
                onChange={(evento) =>
                  setDados((atuais) => ({
                    ...atuais,
                    organizacao_id: evento.target.value === "" ? null : Number(evento.target.value),
                  }))
                }
                disabled={dados.perfil === "ADMIN"}
                required={dados.perfil === "USUARIO"}
              >
                <option value="">Selecione…</option>
                {organizacoes.map((organizacao) => (
                  <option key={organizacao.id} value={organizacao.id}>
                    {organizacao.razao_social}
                  </option>
                ))}
              </select>
            </Campo>
          </div>

          {envio.erro !== null && <AvisoDeErro erro={envio.erro} />}

          <div className="rodape-do-formulario">
            <button type="submit" className="botao botao-principal" disabled={envio.executando}>
              {envio.executando ? "Cadastrando…" : "Cadastrar usuário"}
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}
