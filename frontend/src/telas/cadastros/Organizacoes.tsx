/**
 * Cadastro de organizações — a tela que consome as duas integrações externas.
 *
 * O município não é digitado: vem da lista oficial do IBGE, e é de lá que sai o
 * código de 7 dígitos que o sistema guarda. Digitado à mão, "Aparecida de
 * Goiânia" e "Aparecida de Goiania" seriam dois municípios diferentes nos
 * relatórios.
 *
 * O CEP preenche logradouro, bairro e município de uma vez, pelo ViaCEP. Os
 * nomes dos campos da resposta são iguais aos do cadastro de propósito — a
 * tradução já foi feita no servidor, e aqui o endereço é copiado campo a campo.
 *
 * Toda resposta das duas integrações diz de onde veio, no cabeçalho `X-Fonte`.
 * Quando o valor é `cache-expirado`, significa que o serviço de terceiro não
 * respondeu e o sistema serviu o último dado que conhecia: a tela avisa, porque
 * um endereço possivelmente desatualizado é diferente de um endereço conferido
 * agora.
 *
 * O mesmo formulário serve ao cadastro e à alteração. Na alteração, CNPJ e
 * papel aparecem travados, porque o servidor não os deixa mudar, e surge o
 * campo de situação. É pela alteração que uma licença vencida é renovada.
 */

import { useState } from "react";
import type { FormEvent } from "react";
import { api, PAPEIS } from "../../api/api";
import type { FonteDoDado } from "../../api/cliente";
import type { Organizacao, OrganizacaoNova, PapelOrganizacao } from "../../api/tipos";
import { Campo } from "../../componentes/Campo";
import { Marcador } from "../../componentes/Etiqueta";
import {
  AvisoDeErro,
  Carregando,
  Paginacao,
  Vazio,
} from "../../componentes/Pagina";
import {
  cep as formatarCep,
  cnpj as formatarCnpj,
  data,
  hoje,
  somenteDigitos,
} from "../../formatos";
import { PAPEL } from "../../rotulos";
import { useAcao } from "../../useAcao";
import { useCarregamento } from "../../useCarregamento";

const VAZIA: OrganizacaoNova = {
  razao_social: "",
  cnpj: "",
  papel: "GERADOR",
  cep: "",
  logradouro: "",
  numero: "",
  bairro: "",
  municipio_ibge_codigo: "",
  municipio_nome: "",
  licenca_numero: "",
  licenca_validade: "",
};

/** Os dados de uma organização já cadastrada, no formato do formulário. */
function paraOFormulario(organizacao: Organizacao): OrganizacaoNova {
  return {
    razao_social: organizacao.razao_social,
    cnpj: formatarCnpj(organizacao.cnpj),
    papel: organizacao.papel,
    cep: formatarCep(organizacao.cep),
    logradouro: organizacao.logradouro,
    numero: organizacao.numero,
    bairro: organizacao.bairro,
    municipio_ibge_codigo: organizacao.municipio_ibge_codigo,
    municipio_nome: organizacao.municipio_nome,
    licenca_numero: organizacao.licenca_numero,
    licenca_validade: organizacao.licenca_validade,
  };
}

export function Organizacoes() {
  const [rascunhoDaBusca, setRascunhoDaBusca] = useState("");
  const [busca, setBusca] = useState("");
  const [pagina, setPagina] = useState(1);
  // O formulário pode estar fechado (null), cadastrando uma organização nova
  // ("nova") ou alterando uma existente (a própria organização).
  const [formulario, setFormulario] = useState<Organizacao | "nova" | null>(null);
  const [recado, setRecado] = useState<string | null>(null);

  const lista = useCarregamento(() => api.listarOrganizacoes({ busca, pagina }), `${busca}|${pagina}`);

  return (
    <div className="pilha">
      <section className="cartao">
        <div className="cartao-corpo">
          <form
            className="filtros"
            onSubmit={(evento: FormEvent) => {
              evento.preventDefault();
              setBusca(rascunhoDaBusca);
              setPagina(1);
            }}
          >
            <Campo rotulo="Buscar">
              <input
                value={rascunhoDaBusca}
                onChange={(evento) => setRascunhoDaBusca(evento.target.value)}
                placeholder="Razão social ou CNPJ"
              />
            </Campo>

            <div className="rodape-do-formulario">
              <button type="submit" className="botao">
                Buscar
              </button>
              <button
                type="button"
                className="botao botao-principal"
                onClick={() => {
                  setFormulario(formulario === null ? "nova" : null);
                  setRecado(null);
                }}
              >
                {formulario === null ? "Nova organização" : "Fechar formulário"}
              </button>
            </div>
          </form>
        </div>
      </section>

      {recado !== null && <div className="aviso aviso-sucesso">{recado}</div>}

      {formulario !== null && (
        <Formulario
          // A chave recria o formulário ao trocar de organização, para que ele
          // não carregue os dados da anterior.
          key={formulario === "nova" ? "nova" : formulario.id}
          original={formulario === "nova" ? null : formulario}
          aoSalvar={(mensagem) => {
            setFormulario(null);
            setRecado(mensagem);
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
          <Vazio>Nenhuma organização encontrada.</Vazio>
        )}

        {lista.dado !== null && lista.dado.itens.length > 0 && (
          <>
            <div className="rolagem-lateral">
              <table className="tabela">
                <thead>
                  <tr>
                    <th>Razão social</th>
                    <th>CNPJ</th>
                    <th>Papel</th>
                    <th>Município</th>
                    <th>Licença</th>
                    <th>Situação</th>
                    <th aria-label="Ações" />
                  </tr>
                </thead>
                <tbody>
                  {lista.dado.itens.map((organizacao) => (
                    <tr key={organizacao.id}>
                      <td className="destaque">{organizacao.razao_social}</td>
                      <td>{formatarCnpj(organizacao.cnpj)}</td>
                      <td>{PAPEL[organizacao.papel]}</td>
                      <td>{organizacao.municipio_nome}</td>
                      <td>
                        {organizacao.licenca_numero}
                        <div className="miudo">até {data(organizacao.licenca_validade)}</div>
                      </td>
                      <td>
                        {!organizacao.ativo ? (
                          <Marcador>Inativa</Marcador>
                        ) : organizacao.licenca_validade < hoje() ? (
                          <Marcador tom="negativa">Licença vencida</Marcador>
                        ) : (
                          <Marcador tom="positiva">Apta</Marcador>
                        )}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="botao-texto"
                          onClick={() => {
                            setFormulario(organizacao);
                            setRecado(null);
                            // O formulário fica no topo da página, acima da lista.
                            window.scrollTo({ top: 0, behavior: "smooth" });
                          }}
                        >
                          Alterar
                        </button>
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

      <p className="nota">
        A coluna “Situação” é informativa: quem decide se uma organização pode participar de um
        manifesto novo é a regra RN04, aplicada no servidor no momento da emissão.
      </p>
    </div>
  );
}

/**
 * Cadastro (sem `original`) ou alteração (com a organização a alterar).
 */
function Formulario({
  original,
  aoSalvar,
}: {
  original: Organizacao | null;
  aoSalvar: (mensagem: string) => void;
}) {
  const alterando = original !== null;
  const [dados, setDados] = useState<OrganizacaoNova>(
    original === null ? VAZIA : paraOFormulario(original),
  );
  const [ativa, setAtiva] = useState(original?.ativo ?? true);
  const envio = useAcao();
  const consultaDeCep = useAcao();

  const [fonteDoCep, setFonteDoCep] = useState<FonteDoDado | null>(null);
  const [avisoDoCep, setAvisoDoCep] = useState<string | null>(null);
  // Evita repetir a consulta do mesmo CEP a cada vez que o campo perde o foco.
  // Na alteração, o CEP gravado conta como já consultado: passar pelo campo
  // sem mudá-lo não deve sobrescrever o endereço com a resposta do ViaCEP.
  const [cepConsultado, setCepConsultado] = useState(original?.cep ?? "");

  const municipios = useCarregamento(() => api.municipiosDeGoias(), "");
  const listaDeMunicipios = municipios.dado?.valor ?? [];

  function alterar(mudanca: Partial<OrganizacaoNova>): void {
    setDados((atuais) => ({ ...atuais, ...mudanca }));
  }

  async function consultarCep(): Promise<void> {
    const digitos = somenteDigitos(dados.cep);
    if (digitos.length !== 8 || digitos === cepConsultado) return;

    setCepConsultado(digitos);
    setAvisoDoCep(null);

    await consultaDeCep.executar(async () => {
      const { valor, fonte } = await api.enderecoPorCep(digitos);
      setFonteDoCep(fonte);

      if (valor.uf !== "GO") {
        // O sistema atende organizações de Goiás, e o código IBGE do município
        // é conferido no servidor (precisa começar com 52). Preencher os campos
        // com um endereço de outro estado só levaria a um erro na gravação.
        setAvisoDoCep(
          `O CEP informado é de ${valor.municipio_nome} (${valor.uf}). O sistema cadastra apenas organizações de Goiás.`,
        );
        return;
      }

      alterar({
        cep: valor.cep,
        // Logradouro e bairro podem vir vazios: CEP de zona rural e CEP geral
        // de município pequeno identificam a cidade, não a rua. Nesse caso o
        // que já estava digitado é preservado.
        logradouro: valor.logradouro === "" ? dados.logradouro : valor.logradouro,
        bairro: valor.bairro === "" ? dados.bairro : valor.bairro,
        municipio_ibge_codigo: valor.municipio_ibge_codigo,
        municipio_nome: valor.municipio_nome,
      });
    });
  }

  function escolherMunicipio(codigo: string): void {
    const escolhido = listaDeMunicipios.find((municipio) => municipio.codigo === codigo);
    alterar({
      municipio_ibge_codigo: codigo,
      municipio_nome: escolhido?.nome ?? "",
    });
  }

  async function enviar(evento: FormEvent): Promise<void> {
    evento.preventDefault();

    const certo = await envio.executar(async () => {
      if (original === null) {
        await api.criarOrganizacao({ ...dados, cnpj: somenteDigitos(dados.cnpj) });
      } else {
        // CNPJ e papel ficam de fora: o servidor não os deixa mudar.
        const { cnpj: _cnpj, papel: _papel, ...alteraveis } = dados;
        await api.alterarOrganizacao(original.id, { ...alteraveis, ativo: ativa });
      }
    });

    if (certo) {
      aoSalvar(`${dados.razao_social} foi ${alterando ? "alterada" : "cadastrada"}.`);
    }
  }

  const rotuloDoBotao = alterando ? "Salvar alterações" : "Cadastrar organização";

  return (
    <section className="cartao">
      <header>
        <h2>{alterando ? "Alterar organização" : "Nova organização"}</h2>
        <span className="miudo">município pela lista do IBGE; endereço pelo CEP</span>
      </header>

      <div className="cartao-corpo">
        <form className="pilha" onSubmit={enviar}>
          <div className="grade duas">
            <Campo rotulo="Razão social" erro={envio.erro?.doCampo("razao_social")}>
              <input
                value={dados.razao_social}
                onChange={(evento) => alterar({ razao_social: evento.target.value })}
                maxLength={120}
                required
              />
            </Campo>

            <Campo
              rotulo="CNPJ"
              ajuda={
                alterando
                  ? "O CNPJ identifica a organização e não muda."
                  : "Com ou sem máscara; os dígitos verificadores são conferidos."
              }
              erro={envio.erro?.doCampo("cnpj")}
            >
              <input
                value={dados.cnpj}
                onChange={(evento) => alterar({ cnpj: evento.target.value })}
                disabled={alterando}
                required
              />
            </Campo>
          </div>

          <div className="grade tres">
            <Campo
              rotulo="Papel no ciclo do resíduo"
              ajuda={alterando ? "Não muda: os manifestos em andamento dependem dele." : undefined}
              erro={envio.erro?.doCampo("papel")}
            >
              <select
                value={dados.papel}
                onChange={(evento) => alterar({ papel: evento.target.value as PapelOrganizacao })}
                disabled={alterando}
              >
                {PAPEIS.map((papel) => (
                  <option key={papel} value={papel}>
                    {PAPEL[papel]}
                  </option>
                ))}
              </select>
            </Campo>

            <Campo rotulo="Número da licença ambiental" erro={envio.erro?.doCampo("licenca_numero")}>
              <input
                value={dados.licenca_numero}
                onChange={(evento) => alterar({ licenca_numero: evento.target.value })}
                maxLength={40}
                required
              />
            </Campo>

            <Campo
              rotulo="Validade da licença"
              erro={envio.erro?.doCampo("licenca_validade")}
            >
              <input
                type="date"
                value={dados.licenca_validade}
                onChange={(evento) => alterar({ licenca_validade: evento.target.value })}
                required
              />
            </Campo>
          </div>

          <div className="grade tres">
            <Campo
              rotulo="CEP"
              ajuda={
                consultaDeCep.executando
                  ? "Consultando o ViaCEP…"
                  : "Preenche o endereço automaticamente."
              }
              erro={envio.erro?.doCampo("cep")}
            >
              <input
                value={dados.cep}
                onChange={(evento) => alterar({ cep: evento.target.value })}
                onBlur={consultarCep}
                maxLength={9}
                required
              />
            </Campo>

            <Campo rotulo="Logradouro" erro={envio.erro?.doCampo("logradouro")}>
              <input
                value={dados.logradouro}
                onChange={(evento) => alterar({ logradouro: evento.target.value })}
                maxLength={160}
                required
              />
            </Campo>

            <Campo rotulo="Número" erro={envio.erro?.doCampo("numero")}>
              <input
                value={dados.numero}
                onChange={(evento) => alterar({ numero: evento.target.value })}
                maxLength={20}
                required
              />
            </Campo>
          </div>

          <div className="grade duas">
            <Campo rotulo="Bairro" erro={envio.erro?.doCampo("bairro")}>
              <input
                value={dados.bairro}
                onChange={(evento) => alterar({ bairro: evento.target.value })}
                maxLength={80}
                required
              />
            </Campo>

            <Campo
              rotulo="Município"
              ajuda={
                municipios.carregando
                  ? "Carregando a lista do IBGE…"
                  : `${listaDeMunicipios.length} municípios de Goiás`
              }
              erro={envio.erro?.doCampo("municipio_ibge_codigo")}
            >
              <select
                value={dados.municipio_ibge_codigo}
                onChange={(evento) => escolherMunicipio(evento.target.value)}
                required
              >
                <option value="">Selecione…</option>
                {listaDeMunicipios.map((municipio) => (
                  <option key={municipio.codigo} value={municipio.codigo}>
                    {municipio.nome}
                  </option>
                ))}
              </select>
            </Campo>
          </div>

          {alterando && (
            <div className="grade duas">
              <Campo
                rotulo="Situação"
                ajuda="Inativa, não entra em manifestos novos; os que estão em andamento continuam."
                erro={envio.erro?.doCampo("ativo")}
              >
                <select
                  value={ativa ? "ativa" : "inativa"}
                  onChange={(evento) => setAtiva(evento.target.value === "ativa")}
                >
                  <option value="ativa">Ativa</option>
                  <option value="inativa">Inativa</option>
                </select>
              </Campo>
            </div>
          )}

          {avisoDoCep !== null && <div className="aviso aviso-atencao">{avisoDoCep}</div>}

          {fonteDoCep === "cache-expirado" && (
            <div className="aviso aviso-atencao">
              O ViaCEP não respondeu agora; o endereço veio do último dado guardado pelo sistema.
              Confira antes de salvar.
            </div>
          )}

          {municipios.erro !== null && <AvisoDeErro erro={municipios.erro} />}
          {consultaDeCep.erro !== null && <AvisoDeErro erro={consultaDeCep.erro} />}
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
