/**
 * Como cada valor de enumeração é escrito na tela.
 *
 * Os mesmos rótulos existem no backend (`app/enums.py`), onde servem ao PDF e
 * ao CSV. A duplicação é consciente: traduzir no servidor e devolver o texto
 * pronto em cada resposta engordaria o JSON e tiraria do cliente a
 * possibilidade de exibir o mesmo estado de forma diferente em cada contexto
 * (a etiqueta da listagem é curta; o texto do histórico, não). O que não pode
 * divergir é o significado — e ele está fixado pela enumeração.
 */

import type {
  Acondicionamento,
  ClasseResiduo,
  PapelOrganizacao,
  PerfilUsuario,
  StatusManifesto,
  TipoDestinacao,
  UnidadeMedida,
} from "./api/tipos";

export const STATUS: Record<StatusManifesto, string> = {
  EMITIDO: "Emitido",
  EM_TRANSPORTE: "Em transporte",
  RECEBIDO: "Recebido",
  RECUSADO: "Recusado",
  DESTINADO: "Destinado",
  CANCELADO: "Cancelado",
};

export const PAPEL: Record<PapelOrganizacao, string> = {
  GERADOR: "Gerador",
  TRANSPORTADOR: "Transportador",
  DESTINADOR: "Destinador",
};

export const PERFIL: Record<PerfilUsuario, string> = {
  ADMIN: "Administrador",
  USUARIO: "Usuário",
};

export const CLASSE: Record<ClasseResiduo, string> = {
  I: "Classe I — perigoso",
  IIA: "Classe II A — não inerte",
  IIB: "Classe II B — inerte",
};

/** Versão curta, para caber na coluna de uma tabela. */
export const CLASSE_CURTA: Record<ClasseResiduo, string> = {
  I: "I",
  IIA: "II A",
  IIB: "II B",
};

export const DESTINACAO: Record<TipoDestinacao, string> = {
  RECICLAGEM: "Reciclagem",
  COMPOSTAGEM: "Compostagem",
  COPROCESSAMENTO: "Coprocessamento",
  INCINERACAO: "Incineração",
  ATERRO: "Aterro sanitário",
  OUTRO_TRATAMENTO: "Outro tratamento",
};

export const ACONDICIONAMENTO: Record<Acondicionamento, string> = {
  TAMBOR: "Tambor",
  BOMBONA: "Bombona",
  CACAMBA: "Caçamba",
  BIG_BAG: "Big bag",
  GRANEL: "Granel",
  OUTRO: "Outro",
};

/** Unidade como se escreve: m³ com o expoente, as outras em minúsculas. */
export const UNIDADE: Record<UnidadeMedida, string> = {
  KG: "kg",
  T: "t",
  L: "L",
  M3: "m³",
};
