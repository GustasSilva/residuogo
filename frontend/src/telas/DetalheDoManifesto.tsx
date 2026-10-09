/**
 * Detalhe do manifesto: o documento na tela.
 *
 * Mostra o mesmo conteúdo do PDF que acompanha a carga — participantes,
 * resíduos, etapas e histórico — mais o painel de ações do usuário atual.
 *
 * O manifesto e o seu histórico são duas rotas, buscadas em paralelo e
 * recarregadas juntas depois de qualquer transição: o status novo e a linha do
 * tempo precisam aparecer no mesmo instante, ou a tela mostraria um manifesto
 * já recebido cujo histórico ainda termina na coleta.
 *
 * Abrir o manifesto já aplica a regra RN07: quem não participa dele recebe
 * 403, e é esse erro que esta tela exibe.
 */

import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/api";
import type { ItemManifesto, Manifesto, Movimentacao } from "../api/tipos";
import { Etiqueta, Marcador } from "../componentes/Etiqueta";
import { AvisoDeErro, Carregando, TituloDaPagina, Vazio } from "../componentes/Pagina";
import { cnpj, dataEHora, numero } from "../formatos";
import { ACONDICIONAMENTO, CLASSE_CURTA, DESTINACAO, PAPEL, STATUS, UNIDADE } from "../rotulos";
import { useAcao } from "../useAcao";
import { useCarregamento } from "../useCarregamento";
import { AcoesDoManifesto } from "./AcoesDoManifesto";

export function DetalheDoManifesto() {
  const { id } = useParams();
  const manifestoId = Number(id);
  const impressao = useAcao();

  const { dado, carregando, erro, recarregar } = useCarregamento(async () => {
    const [manifesto, historico] = await Promise.all([
      api.buscarManifesto(manifestoId),
      api.historicoDoManifesto(manifestoId),
    ]);
    return { manifesto, historico };
  }, String(manifestoId));

  if (carregando) return <Carregando />;
  if (erro !== null) return <AvisoDeErro erro={erro} />;
  if (dado === null) return null;

  const { manifesto, historico } = dado;

  return (
    <>
      <TituloDaPagina
        titulo={`Manifesto ${manifesto.numero}`}
        legenda={`Emitido em ${dataEHora(manifesto.emitido_em)} por ${manifesto.gerador.razao_social}`}
      >
        <Etiqueta status={manifesto.status} />
        <button
          type="button"
          className="botao"
          disabled={impressao.executando}
          onClick={() => impressao.executar(() => api.abrirPdfDoManifesto(manifesto))}
        >
          {impressao.executando ? "Gerando…" : "Abrir PDF"}
        </button>
      </TituloDaPagina>

      {impressao.erro !== null && <AvisoDeErro erro={impressao.erro} />}

      <div className="grade larga-e-estreita">
        <div className="pilha">
          <Etapas manifesto={manifesto} />
          <Residuos itens={manifesto.itens} />

          {manifesto.observacoes !== null && (
            <section className="cartao">
              <header>
                <h2>Observações</h2>
              </header>
              <div className="cartao-corpo">{manifesto.observacoes}</div>
            </section>
          )}

          {manifesto.motivo_recusa !== null && (
            <div className="aviso aviso-erro">
              <strong>Carga recusada.</strong> {manifesto.motivo_recusa}
            </div>
          )}

          <AcoesDoManifesto manifesto={manifesto} aoConcluir={recarregar} />
          <Historico movimentacoes={historico} />
        </div>

        <div className="pilha">
          <QrCode manifesto={manifesto} />
          <Participantes manifesto={manifesto} />
        </div>
      </div>
    </>
  );
}

/**
 * As quatro etapas do fluxo, com a data de cada uma.
 *
 * Etapa não cumprida aparece com um travessão, e não escondida: a sequência
 * vazia à frente é a informação de que o manifesto ainda está em curso.
 */
function Etapas({ manifesto }: { manifesto: Manifesto }) {
  return (
    <section className="cartao">
      <header>
        <h2>Transporte e destinação</h2>
        <span className="miudo">{STATUS[manifesto.status]}</span>
      </header>
      <div className="cartao-corpo">
        <dl className="dados">
          <div>
            <dt>Emissão</dt>
            <dd>{dataEHora(manifesto.emitido_em)}</dd>
          </div>
          <div>
            <dt>Coleta</dt>
            <dd>{dataEHora(manifesto.coletado_em)}</dd>
          </div>
          <div>
            <dt>Recebimento</dt>
            <dd>{dataEHora(manifesto.recebido_em)}</dd>
          </div>
          <div>
            <dt>Destinação</dt>
            <dd>{dataEHora(manifesto.destinado_em)}</dd>
          </div>
          <div>
            <dt>Veículo</dt>
            <dd>{manifesto.placa_veiculo ?? "—"}</dd>
          </div>
          <div>
            <dt>Motorista</dt>
            <dd>{manifesto.motorista_nome ?? "—"}</dd>
          </div>
          <div>
            <dt>Tratamento final</dt>
            <dd>
              {manifesto.tipo_destinacao === null
                ? "—"
                : DESTINACAO[manifesto.tipo_destinacao]}
            </dd>
          </div>
        </dl>
      </div>
    </section>
  );
}

function Residuos({ itens }: { itens: ItemManifesto[] }) {
  return (
    <section className="cartao">
      <header>
        <h2>Resíduos</h2>
        <span className="miudo">{itens.length === 1 ? "1 item" : `${itens.length} itens`}</span>
      </header>
      <div className="cartao-corpo sem-folga rolagem-lateral">
        <table className="tabela">
          <thead>
            <tr>
              <th>Resíduo</th>
              <th>Classe</th>
              <th>Acondicionamento</th>
              <th className="numero">Declarado</th>
              <th className="numero">Recebido</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {itens.map((item) => (
              <tr key={item.id}>
                <td>
                  <div className="destaque">{item.tipo_residuo.codigo}</div>
                  <div className="miudo">{item.tipo_residuo.descricao}</div>
                </td>
                <td>{CLASSE_CURTA[item.tipo_residuo.classe]}</td>
                <td>{ACONDICIONAMENTO[item.acondicionamento]}</td>
                <td className="numero">
                  {numero(item.quantidade_declarada)} {UNIDADE[item.unidade]}
                </td>
                <td className="numero">
                  {item.quantidade_recebida === null
                    ? "—"
                    : `${numero(item.quantidade_recebida)} ${UNIDADE[item.unidade]}`}
                </td>
                <td>{item.divergente && <Marcador tom="negativa">divergente</Marcador>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Participantes({ manifesto }: { manifesto: Manifesto }) {
  const papeis = [
    { papel: "GERADOR" as const, organizacao: manifesto.gerador },
    { papel: "TRANSPORTADOR" as const, organizacao: manifesto.transportador },
    { papel: "DESTINADOR" as const, organizacao: manifesto.destinador },
  ];

  return (
    <section className="cartao">
      <header>
        <h2>Participantes</h2>
      </header>
      <div className="cartao-corpo sem-folga">
        {papeis.map(({ papel, organizacao }) => (
          <div className="participante" key={papel}>
            <div className="participante-papel">{PAPEL[papel]}</div>
            <div className="destaque">{organizacao.razao_social}</div>
            <div className="miudo">
              CNPJ {cnpj(organizacao.cnpj)} · {organizacao.municipio_nome}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

/**
 * O QR code do manifesto.
 *
 * A imagem vem da API, que a gera a partir do `qr_token` — um identificador
 * aleatório, e não o id do manifesto: uma etiqueta com `/manifestos/41` diria
 * quantos manifestos existem no sistema e convidaria a tentar o 42.
 *
 * Como a rota exige autenticação, a imagem é buscada por requisição e exibida
 * a partir da memória do navegador. Esse endereço temporário precisa ser
 * liberado quando a tela sai, ou o conteúdo fica preso na memória da aba até
 * ela ser fechada.
 */
function QrCode({ manifesto }: { manifesto: Manifesto }) {
  const [endereco, setEndereco] = useState<string | null>(null);

  useEffect(() => {
    let cancelado = false;
    let criado: string | null = null;

    api
      .imagemDoQrCode(manifesto.id)
      .then((url) => {
        criado = url;
        if (cancelado) {
          URL.revokeObjectURL(url);
          return;
        }
        setEndereco(url);
      })
      .catch(() => {
        // Sem o QR code a tela continua útil; o erro não merece interromper.
      });

    return () => {
      cancelado = true;
      if (criado !== null) URL.revokeObjectURL(criado);
    };
  }, [manifesto.id]);

  return (
    <section className="cartao">
      <header>
        <h2>QR code</h2>
      </header>
      <div className="cartao-corpo">
        <div className="qr-do-manifesto">
          {endereco === null ? (
            <Carregando texto="Gerando imagem…" />
          ) : (
            <img src={endereco} alt={`QR code do manifesto ${manifesto.numero}`} />
          )}
          <p className="miudo">
            Impresso no documento, abre este manifesto na tela. É assim que o destinador lança o
            recebimento sem digitar o número.
          </p>
        </div>
      </div>
    </section>
  );
}

/**
 * A linha do tempo das movimentações.
 *
 * Vem da tabela que só recebe inserções: cada transição grava uma linha com o
 * autor e o instante (RN03). É a parte do documento que serve à auditoria —
 * responde quem mudou o que, e quando.
 */
function Historico({ movimentacoes }: { movimentacoes: Movimentacao[] }) {
  return (
    <section className="cartao">
      <header>
        <h2>Histórico</h2>
        <span className="miudo">{movimentacoes.length} movimentações</span>
      </header>
      <div className="cartao-corpo">
        {movimentacoes.length === 0 ? (
          <Vazio>Nenhuma movimentação registrada.</Vazio>
        ) : (
          <ol className="linha-do-tempo">
            {movimentacoes.map((movimentacao) => (
              <li key={movimentacao.id}>
                <div>
                  <div className="passo-titulo">
                    {movimentacao.status_anterior === null
                      ? `Emissão · ${STATUS[movimentacao.status_novo]}`
                      : `${STATUS[movimentacao.status_anterior]} → ${STATUS[movimentacao.status_novo]}`}
                  </div>
                  <div className="miudo">
                    {dataEHora(movimentacao.data_hora)} · {movimentacao.usuario.nome}
                  </div>
                  {movimentacao.observacao !== null && (
                    <div className="miudo">{movimentacao.observacao}</div>
                  )}
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
