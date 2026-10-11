/**
 * Os tipos do contrato da API, espelhando os schemas Pydantic do backend
 * (`app/schemas.py`).
 *
 * Escritos à mão, e não gerados a partir do OpenAPI, por uma razão prática:
 * gerar exigiria uma ferramenta a mais no projeto, e a divergência entre os
 * dois lados apareceria como erro de compilação no primeiro uso do campo
 * errado — que é exatamente o que se quer proteger. Em troca, estes nomes
 * precisam acompanhar o backend quando ele mudar.
 *
 * Datas chegam como texto no JSON: `datetime` em ISO 8601 com fuso, `date`
 * como `AAAA-MM-DD`. O tipo aqui é `string` para que fique explícito que a
 * conversão acontece na hora de exibir (ver `formatos.ts`).
 */

export type PapelOrganizacao = "GERADOR" | "TRANSPORTADOR" | "DESTINADOR";

export type PerfilUsuario = "ADMIN" | "USUARIO";

export type ClasseResiduo = "I" | "IIA" | "IIB";

export type UnidadeMedida = "KG" | "T" | "L" | "M3";

export type StatusManifesto =
  | "EMITIDO"
  | "EM_TRANSPORTE"
  | "RECEBIDO"
  | "RECUSADO"
  | "DESTINADO"
  | "CANCELADO";

export type TipoDestinacao =
  | "RECICLAGEM"
  | "COMPOSTAGEM"
  | "COPROCESSAMENTO"
  | "INCINERACAO"
  | "ATERRO"
  | "OUTRO_TRATAMENTO";

export type Acondicionamento =
  | "TAMBOR"
  | "BOMBONA"
  | "CACAMBA"
  | "BIG_BAG"
  | "GRANEL"
  | "OUTRO";

/** Envelope de toda listagem paginada da API. */
export interface Pagina<Item> {
  itens: Item[];
  total: number;
  pagina: number;
  tamanho: number;
  paginas: number;
}

export interface Token {
  token: string;
  tipo: string;
  expira_em_minutos: number;
}

export interface OrganizacaoResumo {
  id: number;
  razao_social: string;
  cnpj: string;
  papel: PapelOrganizacao;
  municipio_nome: string;
}

export interface Organizacao extends OrganizacaoResumo {
  cep: string;
  logradouro: string;
  numero: string;
  bairro: string;
  municipio_ibge_codigo: string;
  licenca_numero: string;
  licenca_validade: string;
  ativo: boolean;
  criado_em: string;
}

/** Dados de cadastro de uma organização, como o formulário os envia. */
export interface OrganizacaoNova {
  razao_social: string;
  cnpj: string;
  papel: PapelOrganizacao;
  cep: string;
  logradouro: string;
  numero: string;
  bairro: string;
  municipio_ibge_codigo: string;
  municipio_nome: string;
  licenca_numero: string;
  licenca_validade: string;
}

/**
 * Alteração de uma organização: o cadastro inteiro, menos CNPJ e papel, que
 * não mudam (ver `OrganizacaoAtualizar` no backend).
 */
export type OrganizacaoAlterada = Omit<OrganizacaoNova, "cnpj" | "papel"> & { ativo: boolean };

export interface Usuario {
  id: number;
  nome: string;
  email: string;
  perfil: PerfilUsuario;
  ativo: boolean;
  organizacao_id: number | null;
}

/**
 * Resposta de `/auth/me`. A organização vem completa porque é o papel dela
 * que decide quais ações cada tela oferece.
 */
export interface UsuarioLogado extends Usuario {
  organizacao: OrganizacaoResumo | null;
}

export interface UsuarioNovo {
  nome: string;
  email: string;
  senha: string;
  perfil: PerfilUsuario;
  organizacao_id: number | null;
}

/** Alteração de um usuário. `nova_senha` nula mantém a senha atual. */
export interface UsuarioAlterado {
  nome: string;
  ativo: boolean;
  nova_senha: string | null;
}

export interface TrocaDeSenha {
  senha_atual: string;
  nova_senha: string;
}

export interface TipoResiduo {
  id: number;
  codigo: string;
  descricao: string;
  classe: ClasseResiduo;
  unidade_padrao: UnidadeMedida;
}

export type TipoResiduoNovo = Omit<TipoResiduo, "id">;

/** Correção de um tipo do catálogo: o código não muda. */
export type TipoResiduoCorrigido = Omit<TipoResiduoNovo, "codigo">;

export interface ItemManifesto {
  id: number;
  tipo_residuo: TipoResiduo;
  quantidade_declarada: number;
  quantidade_recebida: number | null;
  unidade: UnidadeMedida;
  acondicionamento: Acondicionamento;
  divergente: boolean;
}

export interface ManifestoResumo {
  id: number;
  numero: string | null;
  status: StatusManifesto;
  gerador: OrganizacaoResumo;
  transportador: OrganizacaoResumo;
  destinador: OrganizacaoResumo;
  tipo_destinacao: TipoDestinacao | null;
  emitido_em: string;
  atualizado_em: string;
}

export interface Manifesto extends ManifestoResumo {
  placa_veiculo: string | null;
  motorista_nome: string | null;
  motivo_recusa: string | null;
  observacoes: string | null;
  qr_token: string;
  coletado_em: string | null;
  recebido_em: string | null;
  destinado_em: string | null;
  itens: ItemManifesto[];
}

export interface Movimentacao {
  id: number;
  status_anterior: StatusManifesto | null;
  status_novo: StatusManifesto;
  data_hora: string;
  observacao: string | null;
  usuario: { id: number; nome: string; perfil: PerfilUsuario };
}

/** Um item na emissão de um manifesto. */
export interface ItemNovo {
  tipo_residuo_id: number;
  quantidade_declarada: number;
  unidade: UnidadeMedida;
  acondicionamento: Acondicionamento;
}

export interface ManifestoNovo {
  transportador_id: number;
  destinador_id: number;
  itens: ItemNovo[];
  observacoes: string | null;
}

export interface Municipio {
  codigo: string;
  nome: string;
}

export interface EnderecoCep {
  cep: string;
  logradouro: string;
  bairro: string;
  municipio_nome: string;
  municipio_ibge_codigo: string;
  uf: string;
}

export interface LinhaRelatorio {
  chave: string;
  rotulo: string;
  massa_kg: number;
  volume_m3: number;
  manifestos: number;
  itens: number;
}

export interface LinhaMensal extends LinhaRelatorio {
  inicio: string;
}

export interface Resumo {
  inicio: string;
  fim: string;
  total: LinhaRelatorio;
  por_tipo: LinhaRelatorio[];
  por_classe: LinhaRelatorio[];
  por_destinacao: LinhaRelatorio[];
  divergencias: {
    itens_conferidos: number;
    itens_divergentes: number;
    percentual: number;
  };
}

export interface Indicadores {
  referencia: string;
  mes: {
    inicio: string;
    fim: string;
    manifestos_emitidos: number;
    manifestos_destinados: number;
    massa_kg: number;
    volume_m3: number;
  };
  pendentes_por_status: { status: StatusManifesto; rotulo: string; total: number }[];
  desvio_de_aterro: {
    meses: number;
    massa_recuperada_kg: number;
    massa_total_kg: number;
    /** Nulo quando nada foi destinado: zero diria que nada foi recuperado. */
    percentual: number | null;
  };
  por_destinacao: LinhaRelatorio[];
  serie_mensal: LinhaMensal[];
  licencas_a_vencer: {
    organizacao_id: number;
    razao_social: string;
    papel: PapelOrganizacao;
    licenca_numero: string;
    licenca_validade: string;
    dias_restantes: number;
    vencida: boolean;
  }[];
}
