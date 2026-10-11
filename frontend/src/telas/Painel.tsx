/**
 * Painel inicial.
 *
 * Tudo o que aparece aqui vem de **uma** requisição a `/dashboard/indicadores`.
 * Essa escolha é do backend e tem uma razão que a tela precisa respeitar: em
 * seis requisições separadas, cada bloco seria apurado em um instante
 * diferente, e o gráfico mostraria um período que o cartão ao lado não
 * confirma. Logo, esta tela não busca nada por conta própria.
 *
 * Os números já vêm limitados ao que o usuário pode ver (RN07): a organização
 * vê os seus manifestos, o administrador vê todos.
 */

import { Link } from "react-router-dom";
import { api, DESTINACOES_DE_RECUPERACAO } from "../api/api";
import type { Indicadores } from "../api/tipos";
import { Barras, Colunas, Proporcao } from "../componentes/Graficos";
import { Marcador } from "../componentes/Etiqueta";
import { AvisoDeErro, Carregando, TituloDaPagina, Vazio } from "../componentes/Pagina";
import { data, grandeza, inteiro, mesCurto, numero, percentual } from "../formatos";
import { PAPEL } from "../rotulos";
import { useSessao } from "../sessao";
import { useCarregamento } from "../useCarregamento";

export function Painel() {
  const { usuario } = useSessao();
  const { dado, carregando, erro } = useCarregamento(() => api.indicadores(), "");

  const abrangencia =
    usuario?.organizacao === null || usuario?.organizacao === undefined
      ? "todas as organizações"
      : usuario.organizacao.razao_social;

  return (
    <>
      <TituloDaPagina
        titulo="Painel"
        legenda={`Indicadores de ${abrangencia}, apurados em uma única consulta ao servidor.`}
      />

      {carregando && <Carregando />}
      {erro !== null && <AvisoDeErro erro={erro} />}
      {dado !== null && <Conteudo indicadores={dado} />}
    </>
  );
}

function Conteudo({ indicadores }: { indicadores: Indicadores }) {
  const { mes, desvio_de_aterro: desvio } = indicadores;
  const periodoDoMes = `${data(mes.inicio)} a ${data(mes.fim)}`;

  return (
    <div className="pilha">
      <div className="grade quatro">
        <Indicador
          rotulo="Massa destinada no mês"
          valor={grandeza(mes.massa_kg)}
          unidade="kg"
          nota={periodoDoMes}
        />
        <Indicador
          rotulo="Volume destinado no mês"
          valor={grandeza(mes.volume_m3)}
          unidade="m³"
          nota={periodoDoMes}
        />
        <Indicador
          rotulo="Manifestos emitidos"
          valor={inteiro(mes.manifestos_emitidos)}
          nota="no mês, em qualquer status"
        />
        <Indicador
          rotulo="Manifestos destinados"
          valor={inteiro(mes.manifestos_destinados)}
          nota="concluíram o ciclo no mês"
        />
      </div>

      <div className="grade larga-e-estreita">
        <section className="cartao">
          <header>
            <h2>Massa destinada por mês</h2>
            <span className="miudo">em kg</span>
          </header>
          <div className="cartao-corpo">
            <Colunas
              fatias={indicadores.serie_mensal.map((linha) => ({
                rotulo: mesCurto(linha.inicio),
                valor: linha.massa_kg,
                texto: grandeza(linha.massa_kg),
              }))}
            />
            <p className="nota">
              A última coluna é o mês corrente, ainda incompleto — por isso aparece destacada.
            </p>
          </div>
        </section>

        <section className="cartao">
          <header>
            <h2>Desvio de aterro</h2>
            <span className="miudo">{desvio.meses} meses</span>
          </header>
          <div className="cartao-corpo">
            <div className="indicador-valor grande">
              {percentual(desvio.percentual)}
            </div>

            {desvio.percentual === null ? (
              <p className="nota">
                Nada foi destinado no período. O indicador fica vazio em vez de zero: zero diria
                que nada foi recuperado, o que é diferente de não haver dado.
              </p>
            ) : (
              <>
                <Proporcao parte={desvio.massa_recuperada_kg} total={desvio.massa_total_kg} />
                <div className="legenda-do-grafico">
                  <span>
                    <i className="cor-recuperacao" />
                    Recuperada {grandeza(desvio.massa_recuperada_kg)} kg
                  </span>
                  <span>
                    <i className="cor-disposicao" />
                    Disposta{" "}
                    {grandeza(desvio.massa_total_kg - desvio.massa_recuperada_kg)} kg
                  </span>
                </div>
                <p className="nota">
                  Proporção da massa que voltou ao ciclo produtivo — reciclagem, compostagem e
                  coprocessamento — sobre a massa total destinada. É um indicador de massa: volume
                  não entra, porque converter um no outro exigiria arbitrar a densidade de cada
                  resíduo.
                </p>
              </>
            )}
          </div>
        </section>
      </div>

      <div className="grade larga-e-estreita">
        <section className="cartao">
          <header>
            <h2>Massa por destinação final</h2>
            <span className="miudo">em kg</span>
          </header>
          <div className="cartao-corpo">
            {indicadores.por_destinacao.length === 0 ? (
              <Vazio>Nenhum manifesto destinado nos últimos meses.</Vazio>
            ) : (
              <>
                <Barras
                  fatias={indicadores.por_destinacao.map((linha) => ({
                    rotulo: linha.rotulo,
                    valor: linha.massa_kg,
                    texto:
                      linha.volume_m3 > 0
                        ? `${grandeza(linha.massa_kg)} kg · ${numero(linha.volume_m3)} m³`
                        : `${grandeza(linha.massa_kg)} kg`,
                    disposicao: !DESTINACOES_DE_RECUPERACAO.includes(linha.chave),
                  }))}
                />
                <p className="nota">
                  A barra mede a massa. Onde houver volume, ele aparece ao lado, na sua própria
                  unidade: as duas grandezas não se somam.
                </p>
              </>
            )}
          </div>
        </section>

        <section className="cartao">
          <header>
            <h2>Aguardando ação</h2>
          </header>
          <div className="cartao-corpo">
            <div className="pilha">
              {indicadores.pendentes_por_status.map((pendencia) => (
                <Link
                  key={pendencia.status}
                  to={`/manifestos?status=${pendencia.status}`}
                  className="indicador pendencia"
                >
                  <div className="indicador-rotulo">{pendencia.rotulo}</div>
                  <div className="indicador-valor">{inteiro(pendencia.total)}</div>
                </Link>
              ))}
            </div>
            <p className="nota">
              Manifestos em estado não final. Clique para abrir a listagem já filtrada.
            </p>
          </div>
        </section>
      </div>

      <Licencas licencas={indicadores.licencas_a_vencer} />
    </div>
  );
}

function Indicador({
  rotulo,
  valor,
  unidade,
  nota,
}: {
  rotulo: string;
  valor: string;
  unidade?: string;
  nota: string;
}) {
  return (
    <div className="indicador">
      <div className="indicador-rotulo">{rotulo}</div>
      <div className="indicador-valor">
        {valor}
        {unidade !== undefined && <span className="unidade">{unidade}</span>}
      </div>
      <div className="indicador-nota">{nota}</div>
    </div>
  );
}

/**
 * Licenças ambientais vencidas ou a vencer nos próximos 30 dias.
 *
 * O alerta importa porque é a licença que autoriza o participante a operar: sem
 * licença válida, a regra RN04 recusa a emissão de novos manifestos. Quem vê
 * este aviso tem trinta dias para renovar antes de ficar impedido.
 *
 * O administrador recebe o atalho para o cadastro, onde a validade nova é
 * registrada e a organização volta a ser aceita na emissão.
 */
function Licencas({ licencas }: { licencas: Indicadores["licencas_a_vencer"] }) {
  const { usuario } = useSessao();

  return (
    <section className="cartao">
      <header>
        <h2>Licenças ambientais</h2>
        <span className="miudo">
          vencidas ou a vencer em 30 dias
          {usuario?.perfil === "ADMIN" && licencas.length > 0 && (
            <>
              {" · "}
              <Link to="/cadastros/organizacoes">renovar no cadastro</Link>
            </>
          )}
        </span>
      </header>

      {licencas.length === 0 ? (
        <div className="cartao-corpo">
          <Vazio>Nenhuma licença vence nos próximos 30 dias.</Vazio>
        </div>
      ) : (
        <div className="cartao-corpo sem-folga rolagem-lateral">
          <table className="tabela">
            <thead>
              <tr>
                <th>Organização</th>
                <th>Papel</th>
                <th>Licença</th>
                <th>Validade</th>
                <th>Situação</th>
              </tr>
            </thead>
            <tbody>
              {licencas.map((licenca) => (
                <tr key={licenca.organizacao_id}>
                  <td>{licenca.razao_social}</td>
                  <td>{PAPEL[licenca.papel]}</td>
                  <td>{licenca.licenca_numero}</td>
                  <td>{data(licenca.licenca_validade)}</td>
                  <td>
                    {licenca.vencida ? (
                      <Marcador tom="negativa">
                        Vencida há {Math.abs(licenca.dias_restantes)} dias
                      </Marcador>
                    ) : (
                      <Marcador tom="alerta">Vence em {licenca.dias_restantes} dias</Marcador>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
