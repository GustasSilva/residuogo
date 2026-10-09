/**
 * As ações que movem o manifesto de um estado para o outro.
 *
 * Cada ação é um POST para um sub-recurso que nomeia o evento — `/coleta`,
 * `/recebimento`, `/recusa`, `/destinacao`, `/cancelamento`. A tela conta o
 * que aconteceu; quem decide o status resultante é o servidor. Não existe aqui
 * nenhum campo "novo status", e é de propósito: a máquina de estados do
 * backend não pode ser contornada pela interface.
 *
 * Qual formulário aparece depende de duas coisas — o status atual e quem está
 * olhando. As duas condições são as mesmas que a regra RN01 aplica no
 * servidor: a organização precisa ter o papel da ação **e** ser a indicada
 * naquele manifesto. Comparar o id da organização, e não apenas o papel,
 * mantém o paralelo exato com a regra.
 *
 * Esconder um botão é conveniência, não autorização: se a requisição for
 * enviada de qualquer outra forma, o servidor a recusa igual.
 */

import { useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { api, DESTINACOES } from "../api/api";
import type { Manifesto, TipoDestinacao } from "../api/tipos";
import { Campo } from "../componentes/Campo";
import { AvisoDeErro } from "../componentes/Pagina";
import { numero } from "../formatos";
import { DESTINACAO, UNIDADE } from "../rotulos";
import { useSessao } from "../sessao";
import { useAcao } from "../useAcao";

/** De quem é a próxima ação em cada estado não final, para explicar a espera. */
const RESPONSAVEL_PELA_PROXIMA_ACAO: Record<string, string> = {
  EMITIDO: "do transportador, que confirma a coleta",
  EM_TRANSPORTE: "do destinador, que recebe ou recusa a carga",
  RECEBIDO: "do destinador, que informa a destinação final",
};

export function AcoesDoManifesto({
  manifesto,
  aoConcluir,
}: {
  manifesto: Manifesto;
  /** Chamado depois de uma transição: a tela recarrega manifesto e histórico. */
  aoConcluir: () => void;
}) {
  const { usuario } = useSessao();
  const minhaOrganizacao = usuario?.organizacao?.id ?? null;

  const souGerador = minhaOrganizacao === manifesto.gerador.id;
  const souTransportador = minhaOrganizacao === manifesto.transportador.id;
  const souDestinador = minhaOrganizacao === manifesto.destinador.id;

  const formularios: ReactNode[] = [];

  if (manifesto.status === "EMITIDO" && souTransportador) {
    formularios.push(<Coleta key="coleta" manifesto={manifesto} aoConcluir={aoConcluir} />);
  }

  if (manifesto.status === "EMITIDO" && souGerador) {
    formularios.push(
      <Cancelamento key="cancelamento" manifesto={manifesto} aoConcluir={aoConcluir} />,
    );
  }

  if (manifesto.status === "EM_TRANSPORTE" && souDestinador) {
    formularios.push(
      <Conferencia key="conferencia" manifesto={manifesto} aoConcluir={aoConcluir} />,
    );
  }

  if (manifesto.status === "RECEBIDO" && souDestinador) {
    formularios.push(
      <Destinacao key="destinacao" manifesto={manifesto} aoConcluir={aoConcluir} />,
    );
  }

  if (formularios.length > 0) return <>{formularios}</>;

  // Sem ação disponível, dizer o motivo é mais útil que não mostrar nada.
  const espera = RESPONSAVEL_PELA_PROXIMA_ACAO[manifesto.status];

  return (
    <section className="cartao">
      <header>
        <h2>Ações</h2>
      </header>
      <div className="cartao-corpo">
        <p className="legenda">
          {espera === undefined
            ? "Este manifesto está encerrado: não há mais transições possíveis."
            : minhaOrganizacao === null
              ? `A próxima ação é ${espera}. O administrador acompanha o manifesto, mas não executa transições (RN01).`
              : `Aguardando a ação ${espera}.`}
        </p>
      </div>
    </section>
  );
}

function CartaoDeAcao({
  titulo,
  descricao,
  children,
}: {
  titulo: string;
  descricao: string;
  children: ReactNode;
}) {
  return (
    <section className="cartao">
      <header>
        <h2>{titulo}</h2>
      </header>
      <div className="cartao-corpo">
        <p className="legenda">{descricao}</p>
        {children}
      </div>
    </section>
  );
}

interface PropsDeAcao {
  manifesto: Manifesto;
  aoConcluir: () => void;
}

/** EMITIDO → EM_TRANSPORTE. Registra veículo e motorista. */
function Coleta({ manifesto, aoConcluir }: PropsDeAcao) {
  const acao = useAcao();
  const [placa, setPlaca] = useState("");
  const [motorista, setMotorista] = useState("");
  const [observacao, setObservacao] = useState("");

  async function enviar(evento: FormEvent): Promise<void> {
    evento.preventDefault();
    const certo = await acao.executar(async () => {
      await api.confirmarColeta(manifesto.id, {
        placa_veiculo: placa.trim().toUpperCase(),
        motorista_nome: motorista.trim(),
        observacao: observacao.trim() === "" ? null : observacao.trim(),
      });
    });
    if (certo) aoConcluir();
  }

  return (
    <CartaoDeAcao
      titulo="Confirmar coleta"
      descricao="A carga saiu do gerador. Informe o veículo e o motorista responsáveis pelo transporte."
    >
      <form className="pilha" onSubmit={enviar}>
        <div className="grade duas">
          <Campo
            rotulo="Placa do veículo"
            erro={acao.erro?.doCampo("placa_veiculo")}
            ajuda="Sete caracteres, com ou sem hífen."
          >
            <input
              value={placa}
              onChange={(evento) => setPlaca(evento.target.value)}
              maxLength={10}
              required
            />
          </Campo>

          <Campo rotulo="Motorista" erro={acao.erro?.doCampo("motorista_nome")}>
            <input
              value={motorista}
              onChange={(evento) => setMotorista(evento.target.value)}
              maxLength={120}
              required
            />
          </Campo>
        </div>

        <Campo rotulo="Observação" ajuda="Opcional." erro={acao.erro?.doCampo("observacao")}>
          <textarea
            value={observacao}
            onChange={(evento) => setObservacao(evento.target.value)}
            maxLength={500}
          />
        </Campo>

        {acao.erro !== null && <AvisoDeErro erro={acao.erro} />}

        <div className="rodape-do-formulario">
          <button type="submit" className="botao botao-principal" disabled={acao.executando}>
            {acao.executando ? "Registrando…" : "Confirmar coleta"}
          </button>
        </div>
      </form>
    </CartaoDeAcao>
  );
}

/**
 * EM_TRANSPORTE → RECEBIDO ou RECUSADO.
 *
 * As duas saídas ficam no mesmo cartão porque são a mesma decisão tomada na
 * portaria do destino: conferir e aceitar, ou recusar a carga. O destinador
 * escolhe uma das duas antes de ver o formulário correspondente — sem isso,
 * dois formulários abertos lado a lado convidariam ao clique errado.
 */
function Conferencia({ manifesto, aoConcluir }: PropsDeAcao) {
  const [escolha, setEscolha] = useState<"receber" | "recusar" | null>(null);

  return (
    <CartaoDeAcao
      titulo="Conferir a carga"
      descricao="A carga chegou ao destino. Confira as quantidades e registre o recebimento, ou recuse a carga informando o motivo."
    >
      {escolha === null && (
        <div className="rodape-do-formulario">
          <button type="button" className="botao botao-perigo" onClick={() => setEscolha("recusar")}>
            Recusar a carga
          </button>
          <button
            type="button"
            className="botao botao-principal"
            onClick={() => setEscolha("receber")}
          >
            Registrar recebimento
          </button>
        </div>
      )}

      {escolha === "receber" && (
        <Recebimento
          manifesto={manifesto}
          aoConcluir={aoConcluir}
          aoVoltar={() => setEscolha(null)}
        />
      )}

      {escolha === "recusar" && (
        <Recusa manifesto={manifesto} aoConcluir={aoConcluir} aoVoltar={() => setEscolha(null)} />
      )}
    </CartaoDeAcao>
  );
}

/**
 * O formulário de recebimento, item por item.
 *
 * Os campos nascem vazios de propósito. Preenchê-los com a quantidade
 * declarada pelo gerador seria cômodo e inutilizaria a conferência: bastaria
 * confirmar para que nenhuma divergência jamais aparecesse. O valor declarado
 * fica ao lado, como referência.
 *
 * A regra RN05 exige todos os itens conferidos; a diferença acima de 5% marca
 * o item como divergente — o cálculo é do servidor, não desta tela.
 */
function Recebimento({
  manifesto,
  aoConcluir,
  aoVoltar,
}: PropsDeAcao & { aoVoltar: () => void }) {
  const acao = useAcao();
  const [quantidades, setQuantidades] = useState<Record<number, string>>({});
  const [observacao, setObservacao] = useState("");

  async function enviar(evento: FormEvent): Promise<void> {
    evento.preventDefault();
    const certo = await acao.executar(async () => {
      await api.registrarRecebimento(manifesto.id, {
        itens: manifesto.itens.map((item) => ({
          item_id: item.id,
          quantidade_recebida: Number(quantidades[item.id]),
        })),
        observacao: observacao.trim() === "" ? null : observacao.trim(),
      });
    });
    if (certo) aoConcluir();
  }

  return (
    <form className="pilha" onSubmit={enviar}>
      {manifesto.itens.map((item, indice) => (
        <Campo
          key={item.id}
          rotulo={`${item.tipo_residuo.codigo} — ${item.tipo_residuo.descricao}`}
          ajuda={`Declarado pelo gerador: ${numero(item.quantidade_declarada)} ${UNIDADE[item.unidade]}`}
          erro={acao.erro?.doCampo(`itens.${indice}.quantidade_recebida`)}
        >
          <input
            type="number"
            step="any"
            min="0"
            placeholder={`Quantidade recebida em ${UNIDADE[item.unidade]}`}
            value={quantidades[item.id] ?? ""}
            onChange={(evento) =>
              setQuantidades((atuais) => ({ ...atuais, [item.id]: evento.target.value }))
            }
            required
          />
        </Campo>
      ))}

      <Campo rotulo="Observação" ajuda="Opcional." erro={acao.erro?.doCampo("observacao")}>
        <textarea
          value={observacao}
          onChange={(evento) => setObservacao(evento.target.value)}
          maxLength={500}
        />
      </Campo>

      {acao.erro !== null && <AvisoDeErro erro={acao.erro} />}

      <div className="rodape-do-formulario">
        <button type="button" className="botao" onClick={aoVoltar}>
          Voltar
        </button>
        <button type="submit" className="botao botao-principal" disabled={acao.executando}>
          {acao.executando ? "Registrando…" : "Registrar recebimento"}
        </button>
      </div>
    </form>
  );
}

/** EM_TRANSPORTE → RECUSADO. O motivo é obrigatório (RN06). */
function Recusa({ manifesto, aoConcluir, aoVoltar }: PropsDeAcao & { aoVoltar: () => void }) {
  const acao = useAcao();
  const [motivo, setMotivo] = useState("");

  async function enviar(evento: FormEvent): Promise<void> {
    evento.preventDefault();
    const certo = await acao.executar(async () => {
      await api.recusar(manifesto.id, { motivo_recusa: motivo.trim() });
    });
    if (certo) aoConcluir();
  }

  return (
    <form className="pilha" onSubmit={enviar}>
      <Campo
        rotulo="Motivo da recusa"
        ajuda="Obrigatório, com ao menos 10 caracteres. Fica registrado no manifesto e no PDF."
        erro={acao.erro?.doCampo("motivo_recusa")}
      >
        <textarea
          value={motivo}
          onChange={(evento) => setMotivo(evento.target.value)}
          minLength={10}
          maxLength={500}
          required
        />
      </Campo>

      {acao.erro !== null && <AvisoDeErro erro={acao.erro} />}

      <div className="rodape-do-formulario">
        <button type="button" className="botao" onClick={aoVoltar}>
          Voltar
        </button>
        <button type="submit" className="botao botao-perigo" disabled={acao.executando}>
          {acao.executando ? "Registrando…" : "Recusar a carga"}
        </button>
      </div>
    </form>
  );
}

/** RECEBIDO → DESTINADO. O tipo de tratamento é obrigatório (RN06). */
function Destinacao({ manifesto, aoConcluir }: PropsDeAcao) {
  const acao = useAcao();
  const [tipo, setTipo] = useState<TipoDestinacao | "">("");
  const [observacao, setObservacao] = useState("");

  async function enviar(evento: FormEvent): Promise<void> {
    evento.preventDefault();
    const certo = await acao.executar(async () => {
      await api.informarDestinacao(manifesto.id, {
        tipo_destinacao: tipo as TipoDestinacao,
        observacao: observacao.trim() === "" ? null : observacao.trim(),
      });
    });
    if (certo) aoConcluir();
  }

  return (
    <CartaoDeAcao
      titulo="Informar destinação final"
      descricao="O tratamento aplicado encerra o ciclo do resíduo. É esta informação que alimenta o indicador de desvio de aterro."
    >
      <form className="pilha" onSubmit={enviar}>
        <Campo rotulo="Tratamento aplicado" erro={acao.erro?.doCampo("tipo_destinacao")}>
          <select
            value={tipo}
            onChange={(evento) => setTipo(evento.target.value as TipoDestinacao)}
            required
          >
            <option value="">Selecione…</option>
            {DESTINACOES.map((destinacao) => (
              <option key={destinacao} value={destinacao}>
                {DESTINACAO[destinacao]}
              </option>
            ))}
          </select>
        </Campo>

        <Campo rotulo="Observação" ajuda="Opcional." erro={acao.erro?.doCampo("observacao")}>
          <textarea
            value={observacao}
            onChange={(evento) => setObservacao(evento.target.value)}
            maxLength={500}
          />
        </Campo>

        {acao.erro !== null && <AvisoDeErro erro={acao.erro} />}

        <div className="rodape-do-formulario">
          <button type="submit" className="botao botao-principal" disabled={acao.executando}>
            {acao.executando ? "Registrando…" : "Informar destinação"}
          </button>
        </div>
      </form>
    </CartaoDeAcao>
  );
}

/**
 * EMITIDO → CANCELADO, possível apenas antes da coleta.
 *
 * A confirmação é o próprio formulário, que só aparece depois do primeiro
 * clique. Um aviso do navegador (`confirm`) daria o mesmo efeito, mas
 * interromperia a página inteira e não teria onde registrar o motivo.
 */
function Cancelamento({ manifesto, aoConcluir }: PropsDeAcao) {
  const acao = useAcao();
  const [confirmando, setConfirmando] = useState(false);
  const [observacao, setObservacao] = useState("");

  async function enviar(evento: FormEvent): Promise<void> {
    evento.preventDefault();
    const certo = await acao.executar(async () => {
      await api.cancelar(manifesto.id, {
        observacao: observacao.trim() === "" ? null : observacao.trim(),
      });
    });
    if (certo) aoConcluir();
  }

  return (
    <CartaoDeAcao
      titulo="Cancelar manifesto"
      descricao="Só é possível cancelar antes da coleta. Depois que a carga sai, o manifesto segue o fluxo até a destinação ou a recusa."
    >
      {!confirmando ? (
        <div className="rodape-do-formulario">
          <button type="button" className="botao botao-perigo" onClick={() => setConfirmando(true)}>
            Cancelar manifesto
          </button>
        </div>
      ) : (
        <form className="pilha" onSubmit={enviar}>
          <Campo
            rotulo="Motivo do cancelamento"
            ajuda="Opcional, mas recomendável: fica no histórico do manifesto."
            erro={acao.erro?.doCampo("observacao")}
          >
            <textarea
              value={observacao}
              onChange={(evento) => setObservacao(evento.target.value)}
              maxLength={500}
            />
          </Campo>

          {acao.erro !== null && <AvisoDeErro erro={acao.erro} />}

          <div className="rodape-do-formulario">
            <button type="button" className="botao" onClick={() => setConfirmando(false)}>
              Voltar
            </button>
            <button type="submit" className="botao botao-perigo" disabled={acao.executando}>
              {acao.executando ? "Cancelando…" : "Confirmar cancelamento"}
            </button>
          </div>
        </form>
      )}
    </CartaoDeAcao>
  );
}
