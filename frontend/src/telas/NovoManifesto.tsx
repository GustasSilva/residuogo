/**
 * Emissão de manifesto.
 *
 * Quem emite é o gerador, e não existe campo para informá-lo: o gerador é a
 * organização do usuário autenticado, decidido no servidor. Isso elimina por
 * construção a possibilidade de alguém emitir um manifesto em nome de outra
 * empresa.
 *
 * Os dois campos de participante são preenchidos com a lista de organizações
 * **aptas** — ativas, com o papel certo e com licença ambiental válida. A
 * consulta usa o filtro `apenas_aptas`, que no servidor reaproveita as mesmas
 * condições que a emissão aplica (RN04). É por isso que esta tela não
 * consegue oferecer um participante que a API depois recusaria: a lista e a
 * regra saem do mesmo lugar.
 */

import { useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ACONDICIONAMENTOS, api } from "../api/api";
import type { Acondicionamento, UnidadeMedida } from "../api/tipos";
import { Campo } from "../componentes/Campo";
import { AvisoDeErro, Carregando, TituloDaPagina } from "../componentes/Pagina";
import { ACONDICIONAMENTO, CLASSE_CURTA, UNIDADE } from "../rotulos";
import { usePapel } from "../sessao";
import { useAcao } from "../useAcao";
import { useCarregamento } from "../useCarregamento";

/** Um item enquanto está sendo digitado: tudo texto, como vem dos campos. */
interface ItemEmEdicao {
  tipo_residuo_id: string;
  quantidade: string;
  unidade: UnidadeMedida | "";
  acondicionamento: Acondicionamento;
}

const ITEM_VAZIO: ItemEmEdicao = {
  tipo_residuo_id: "",
  quantidade: "",
  unidade: "",
  acondicionamento: "TAMBOR",
};

const UNIDADES: UnidadeMedida[] = ["KG", "T", "L", "M3"];

export function NovoManifesto() {
  const papel = usePapel();
  const navegar = useNavigate();
  const acao = useAcao();

  const [transportador, setTransportador] = useState("");
  const [destinador, setDestinador] = useState("");
  const [observacoes, setObservacoes] = useState("");
  const [itens, setItens] = useState<ItemEmEdicao[]>([ITEM_VAZIO]);

  // Três listas independentes, buscadas em paralelo e esperadas juntas: a tela
  // não tem o que mostrar enquanto faltar qualquer uma delas.
  const catalogos = useCarregamento(async () => {
    const [transportadores, destinadores, tipos] = await Promise.all([
      api.organizacoesAptas("TRANSPORTADOR"),
      api.organizacoesAptas("DESTINADOR"),
      api.tiposDeResiduo(),
    ]);
    return { transportadores, destinadores, tipos };
  }, "");

  // Guardado em constante para que o TypeScript saiba, dentro dos laços mais
  // abaixo, que os catálogos já chegaram.
  const catalogo = catalogos.dado;

  function alterarItem(indice: number, mudanca: Partial<ItemEmEdicao>): void {
    setItens((atuais) =>
      atuais.map((item, posicao) => (posicao === indice ? { ...item, ...mudanca } : item)),
    );
  }

  /**
   * Ao escolher o resíduo, a unidade do catálogo é sugerida.
   *
   * Sugerida, e não imposta: o mesmo resíduo pode ser pesado em uma balança ou
   * medido em volume, dependendo de como foi acondicionado.
   */
  function escolherResiduo(indice: number, tipoId: string): void {
    const tipo = catalogo?.tipos.find((candidato) => String(candidato.id) === tipoId);
    alterarItem(indice, {
      tipo_residuo_id: tipoId,
      unidade: tipo?.unidade_padrao ?? "",
    });
  }

  async function emitir(evento: FormEvent): Promise<void> {
    evento.preventDefault();

    await acao.executar(async () => {
      const emitido = await api.emitirManifesto({
        transportador_id: Number(transportador),
        destinador_id: Number(destinador),
        observacoes: observacoes.trim() === "" ? null : observacoes.trim(),
        itens: itens.map((item) => ({
          tipo_residuo_id: Number(item.tipo_residuo_id),
          quantidade_declarada: Number(item.quantidade),
          unidade: item.unidade as UnidadeMedida,
          acondicionamento: item.acondicionamento,
        })),
      });

      // O manifesto recém-emitido é o documento que o gerador precisa ver
      // agora: dali ele imprime o PDF que acompanha a carga.
      navegar(`/manifestos/${emitido.id}`, { replace: true });
    });
  }

  if (papel !== "GERADOR") {
    return (
      <>
        <TituloDaPagina titulo="Emitir manifesto" />
        <div className="aviso aviso-info">
          Somente usuários de uma organização geradora emitem manifestos (regra RN01). O
          administrador supervisiona o sistema, mas não gera, transporta nem recebe carga.
        </div>
      </>
    );
  }

  return (
    <>
      <TituloDaPagina
        titulo="Emitir manifesto"
        legenda="O gerador é a sua organização. Informe quem transporta, quem recebe e quais resíduos seguem na carga."
      />

      {catalogos.carregando && <Carregando />}
      {catalogos.erro !== null && <AvisoDeErro erro={catalogos.erro} />}

      {catalogo !== null && (
        <form className="pilha" onSubmit={emitir}>
          <section className="cartao">
            <header>
              <h2>Participantes</h2>
              <span className="miudo">apenas organizações com licença válida</span>
            </header>
            <div className="cartao-corpo">
              <div className="grade duas">
                <Campo rotulo="Transportador" erro={acao.erro?.doCampo("transportador_id")}>
                  <select
                    value={transportador}
                    onChange={(evento) => setTransportador(evento.target.value)}
                    required
                  >
                    <option value="">Selecione…</option>
                    {catalogo.transportadores.map((organizacao) => (
                      <option key={organizacao.id} value={organizacao.id}>
                        {organizacao.razao_social} — {organizacao.municipio_nome}
                      </option>
                    ))}
                  </select>
                </Campo>

                <Campo rotulo="Destinador" erro={acao.erro?.doCampo("destinador_id")}>
                  <select
                    value={destinador}
                    onChange={(evento) => setDestinador(evento.target.value)}
                    required
                  >
                    <option value="">Selecione…</option>
                    {catalogo.destinadores.map((organizacao) => (
                      <option key={organizacao.id} value={organizacao.id}>
                        {organizacao.razao_social} — {organizacao.municipio_nome}
                      </option>
                    ))}
                  </select>
                </Campo>
              </div>
            </div>
          </section>

          <section className="cartao">
            <header>
              <h2>Resíduos</h2>
              <span className="miudo">ao menos um item, com quantidade maior que zero</span>
            </header>
            <div className="cartao-corpo">
              {itens.map((item, indice) => (
                <div className="item-do-manifesto" key={indice}>
                  <Campo
                    rotulo="Resíduo"
                    erro={acao.erro?.doCampo(`itens.${indice}.tipo_residuo_id`)}
                  >
                    <select
                      value={item.tipo_residuo_id}
                      onChange={(evento) => escolherResiduo(indice, evento.target.value)}
                      required
                    >
                      <option value="">Selecione…</option>
                      {catalogo.tipos.map((tipo) => (
                        <option key={tipo.id} value={tipo.id}>
                          {tipo.codigo} — {tipo.descricao} (classe {CLASSE_CURTA[tipo.classe]})
                        </option>
                      ))}
                    </select>
                  </Campo>

                  <Campo
                    rotulo="Quantidade"
                    erro={acao.erro?.doCampo(`itens.${indice}.quantidade_declarada`)}
                  >
                    <input
                      type="number"
                      step="any"
                      min="0.001"
                      value={item.quantidade}
                      onChange={(evento) => alterarItem(indice, { quantidade: evento.target.value })}
                      required
                    />
                  </Campo>

                  <Campo rotulo="Unidade" erro={acao.erro?.doCampo(`itens.${indice}.unidade`)}>
                    <select
                      value={item.unidade}
                      onChange={(evento) =>
                        alterarItem(indice, { unidade: evento.target.value as UnidadeMedida })
                      }
                      required
                    >
                      <option value="">—</option>
                      {UNIDADES.map((unidade) => (
                        <option key={unidade} value={unidade}>
                          {UNIDADE[unidade]}
                        </option>
                      ))}
                    </select>
                  </Campo>

                  <Campo rotulo="Acondicionamento">
                    <select
                      value={item.acondicionamento}
                      onChange={(evento) =>
                        alterarItem(indice, {
                          acondicionamento: evento.target.value as Acondicionamento,
                        })
                      }
                    >
                      {ACONDICIONAMENTOS.map((forma) => (
                        <option key={forma} value={forma}>
                          {ACONDICIONAMENTO[forma]}
                        </option>
                      ))}
                    </select>
                  </Campo>

                  <button
                    type="button"
                    className="remover-item"
                    title="Remover este resíduo"
                    // A regra RN08 exige ao menos um item: o último não sai.
                    disabled={itens.length === 1}
                    onClick={() =>
                      setItens((atuais) => atuais.filter((_, posicao) => posicao !== indice))
                    }
                  >
                    ×
                  </button>
                </div>
              ))}

              <button
                type="button"
                className="botao-texto"
                onClick={() => setItens((atuais) => [...atuais, ITEM_VAZIO])}
              >
                Adicionar resíduo
              </button>
            </div>
          </section>

          <section className="cartao">
            <header>
              <h2>Observações</h2>
            </header>
            <div className="cartao-corpo">
              <Campo
                rotulo="Informações complementares"
                ajuda="Opcional. Aparece no PDF que acompanha a carga."
                erro={acao.erro?.doCampo("observacoes")}
              >
                <textarea
                  value={observacoes}
                  onChange={(evento) => setObservacoes(evento.target.value)}
                  maxLength={1000}
                />
              </Campo>
            </div>
          </section>

          {acao.erro !== null && <AvisoDeErro erro={acao.erro} />}

          <div className="rodape-do-formulario">
            <button type="button" className="botao" onClick={() => navegar("/manifestos")}>
              Cancelar
            </button>
            <button type="submit" className="botao botao-principal" disabled={acao.executando}>
              {acao.executando ? "Emitindo…" : "Emitir manifesto"}
            </button>
          </div>
        </form>
      )}
    </>
  );
}
