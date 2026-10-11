/**
 * Cliente SOAP do front-end: a mesma consulta que um sistema externo faria.
 *
 * O resto da aplicação fala REST, com JSON. Este módulo consome o outro web
 * service do sistema — e sem biblioteca, de propósito: o envelope é montado
 * como texto e a resposta é lida com o `DOMParser` do navegador, para que cada
 * parte da mensagem SOAP fique à vista de quem lê o código.
 *
 * O contrato está no WSDL. O namespace, o nome da operação e os campos abaixo
 * são os que ele declara.
 */

import { ENDERECO_DA_API, ErroDaApi } from "./cliente";
import type { StatusManifesto, TipoDestinacao } from "./tipos";

/** O serviço SOAP fica no mesmo servidor do REST, fora de `/api/v1`. */
export const ENDERECO_SOAP = new URL("/soap/manifesto", ENDERECO_DA_API).href;
export const ENDERECO_DO_WSDL = `${ENDERECO_SOAP}?wsdl`;

const NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/";
const NS_SERVICO = "http://residuogo.example/soap/manifesto";
const OPERACAO = "ConsultarStatusManifesto";

/** O que a operação devolve, com os nomes de campo do WSDL. */
export interface StatusPeloSoap {
  numero: string;
  status: StatusManifesto;
  gerador_razao_social: string;
  destinador_razao_social: string;
  /** Ausente enquanto o manifesto não foi destinado. */
  tipo_destinacao: TipoDestinacao | null;
  atualizado_em: string;
}

/** Um SOAP Fault: a forma de o SOAP responder com erro. */
export interface FalhaSoap {
  /** `soap:Client` quando o erro é de quem pediu; `soap:Server` quando é do servidor. */
  faultcode: string;
  faultstring: string;
  /** O mesmo código de erro que o REST devolve no campo `codigo`. */
  codigo: string;
}

export type ResultadoSoap = { manifesto: StatusPeloSoap } | { falha: FalhaSoap };

/** Uma ida e volta ao serviço: as duas mensagens trocadas e o que se leu da resposta. */
export interface TrocaSoap {
  enviado: string;
  recebido: string;
  resultado: ResultadoSoap;
}

/** Escapa os caracteres que mudariam o sentido do XML se viessem digitados. */
function escaparXml(texto: string): string {
  return texto.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/**
 * O envelope da consulta. O `Body` carrega um elemento com o nome da operação,
 * e os filhos dele são os parâmetros.
 */
function montarEnvelope(numero: string, cnpj: string): string {
  return `<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="${NS_SOAP}" xmlns:rgo="${NS_SERVICO}">
  <soap:Body>
    <rgo:${OPERACAO}>
      <rgo:numero>${escaparXml(numero)}</rgo:numero>
      <rgo:cnpj_consultante>${escaparXml(cnpj)}</rgo:cnpj_consultante>
    </rgo:${OPERACAO}>
  </soap:Body>
</soap:Envelope>`;
}

/** O texto de um elemento do namespace do serviço, ou nulo se ele não veio. */
function lerCampo(documento: Document, nome: string): string | null {
  return documento.getElementsByTagNameNS(NS_SERVICO, nome)[0]?.textContent ?? null;
}

/** Lê o envelope de resposta, que traz ou um `Fault` ou a resposta da operação. */
function lerResposta(xml: string): ResultadoSoap {
  const documento = new DOMParser().parseFromString(xml, "text/xml");

  const falha = documento.getElementsByTagNameNS(NS_SOAP, "Fault")[0];
  if (falha !== undefined) {
    return {
      falha: {
        // No SOAP 1.1, `faultcode` e `faultstring` não levam namespace.
        faultcode: falha.getElementsByTagName("faultcode")[0]?.textContent ?? "",
        faultstring: falha.getElementsByTagName("faultstring")[0]?.textContent ?? "",
        codigo: lerCampo(documento, "codigo") ?? "",
      },
    };
  }

  // Nem Fault nem resposta: o que voltou não é uma mensagem deste serviço
  // (XML mal formado também cai aqui).
  if (documento.getElementsByTagNameNS(NS_SERVICO, `${OPERACAO}Response`).length === 0) {
    throw new ErroDaApi(
      0,
      "RESPOSTA_SOAP_INVALIDA",
      "O serviço SOAP respondeu uma mensagem que não é a resposta esperada.",
    );
  }

  return {
    manifesto: {
      numero: lerCampo(documento, "numero") ?? "",
      status: lerCampo(documento, "status") as StatusManifesto,
      gerador_razao_social: lerCampo(documento, "gerador_razao_social") ?? "",
      destinador_razao_social: lerCampo(documento, "destinador_razao_social") ?? "",
      tipo_destinacao: lerCampo(documento, "tipo_destinacao") as TipoDestinacao | null,
      atualizado_em: lerCampo(documento, "atualizado_em") ?? "",
    },
  };
}

/**
 * Consulta o status de um manifesto pelo serviço SOAP.
 *
 * Um Fault chega com HTTP 500 — é a regra do SOAP 1.1 — e ainda assim é uma
 * resposta válida, que a tela mostra. Por isso o status HTTP não decide nada
 * aqui: quem decide é o conteúdo do envelope.
 */
export async function consultarStatusPeloSoap(numero: string, cnpj: string): Promise<TrocaSoap> {
  const enviado = montarEnvelope(numero, cnpj);

  let resposta: Response;
  try {
    resposta = await fetch(ENDERECO_SOAP, {
      method: "POST",
      headers: {
        "Content-Type": "text/xml; charset=utf-8",
        // Declarado no WSDL, como pede o SOAP 1.1. O servidor identifica a
        // operação pelo elemento dentro do Body, mas um cliente correto o envia.
        SOAPAction: `"${NS_SERVICO}/${OPERACAO}"`,
      },
      body: enviado,
    });
  } catch {
    throw new ErroDaApi(
      0,
      "SEM_CONEXAO",
      "Não foi possível falar com o servidor. Verifique se a API está no ar.",
    );
  }

  const recebido = await resposta.text();
  return { enviado, recebido, resultado: lerResposta(recebido) };
}
