/**
 * Listagem de manifestos, com filtros e exportação.
 *
 * Os filtros ficam no **endereço** da página, não em estado do componente.
 * Isso tem três consequências práticas: recarregar a página mantém o filtro,
 * o botão voltar do navegador funciona, e o painel pode apontar para
 * `/manifestos?status=EMITIDO` — que é exatamente como os cartões de pendência
 * levam até aqui.
 *
 * O formulário, por sua vez, não guarda estado nenhum: os campos nascem com o
 * valor que está no endereço (`defaultValue`) e, ao enviar, o endereço é
 * reescrito. A `key` do formulário muda junto com o endereço, de modo que uma
 * navegação externa — um link do painel, o botão voltar — recrie os campos com
 * os valores novos.
 *
 * A listagem já vem recortada pela regra RN07: o usuário comum vê apenas os
 * manifestos da própria organização.
 */

import { Link, useSearchParams } from "react-router-dom";
import { api, STATUS as STATUS_POSSIVEIS } from "../api/api";
import type { FiltrosDeManifesto } from "../api/api";
import type { StatusManifesto } from "../api/tipos";
import { Campo } from "../componentes/Campo";
import { Etiqueta } from "../componentes/Etiqueta";
import { AvisoDeErro, Carregando, Paginacao, TituloDaPagina, Vazio } from "../componentes/Pagina";
import { dataEHora } from "../formatos";
import { STATUS } from "../rotulos";
import { useAcao } from "../useAcao";
import { useCarregamento } from "../useCarregamento";
import type { FormEvent } from "react";

export function Manifestos() {
  const [parametros, setParametros] = useSearchParams();
  const exportacao = useAcao();

  // O endereço é a fonte da verdade dos filtros; aqui ele é apenas lido.
  const filtros: FiltrosDeManifesto = {
    status: (parametros.get("status") ?? "") as StatusManifesto | "",
    inicio: parametros.get("inicio") ?? "",
    fim: parametros.get("fim") ?? "",
    participante_id: parametros.get("participante_id") ?? "",
    numero: parametros.get("numero") ?? "",
    pagina: Number(parametros.get("pagina") ?? 1),
  };

  const endereco = parametros.toString();

  const { dado, carregando, erro } = useCarregamento(
    () => api.listarManifestos(filtros),
    // Qualquer mudança no endereço refaz a consulta — e só ela.
    endereco,
  );

  const organizacoes = useCarregamento(() => api.todasAsOrganizacoes(), "");

  function aplicarFiltros(evento: FormEvent<HTMLFormElement>): void {
    evento.preventDefault();

    const preenchidos: Record<string, string> = {};
    for (const [nome, valor] of new FormData(evento.currentTarget).entries()) {
      if (typeof valor === "string" && valor !== "") preenchidos[nome] = valor;
    }

    // Filtrar volta para a primeira página: o resultado é outro, e a página 3
    // do filtro anterior provavelmente não existe no novo.
    setParametros(preenchidos);
  }

  function irParaPagina(pagina: number): void {
    const novos = new URLSearchParams(parametros);
    novos.set("pagina", String(pagina));
    setParametros(novos);
  }

  return (
    <>
      <TituloDaPagina
        titulo="Manifestos"
        legenda="Documentos de transporte emitidos, em andamento e encerrados."
      >
        <button
          type="button"
          className="botao"
          disabled={exportacao.executando}
          onClick={() => exportacao.executar(() => api.exportarManifestosEmCsv(filtros))}
        >
          {exportacao.executando ? "Gerando…" : "Exportar CSV"}
        </button>
      </TituloDaPagina>

      <div className="pilha">
        <section className="cartao">
          <div className="cartao-corpo">
            <form className="filtros" onSubmit={aplicarFiltros} key={endereco}>
              <Campo rotulo="Número">
                <input name="numero" defaultValue={filtros.numero} placeholder="RGO-2026-" />
              </Campo>

              <Campo rotulo="Status">
                <select name="status" defaultValue={filtros.status}>
                  <option value="">Todos</option>
                  {STATUS_POSSIVEIS.map((status) => (
                    <option key={status} value={status}>
                      {STATUS[status]}
                    </option>
                  ))}
                </select>
              </Campo>

              <Campo rotulo="Emitido a partir de">
                <input type="date" name="inicio" defaultValue={filtros.inicio} />
              </Campo>

              <Campo rotulo="Emitido até">
                <input type="date" name="fim" defaultValue={filtros.fim} />
              </Campo>

              <Campo rotulo="Participante">
                <select name="participante_id" defaultValue={filtros.participante_id}>
                  <option value="">Qualquer</option>
                  {(organizacoes.dado ?? []).map((organizacao) => (
                    <option key={organizacao.id} value={organizacao.id}>
                      {organizacao.razao_social}
                    </option>
                  ))}
                </select>
              </Campo>

              <div className="rodape-do-formulario">
                {endereco !== "" && (
                  <button type="button" className="botao" onClick={() => setParametros({})}>
                    Limpar
                  </button>
                )}
                <button type="submit" className="botao botao-principal">
                  Filtrar
                </button>
              </div>
            </form>
          </div>
        </section>

        {exportacao.erro !== null && <AvisoDeErro erro={exportacao.erro} />}
        {erro !== null && <AvisoDeErro erro={erro} />}

        <section className="cartao">
          {carregando && <Carregando />}

          {dado !== null && dado.itens.length === 0 && (
            <Vazio>Nenhum manifesto encontrado com estes filtros.</Vazio>
          )}

          {dado !== null && dado.itens.length > 0 && (
            <>
              <div className="rolagem-lateral">
                <table className="tabela">
                  <thead>
                    <tr>
                      <th>Número</th>
                      <th>Status</th>
                      <th>Gerador</th>
                      <th>Transportador</th>
                      <th>Destinador</th>
                      <th>Emitido em</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dado.itens.map((manifesto) => (
                      <tr key={manifesto.id}>
                        <td>
                          <Link to={`/manifestos/${manifesto.id}`}>{manifesto.numero}</Link>
                        </td>
                        <td>
                          <Etiqueta status={manifesto.status} />
                        </td>
                        <td>{manifesto.gerador.razao_social}</td>
                        <td>{manifesto.transportador.razao_social}</td>
                        <td>{manifesto.destinador.razao_social}</td>
                        <td>{dataEHora(manifesto.emitido_em)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <Paginacao
                pagina={dado.pagina}
                paginas={dado.paginas}
                total={dado.total}
                aoTrocar={irParaPagina}
              />
            </>
          )}
        </section>
      </div>
    </>
  );
}
