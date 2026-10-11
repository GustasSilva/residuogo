/**
 * Catálogo de tipos de resíduo.
 *
 * É o cadastro que dá sentido aos relatórios: cada item de manifesto aponta
 * para um tipo daqui, com código, classe da NBR 10004 e unidade padrão. É
 * por isso que o resumo consegue agrupar por resíduo e por classe sem ter de
 * interpretar texto digitado por quem emitiu o manifesto.
 *
 * O catálogo é pequeno e não tem filtro: a listagem traz tudo de uma vez.
 *
 * O mesmo formulário serve ao cadastro e à correção. Na correção o código fica
 * travado: é ele que identifica o resíduo na Lista Brasileira.
 */

import { useState } from "react";
import type { FormEvent } from "react";
import { api } from "../../api/api";
import type { ClasseResiduo, TipoResiduo, TipoResiduoNovo, UnidadeMedida } from "../../api/tipos";
import { Campo } from "../../componentes/Campo";
import { AvisoDeErro, Carregando, Vazio } from "../../componentes/Pagina";
import { CLASSE, UNIDADE } from "../../rotulos";
import { useAcao } from "../../useAcao";
import { useCarregamento } from "../../useCarregamento";

const CLASSES: ClasseResiduo[] = ["I", "IIA", "IIB"];
const UNIDADES: UnidadeMedida[] = ["KG", "T", "L", "M3"];

const VAZIO: TipoResiduoNovo = {
  codigo: "",
  descricao: "",
  classe: "IIA",
  unidade_padrao: "KG",
};

export function TiposDeResiduo() {
  // O formulário pode estar fechado (null), cadastrando um tipo novo ("novo")
  // ou corrigindo um existente (o próprio tipo).
  const [formulario, setFormulario] = useState<TipoResiduo | "novo" | null>(null);
  const [recado, setRecado] = useState<string | null>(null);
  const lista = useCarregamento(() => api.tiposDeResiduo(), "");

  return (
    <div className="pilha">
      <div className="rodape-do-formulario">
        <button
          type="button"
          className="botao botao-principal"
          onClick={() => {
            setFormulario(formulario === null ? "novo" : null);
            setRecado(null);
          }}
        >
          {formulario === null ? "Novo tipo de resíduo" : "Fechar formulário"}
        </button>
      </div>

      {recado !== null && <div className="aviso aviso-sucesso">{recado}</div>}

      {formulario !== null && (
        <Formulario
          // A chave recria o formulário ao trocar de tipo, para que ele não
          // carregue os dados do anterior.
          key={formulario === "novo" ? "novo" : formulario.id}
          original={formulario === "novo" ? null : formulario}
          aoSalvar={(mensagem) => {
            setFormulario(null);
            setRecado(mensagem);
            lista.recarregar();
          }}
        />
      )}

      <section className="cartao">
        <header>
          <h2>Catálogo</h2>
          {lista.dado !== null && <span className="miudo">{lista.dado.length} tipos</span>}
        </header>

        {lista.carregando && <Carregando />}
        {lista.erro !== null && (
          <div className="cartao-corpo">
            <AvisoDeErro erro={lista.erro} />
          </div>
        )}

        {lista.dado !== null && lista.dado.length === 0 && (
          <Vazio>Nenhum tipo de resíduo cadastrado.</Vazio>
        )}

        {lista.dado !== null && lista.dado.length > 0 && (
          <div className="cartao-corpo sem-folga rolagem-lateral">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Código</th>
                  <th>Descrição</th>
                  <th>Classe</th>
                  <th>Unidade padrão</th>
                  <th aria-label="Ações" />
                </tr>
              </thead>
              <tbody>
                {lista.dado.map((tipo) => (
                  <tr key={tipo.id}>
                    <td className="destaque">{tipo.codigo}</td>
                    <td>{tipo.descricao}</td>
                    <td>{CLASSE[tipo.classe]}</td>
                    <td>{UNIDADE[tipo.unidade_padrao]}</td>
                    <td>
                      <button
                        type="button"
                        className="botao-texto"
                        onClick={() => {
                          setFormulario(tipo);
                          setRecado(null);
                          // O formulário fica no topo da página, acima da lista.
                          window.scrollTo({ top: 0, behavior: "smooth" });
                        }}
                      >
                        Corrigir
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

/**
 * Cadastro (sem `original`) ou correção (com o tipo a corrigir).
 */
function Formulario({
  original,
  aoSalvar,
}: {
  original: TipoResiduo | null;
  aoSalvar: (mensagem: string) => void;
}) {
  const corrigindo = original !== null;
  const [dados, setDados] = useState<TipoResiduoNovo>(
    original === null
      ? VAZIO
      : {
          codigo: original.codigo,
          descricao: original.descricao,
          classe: original.classe,
          unidade_padrao: original.unidade_padrao,
        },
  );
  const envio = useAcao();

  async function enviar(evento: FormEvent): Promise<void> {
    evento.preventDefault();
    const certo = await envio.executar(async () => {
      if (original === null) {
        await api.criarTipoDeResiduo(dados);
      } else {
        await api.corrigirTipoDeResiduo(original.id, {
          descricao: dados.descricao,
          classe: dados.classe,
          unidade_padrao: dados.unidade_padrao,
        });
      }
    });
    if (certo) {
      aoSalvar(`O tipo ${dados.codigo} foi ${corrigindo ? "corrigido" : "cadastrado"}.`);
    }
  }

  const rotuloDoBotao = corrigindo ? "Salvar correção" : "Cadastrar tipo";

  return (
    <section className="cartao">
      <header>
        <h2>{corrigindo ? "Corrigir tipo de resíduo" : "Novo tipo de resíduo"}</h2>
      </header>
      <div className="cartao-corpo">
        <form className="pilha" onSubmit={enviar}>
          <div className="grade duas">
            <Campo
              rotulo="Código"
              ajuda={
                corrigindo
                  ? "O código identifica o resíduo e não muda."
                  : "Código da Lista Brasileira de Resíduos."
              }
              erro={envio.erro?.doCampo("codigo")}
            >
              <input
                value={dados.codigo}
                onChange={(evento) =>
                  setDados((atuais) => ({ ...atuais, codigo: evento.target.value }))
                }
                maxLength={20}
                disabled={corrigindo}
                required
              />
            </Campo>

            <Campo rotulo="Descrição" erro={envio.erro?.doCampo("descricao")}>
              <input
                value={dados.descricao}
                onChange={(evento) =>
                  setDados((atuais) => ({ ...atuais, descricao: evento.target.value }))
                }
                maxLength={160}
                required
              />
            </Campo>
          </div>

          <div className="grade duas">
            <Campo
              rotulo="Classe (NBR 10004)"
              ajuda={
                corrigindo
                  ? "A classe corrigida vale também nos relatórios de meses anteriores."
                  : undefined
              }
              erro={envio.erro?.doCampo("classe")}
            >
              <select
                value={dados.classe}
                onChange={(evento) =>
                  setDados((atuais) => ({ ...atuais, classe: evento.target.value as ClasseResiduo }))
                }
              >
                {CLASSES.map((classe) => (
                  <option key={classe} value={classe}>
                    {CLASSE[classe]}
                  </option>
                ))}
              </select>
            </Campo>

            <Campo
              rotulo="Unidade padrão"
              ajuda="Sugerida na emissão do manifesto, e lá pode ser trocada."
              erro={envio.erro?.doCampo("unidade_padrao")}
            >
              <select
                value={dados.unidade_padrao}
                onChange={(evento) =>
                  setDados((atuais) => ({
                    ...atuais,
                    unidade_padrao: evento.target.value as UnidadeMedida,
                  }))
                }
              >
                {UNIDADES.map((unidade) => (
                  <option key={unidade} value={unidade}>
                    {UNIDADE[unidade]}
                  </option>
                ))}
              </select>
            </Campo>
          </div>

          {envio.erro !== null && <AvisoDeErro erro={envio.erro} />}

          <div className="rodape-do-formulario">
            <button type="submit" className="botao botao-principal" disabled={envio.executando}>
              {envio.executando ? "Salvando…" : rotuloDoBotao}
            </button>
          </div>
        </form>
      </div>
    </section>
  );
}
