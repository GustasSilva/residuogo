/**
 * As rotas da API, uma função por operação.
 *
 * Esta é a única camada que conhece os caminhos (`/manifestos/5/coleta`) e o
 * formato de cada resposta. As telas chamam `api.confirmarColeta(...)` e não
 * montam URL nenhuma — assim uma rota que mude de endereço no backend é
 * corrigida em um lugar só, e o nome da função diz o que a chamada faz.
 *
 * Os filtros de listagem são opcionais e viram parâmetros de consulta apenas
 * quando preenchidos (ver `consulta`, em `cliente.ts`).
 */

import { baixarArquivo, consulta, pedir, pedirCatalogo, pedirComFonte, pedirImagem } from "./cliente";
import type {
  Acondicionamento,
  Indicadores,
  Manifesto,
  ManifestoNovo,
  ManifestoResumo,
  Municipio,
  Movimentacao,
  Organizacao,
  OrganizacaoNova,
  Pagina,
  PapelOrganizacao,
  Resumo,
  StatusManifesto,
  TipoDestinacao,
  TipoResiduo,
  TipoResiduoNovo,
  Token,
  Usuario,
  UsuarioLogado,
  UsuarioNovo,
  EnderecoCep,
} from "./tipos";

export interface FiltrosDeManifesto {
  status?: StatusManifesto | "";
  inicio?: string;
  fim?: string;
  participante_id?: string;
  numero?: string;
  pagina?: number;
}

export const api = {
  // ---------------------------------------------------------------- sessão

  entrar(email: string, senha: string): Promise<Token> {
    return pedir<Token>("/auth/login", { metodo: "POST", corpo: { email, senha } });
  },

  eu(): Promise<UsuarioLogado> {
    return pedir<UsuarioLogado>("/auth/me");
  },

  // ------------------------------------------------------------ manifestos

  listarManifestos(filtros: FiltrosDeManifesto): Promise<Pagina<ManifestoResumo>> {
    return pedir<Pagina<ManifestoResumo>>(`/manifestos${consulta({ ...filtros, tamanho: 20 })}`);
  },

  buscarManifesto(id: number): Promise<Manifesto> {
    return pedir<Manifesto>(`/manifestos/${id}`);
  },

  /** Resolve o token impresso no QR code do documento. */
  buscarManifestoPorToken(token: string): Promise<Manifesto> {
    return pedir<Manifesto>(`/manifestos/qr/${token}`);
  },

  historicoDoManifesto(id: number): Promise<Movimentacao[]> {
    return pedir<Movimentacao[]>(`/manifestos/${id}/historico`);
  },

  emitirManifesto(dados: ManifestoNovo): Promise<Manifesto> {
    return pedir<Manifesto>("/manifestos", { metodo: "POST", corpo: dados });
  },

  // As cinco transições da máquina de estados. Cada uma é um POST para um
  // sub-recurso que nomeia o evento: o cliente conta o que aconteceu e o
  // servidor decide o status resultante.

  confirmarColeta(
    id: number,
    dados: { placa_veiculo: string; motorista_nome: string; observacao: string | null },
  ): Promise<Manifesto> {
    return pedir<Manifesto>(`/manifestos/${id}/coleta`, { metodo: "POST", corpo: dados });
  },

  registrarRecebimento(
    id: number,
    dados: {
      itens: { item_id: number; quantidade_recebida: number }[];
      observacao: string | null;
    },
  ): Promise<Manifesto> {
    return pedir<Manifesto>(`/manifestos/${id}/recebimento`, { metodo: "POST", corpo: dados });
  },

  recusar(id: number, dados: { motivo_recusa: string }): Promise<Manifesto> {
    return pedir<Manifesto>(`/manifestos/${id}/recusa`, { metodo: "POST", corpo: dados });
  },

  informarDestinacao(
    id: number,
    dados: { tipo_destinacao: TipoDestinacao; observacao: string | null },
  ): Promise<Manifesto> {
    return pedir<Manifesto>(`/manifestos/${id}/destinacao`, { metodo: "POST", corpo: dados });
  },

  cancelar(id: number, dados: { observacao: string | null }): Promise<Manifesto> {
    return pedir<Manifesto>(`/manifestos/${id}/cancelamento`, { metodo: "POST", corpo: dados });
  },

  // -------------------------------------------------------------- arquivos

  abrirPdfDoManifesto(manifesto: ManifestoResumo): Promise<void> {
    return baixarArquivo(
      `/manifestos/${manifesto.id}/pdf`,
      `manifesto-${manifesto.numero}.pdf`,
      true,
    );
  },

  imagemDoQrCode(id: number): Promise<string> {
    return pedirImagem(`/manifestos/${id}/qrcode.png`);
  },

  abrirPdfDoResumo(inicio: string, fim: string): Promise<void> {
    return baixarArquivo(
      `/relatorios/resumo.pdf${consulta({ inicio, fim })}`,
      `resumo-${inicio}-a-${fim}.pdf`,
      true,
    );
  },

  exportarManifestosEmCsv(filtros: FiltrosDeManifesto): Promise<void> {
    // A exportação usa os mesmos filtros da listagem — e sem paginação, que
    // é a única diferença: exportar meia página não serviria para nada.
    const { pagina: _ignorado, ...semPaginacao } = filtros;
    return baixarArquivo(
      `/relatorios/manifestos.csv${consulta(semPaginacao)}`,
      "manifestos.csv",
    );
  },

  // ------------------------------------------------- relatórios e painel

  resumo(inicio?: string, fim?: string): Promise<Resumo> {
    return pedir<Resumo>(`/relatorios/resumo${consulta({ inicio, fim })}`);
  },

  indicadores(): Promise<Indicadores> {
    return pedir<Indicadores>("/dashboard/indicadores");
  },

  // --------------------------------------------------------------- cadastros

  listarOrganizacoes(parametros: {
    papel?: PapelOrganizacao | "";
    busca?: string;
    pagina?: number;
  }): Promise<Pagina<Organizacao>> {
    return pedir<Pagina<Organizacao>>(`/organizacoes${consulta({ ...parametros, tamanho: 20 })}`);
  },

  /**
   * Organizações que podem receber um manifesto agora: ativas, com o papel
   * pedido e com licença ambiental válida.
   *
   * O filtro `apenas_aptas` reusa no servidor as mesmas condições que a
   * emissão aplica (RN04). É por isso que a tela de novo manifesto não
   * consegue oferecer um participante que a API depois recusaria.
   */
  organizacoesAptas(papel: PapelOrganizacao): Promise<Organizacao[]> {
    return pedirCatalogo<Organizacao>("/organizacoes", { papel, apenas_aptas: "true" });
  },

  todasAsOrganizacoes(): Promise<Organizacao[]> {
    return pedirCatalogo<Organizacao>("/organizacoes");
  },

  criarOrganizacao(dados: OrganizacaoNova): Promise<Organizacao> {
    return pedir<Organizacao>("/organizacoes", { metodo: "POST", corpo: dados });
  },

  listarUsuarios(parametros: { organizacao_id?: string; pagina?: number }): Promise<Pagina<Usuario>> {
    return pedir<Pagina<Usuario>>(`/usuarios${consulta({ ...parametros, tamanho: 20 })}`);
  },

  criarUsuario(dados: UsuarioNovo): Promise<Usuario> {
    return pedir<Usuario>("/usuarios", { metodo: "POST", corpo: dados });
  },

  tiposDeResiduo(): Promise<TipoResiduo[]> {
    return pedirCatalogo<TipoResiduo>("/tipos-residuo");
  },

  criarTipoDeResiduo(dados: TipoResiduoNovo): Promise<TipoResiduo> {
    return pedir<TipoResiduo>("/tipos-residuo", { metodo: "POST", corpo: dados });
  },

  // ------------------------------------------------------------ localidades

  /** Os 246 municípios de Goiás, da API de Localidades do IBGE. */
  municipiosDeGoias() {
    return pedirComFonte<Municipio[]>("/localidades/municipios-go");
  },

  /** O endereço de um CEP, do ViaCEP, já com os nomes de campo do cadastro. */
  enderecoPorCep(cep: string) {
    return pedirComFonte<EnderecoCep>(`/localidades/cep/${cep}`);
  },
};

/** Acondicionamentos possíveis, na ordem em que aparecem no formulário. */
export const ACONDICIONAMENTOS: Acondicionamento[] = [
  "TAMBOR",
  "BOMBONA",
  "CACAMBA",
  "BIG_BAG",
  "GRANEL",
  "OUTRO",
];

/** Destinações possíveis, agrupadas por recuperação antes de disposição. */
export const DESTINACOES: TipoDestinacao[] = [
  "RECICLAGEM",
  "COMPOSTAGEM",
  "COPROCESSAMENTO",
  "INCINERACAO",
  "ATERRO",
  "OUTRO_TRATAMENTO",
];

export const STATUS: StatusManifesto[] = [
  "EMITIDO",
  "EM_TRANSPORTE",
  "RECEBIDO",
  "DESTINADO",
  "RECUSADO",
  "CANCELADO",
];

export const PAPEIS: PapelOrganizacao[] = ["GERADOR", "TRANSPORTADOR", "DESTINADOR"];

/**
 * Destinações que recuperam o resíduo, espelhando `DESTINACOES_RECUPERACAO`
 * no backend.
 *
 * Aqui o conjunto serve a uma única coisa: pintar de outra cor a barra das
 * destinações que apenas dispõem o resíduo. O indicador de desvio de aterro em
 * si vem calculado do servidor — a conta não é refeita na tela.
 */
export const DESTINACOES_DE_RECUPERACAO: string[] = [
  "RECICLAGEM",
  "COMPOSTAGEM",
  "COPROCESSAMENTO",
];
