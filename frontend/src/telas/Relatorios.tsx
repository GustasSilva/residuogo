/**
 * Relatório do período.
 *
 * Apura o que foi **destinado** no período, pela data da destinação: é quando
 * o resíduo efetivamente teve destino, e é o que o indicador ambiental mede.
 * Manifestos em trânsito ainda não produziram resultado e não entram.
 *
 * Massa e volume aparecem em colunas separadas, e uma das duas costuma ser
 * zero. Somá-las exigiria arbitrar a densidade de cada resíduo — o sistema não
 * inventa esse número. As únicas conversões feitas são exatas e dentro da
 * mesma grandeza: 1 t = 1000 kg, 1000 L = 1 m³.
 *
 * As três tabelas são o mesmo total repartido de três maneiras, e por isso
 * fecham no mesmo valor. O rodapé de cada uma mostra esse total: se um dos
 * agrupamentos divergisse — por uma junção que duplicasse linhas, por
 * exemplo — a diferença apareceria aqui.
 */

import { useState } from "react";
import type { FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/api";
import type { LinhaRelatorio, Resumo } from "../api/tipos";
import { Campo } from "../componentes/Campo";
import { AvisoDeErro, Carregando, TituloDaPagina, Vazio } from "../componentes/Pagina";
import { data, grandeza, inteiro, numero, percentual } from "../formatos";
import { useAcao } from "../useAcao";
import { useCarregamento } from "../useCarregamento";

export function Relatorios() {
  const [parametros, setParametros] = useSearchParams();
  const impressao = useAcao();

  const inicioEscolhido = parametros.get("inicio") ?? "";
  const fimEscolhido = parametros.get("fim") ?? "";

  const { dado, carregando, erro } = useCarregamento(
    () => api.resumo(inicioEscolhido, fimEscolhido),
    parametros.toString(),
  );

  // O que o usuário digitou nos campos de data, enquanto não aplica. Nulo
  // significa "não mexeu nos campos".
  const [digitado, setDigitado] = useState<{ inicio: string; fim: string } | null>(null);

  /*
   * O período exibido nos dois campos, decidido na própria renderização e não
   * por um efeito que copia um estado para o outro.
   *
   * A ordem de preferência resolve os três casos: o que está sendo digitado
   * vale mais que tudo; sem nada digitado, mostra-se o período que o servidor
   * apurou — importante porque, na primeira visita, nenhum período foi
   * informado e quem escolheu os seis meses padrão foi o backend; e, se a
   * consulta falhou, restam os valores do endereço, para que o usuário possa
   * corrigi-los (um período invertido, por exemplo).
   */
  const periodo =
    digitado ??
    (dado !== null
      ? { inicio: dado.inicio, fim: dado.fim }
      : { inicio: inicioEscolhido, fim: fimEscolhido });

  function alterar(mudanca: { inicio?: string; fim?: string }): void {
    setDigitado({ ...periodo, ...mudanca });
  }

  function aplicar(evento: FormEvent): void {
    evento.preventDefault();
    setParametros({ inicio: periodo.inicio, fim: periodo.fim });
    // O período volta a ser lido da resposta, que é a fonte do que está na tela.
    setDigitado(null);
  }

  return (
    <>
      <TituloDaPagina
        titulo="Relatórios"
        legenda="Resumo dos resíduos destinados no período, por tipo, classe e destinação final."
      >
        <button
          type="button"
          className="botao"
          disabled={impressao.executando || dado === null}
          onClick={() => {
            if (dado !== null) {
              impressao.executar(() => api.abrirPdfDoResumo(dado.inicio, dado.fim));
            }
          }}
        >
          {impressao.executando ? "Gerando…" : "Abrir PDF"}
        </button>
      </TituloDaPagina>

      <div className="pilha">
        <section className="cartao">
          <div className="cartao-corpo">
            <form className="filtros" onSubmit={aplicar}>
              <Campo rotulo="Início do período">
                <input
                  type="date"
                  value={periodo.inicio}
                  onChange={(evento) => alterar({ inicio: evento.target.value })}
                  required
                />
              </Campo>

              <Campo rotulo="Fim do período">
                <input
                  type="date"
                  value={periodo.fim}
                  onChange={(evento) => alterar({ fim: evento.target.value })}
                  required
                />
              </Campo>

              <div className="rodape-do-formulario">
                <button type="submit" className="botao botao-principal">
                  Aplicar
                </button>
              </div>
            </form>
          </div>
        </section>

        {carregando && <Carregando />}
        {erro !== null && <AvisoDeErro erro={erro} />}
        {dado !== null && <Apuracao resumo={dado} />}
      </div>
    </>
  );
}

function Apuracao({ resumo }: { resumo: Resumo }) {
  const { total, divergencias } = resumo;

  return (
    <>
      <div className="grade quatro">
        <div className="indicador">
          <div className="indicador-rotulo">Massa destinada</div>
          <div className="indicador-valor">
            {grandeza(total.massa_kg)}
            <span className="unidade">kg</span>
          </div>
          <div className="indicador-nota">
            {data(resumo.inicio)} a {data(resumo.fim)}
          </div>
        </div>

        <div className="indicador">
          <div className="indicador-rotulo">Volume destinado</div>
          <div className="indicador-valor">
            {grandeza(total.volume_m3)}
            <span className="unidade">m³</span>
          </div>
          <div className="indicador-nota">medido separadamente da massa</div>
        </div>

        <div className="indicador">
          <div className="indicador-rotulo">Manifestos destinados</div>
          <div className="indicador-valor">{inteiro(total.manifestos)}</div>
          <div className="indicador-nota">pela data da destinação</div>
        </div>

        <div className="indicador">
          <div className="indicador-rotulo">Itens divergentes</div>
          <div className="indicador-valor">{inteiro(divergencias.itens_divergentes)}</div>
          <div className="indicador-nota">
            de {inteiro(divergencias.itens_conferidos)} conferidos ·{" "}
            {percentual(divergencias.percentual)}
          </div>
        </div>
      </div>

      <Agrupamento
        titulo="Por tipo de resíduo"
        coluna="Resíduo"
        linhas={resumo.por_tipo}
        total={total}
      />
      <Agrupamento
        titulo="Por classe (NBR 10004)"
        coluna="Classe"
        linhas={resumo.por_classe}
        total={total}
      />
      <Agrupamento
        titulo="Por destinação final"
        coluna="Destinação"
        linhas={resumo.por_destinacao}
        total={total}
      />

      <p className="nota">
        A quantidade considerada é a recebida na conferência do destino; onde ela não existe, vale
        a declarada pelo gerador. As colunas “Manifestos” e “Itens” dizem de quantos documentos
        cada linha foi apurada.
      </p>
    </>
  );
}

function Agrupamento({
  titulo,
  coluna,
  linhas,
  total,
}: {
  titulo: string;
  coluna: string;
  linhas: LinhaRelatorio[];
  total: LinhaRelatorio;
}) {
  return (
    <section className="cartao">
      <header>
        <h2>{titulo}</h2>
      </header>

      {linhas.length === 0 ? (
        <Vazio>Nenhum manifesto destinado no período.</Vazio>
      ) : (
        <div className="cartao-corpo sem-folga rolagem-lateral">
          <table className="tabela">
            <thead>
              <tr>
                <th>{coluna}</th>
                <th className="numero">Massa (kg)</th>
                <th className="numero">Volume (m³)</th>
                <th className="numero">Manifestos</th>
                <th className="numero">Itens</th>
              </tr>
            </thead>
            <tbody>
              {linhas.map((linha) => (
                <tr key={linha.chave}>
                  <td>{linha.rotulo}</td>
                  <td className="numero">{numero(linha.massa_kg)}</td>
                  <td className="numero">{numero(linha.volume_m3)}</td>
                  <td className="numero">{inteiro(linha.manifestos)}</td>
                  <td className="numero">{inteiro(linha.itens)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr>
                <td>Total do período</td>
                <td className="numero">{numero(total.massa_kg)}</td>
                <td className="numero">{numero(total.volume_m3)}</td>
                <td className="numero">{inteiro(total.manifestos)}</td>
                <td className="numero">{inteiro(total.itens)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </section>
  );
}
