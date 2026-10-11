/**
 * Consulta SOAP: a aplicação consumindo o seu outro web service.
 *
 * Todas as outras telas usam o REST. Esta faz pelo SOAP a pergunta que um
 * sistema externo faria — "em que pé está este manifesto?" — e mostra as duas
 * mensagens trocadas, o envelope que foi e o que voltou. Serve para comparar
 * os dois estilos na apresentação: o mesmo dado, agora em XML e descrito por
 * um contrato WSDL.
 *
 * Como no cliente `zeep`, quem consulta se identifica pelo CNPJ, e o serviço
 * só responde a quem participa do manifesto. O campo já vem com o CNPJ da
 * organização do usuário; trocá-lo por outro demonstra o SOAP Fault.
 */

import { useState } from "react";
import type { FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { consultarStatusPeloSoap, ENDERECO_DO_WSDL, ENDERECO_SOAP } from "../api/soap";
import type { FalhaSoap, StatusPeloSoap, TrocaSoap } from "../api/soap";
import { Campo } from "../componentes/Campo";
import { Etiqueta } from "../componentes/Etiqueta";
import { AvisoDeErro, TituloDaPagina } from "../componentes/Pagina";
import { cnpj as formatarCnpj, dataEHora, somenteDigitos } from "../formatos";
import { DESTINACAO } from "../rotulos";
import { useSessao } from "../sessao";
import { useAcao } from "../useAcao";

export function ConsultaSoap() {
  const { usuario } = useSessao();
  // O detalhe do manifesto abre esta tela com o número já preenchido.
  const [parametros] = useSearchParams();
  const cnpjDaOrganizacao = usuario?.organizacao?.cnpj;

  const [numero, setNumero] = useState(parametros.get("numero") ?? "");
  const [cnpj, setCnpj] = useState(
    cnpjDaOrganizacao === undefined ? "" : formatarCnpj(cnpjDaOrganizacao),
  );
  const [troca, setTroca] = useState<TrocaSoap | null>(null);
  const consulta = useAcao();

  async function enviar(evento: FormEvent): Promise<void> {
    evento.preventDefault();
    setTroca(null);
    await consulta.executar(async () => {
      setTroca(await consultarStatusPeloSoap(numero.trim(), somenteDigitos(cnpj)));
    });
  }

  return (
    <>
      <TituloDaPagina
        titulo="Consulta SOAP"
        legenda="O status de um manifesto pelo web service SOAP, com as mensagens XML trocadas."
      >
        <a className="botao" href={ENDERECO_DO_WSDL} target="_blank" rel="noreferrer">
          Ver o contrato WSDL
        </a>
      </TituloDaPagina>

      <div className="pilha">
        <section className="cartao">
          <div className="cartao-corpo">
            <form className="pilha" onSubmit={enviar}>
              <div className="grade duas">
                <Campo rotulo="Número do manifesto">
                  <input
                    value={numero}
                    onChange={(evento) => setNumero(evento.target.value)}
                    placeholder="RGO-2026-000001"
                    required
                  />
                </Campo>

                <Campo
                  rotulo="CNPJ de quem consulta"
                  ajuda={
                    cnpjDaOrganizacao === undefined
                      ? "Informe o CNPJ de um participante do manifesto."
                      : "O da sua organização; outro CNPJ demonstra o SOAP Fault."
                  }
                >
                  <input value={cnpj} onChange={(evento) => setCnpj(evento.target.value)} required />
                </Campo>
              </div>

              <div className="rodape-do-formulario">
                <button
                  type="submit"
                  className="botao botao-principal"
                  disabled={consulta.executando}
                >
                  {consulta.executando ? "Consultando…" : "Consultar"}
                </button>
              </div>
            </form>
          </div>
        </section>

        {consulta.erro !== null && <AvisoDeErro erro={consulta.erro} />}

        {troca !== null && (
          <>
            {"manifesto" in troca.resultado ? (
              <Resposta manifesto={troca.resultado.manifesto} />
            ) : (
              <Falha falha={troca.resultado.falha} />
            )}

            <Mensagem titulo="Envelope enviado" legenda={`POST ${ENDERECO_SOAP}`} xml={troca.enviado} />
            <Mensagem titulo="Envelope recebido" legenda="text/xml" xml={troca.recebido} />
          </>
        )}
      </div>
    </>
  );
}

function Resposta({ manifesto }: { manifesto: StatusPeloSoap }) {
  return (
    <section className="cartao">
      <header>
        <h2>Manifesto {manifesto.numero}</h2>
        <Etiqueta status={manifesto.status} />
      </header>
      <div className="cartao-corpo">
        <dl className="dados">
          <div>
            <dt>Gerador</dt>
            <dd>{manifesto.gerador_razao_social}</dd>
          </div>
          <div>
            <dt>Destinador</dt>
            <dd>{manifesto.destinador_razao_social}</dd>
          </div>
          <div>
            <dt>Destinação</dt>
            <dd>
              {manifesto.tipo_destinacao === null ? "—" : DESTINACAO[manifesto.tipo_destinacao]}
            </dd>
          </div>
          <div>
            <dt>Atualizado em</dt>
            <dd>{dataEHora(manifesto.atualizado_em)}</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}

/**
 * O SOAP Fault como o usuário o vê. O `faultcode` diz de quem é o erro, e o
 * código interno é o mesmo que o REST devolveria para o mesmo problema.
 */
function Falha({ falha }: { falha: FalhaSoap }) {
  return (
    <div className="aviso aviso-erro" role="alert">
      <div>O serviço respondeu com um SOAP Fault: {falha.faultstring}</div>
      <div className="aviso-codigo">
        {falha.codigo} · {falha.faultcode}
      </div>
    </div>
  );
}

function Mensagem({ titulo, legenda, xml }: { titulo: string; legenda: string; xml: string }) {
  return (
    <section className="cartao">
      <header>
        <h2>{titulo}</h2>
        <span className="miudo">{legenda}</span>
      </header>
      <pre className="xml">{xml}</pre>
    </section>
  );
}
