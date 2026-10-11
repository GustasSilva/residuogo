/**
 * Camada de transporte: tudo o que o front-end faz pela rede passa por aqui.
 *
 * Usa `fetch` direto, sem biblioteca de requisição. São poucas chamadas, e
 * concentrá-las em um módulo resolve de uma vez três coisas que, soltas pelas
 * telas, apareceriam repetidas e inconsistentes:
 *
 * 1. o token JWT no cabeçalho `Authorization` de toda requisição;
 * 2. a tradução do erro RFC 7807 do backend em um `ErroDaApi` com `codigo` e
 *    lista de campos, que é o que as telas sabem exibir;
 * 3. o fim de sessão: um `401` em qualquer tela derruba o usuário para o
 *    login, porque o token expira em 8 horas e isso acontece em uso normal.
 */

import type { Pagina } from "./tipos";

/**
 * Endereço da API. Vem de variável de ambiente para que o mesmo código rode
 * apontando para outro servidor sem recompilação manual do endereço; o padrão
 * é o backend rodando na própria máquina. O cliente SOAP (`soap.ts`) parte
 * deste mesmo endereço.
 */
export const ENDERECO_DA_API = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000/api/v1";

const CHAVE_DO_TOKEN = "residuogo.token";

/**
 * Onde vem o dado das integrações externas, informado pelo backend no
 * cabeçalho `X-Fonte`. `cache-expirado` significa que o IBGE ou o ViaCEP não
 * respondeu e o sistema serviu o último dado conhecido — o usuário merece
 * saber disso antes de confiar no endereço preenchido.
 */
export type FonteDoDado = "api" | "cache" | "cache-expirado";

/** Um campo que o servidor recusou, dentro de um erro de validação. */
export interface ErroDeCampo {
  campo: string;
  mensagem: string;
}

/**
 * Erro previsto da API, já traduzido do corpo `application/problem+json`.
 *
 * `codigo` é a extensão que o backend criou justamente para o cliente decidir
 * o que fazer sem depender do texto da mensagem (que pode mudar).
 */
export class ErroDaApi extends Error {
  status: number;
  codigo: string;
  erros: ErroDeCampo[];

  constructor(status: number, codigo: string, mensagem: string, erros: ErroDeCampo[] = []) {
    super(mensagem);
    this.name = "ErroDaApi";
    this.status = status;
    this.codigo = codigo;
    this.erros = erros;
  }

  /** A mensagem referente a um campo do formulário, se houver. */
  doCampo(campo: string): string | undefined {
    return this.erros.find((erro) => erro.campo === campo)?.mensagem;
  }
}

/**
 * Garante um `ErroDaApi` a partir de qualquer falha capturada.
 *
 * Em um `catch` o TypeScript entrega `unknown`, e com razão: além dos erros
 * previstos da API, pode cair ali um defeito de programação (um `undefined`
 * acessado dentro do `then`). Tratar os dois igual esconderia o segundo, então
 * o inesperado chega à tela como erro genérico — e ao console como ele é.
 */
export function comoErroDaApi(falha: unknown): ErroDaApi {
  if (falha instanceof ErroDaApi) return falha;

  console.error(falha);
  return new ErroDaApi(0, "ERRO_INESPERADO", "Ocorreu um erro inesperado na aplicação.");
}

// --------------------------------------------------------------------------
// Token
// --------------------------------------------------------------------------

// O token fica no `localStorage` para sobreviver a um F5: sem isso, recarregar
// a página exigiria novo login, o que seria insuportável em uso real. A
// alternativa mais segura seria um cookie `HttpOnly`, inacessível ao
// JavaScript, mas ela exige o servidor emitindo e invalidando o cookie — uma
// troca consciente, registrada aqui porque é o tipo de decisão que não se
// deduz lendo o código.
let token: string | null = localStorage.getItem(CHAVE_DO_TOKEN);

export function definirToken(novo: string | null): void {
  token = novo;
  if (novo === null) {
    localStorage.removeItem(CHAVE_DO_TOKEN);
  } else {
    localStorage.setItem(CHAVE_DO_TOKEN, novo);
  }
}

export function temToken(): boolean {
  return token !== null;
}

// Avisado quando o servidor recusa o token. Quem registra é o provedor de
// sessão (`ProvedorDeSessao.tsx`): o cliente não conhece React nem rotas.
let aoPerderSessao: () => void = () => {};

export function quandoPerderSessao(callback: () => void): void {
  aoPerderSessao = callback;
}

// --------------------------------------------------------------------------
// Requisições
// --------------------------------------------------------------------------

interface Opcoes {
  metodo?: "GET" | "POST" | "PUT";
  corpo?: unknown;
}

function cabecalhos(temCorpo: boolean): HeadersInit {
  const montados: Record<string, string> = { Accept: "application/json" };
  if (temCorpo) montados["Content-Type"] = "application/json";
  if (token !== null) montados["Authorization"] = `Bearer ${token}`;
  return montados;
}

/**
 * Executa a requisição e devolve a resposta HTTP, já tendo tratado o que é
 * comum a todas: erro de rede, erro da API e sessão perdida.
 */
async function executar(caminho: string, opcoes: Opcoes): Promise<Response> {
  const temCorpo = opcoes.corpo !== undefined;

  let resposta: Response;
  try {
    resposta = await fetch(`${ENDERECO_DA_API}${caminho}`, {
      method: opcoes.metodo ?? "GET",
      headers: cabecalhos(temCorpo),
      body: temCorpo ? JSON.stringify(opcoes.corpo) : undefined,
    });
  } catch {
    // `fetch` só rejeita quando a requisição não chegou a acontecer: servidor
    // fora do ar, DNS, CORS. Nenhuma dessas é culpa do usuário, e a mensagem
    // precisa dizer o que ele pode fazer.
    throw new ErroDaApi(
      0,
      "SEM_CONEXAO",
      "Não foi possível falar com o servidor. Verifique se a API está no ar.",
    );
  }

  if (resposta.ok) return resposta;

  // Token ausente, inválido ou expirado: a sessão acabou, em qualquer tela.
  // Só vale quando havia token — um 401 na tela de login é senha errada.
  if (resposta.status === 401 && token !== null) {
    aoPerderSessao();
  }

  throw await traduzirErro(resposta);
}

/** Converte o corpo `application/problem+json` em `ErroDaApi`. */
async function traduzirErro(resposta: Response): Promise<ErroDaApi> {
  let problema: Record<string, unknown> = {};
  try {
    problema = await resposta.json();
  } catch {
    // Erro sem corpo JSON (um 502 de proxy, por exemplo): sobra o status.
  }

  return new ErroDaApi(
    resposta.status,
    typeof problema.codigo === "string" ? problema.codigo : "ERRO_INESPERADO",
    typeof problema.detail === "string"
      ? problema.detail
      : `O servidor respondeu ${resposta.status}.`,
    Array.isArray(problema.erros) ? (problema.erros as ErroDeCampo[]) : [],
  );
}

/** Requisição que devolve JSON. É a forma usada pela maioria das telas. */
export async function pedir<Dado>(caminho: string, opcoes: Opcoes = {}): Promise<Dado> {
  const resposta = await executar(caminho, opcoes);
  if (resposta.status === 204) return undefined as Dado;
  return (await resposta.json()) as Dado;
}

/**
 * Igual à anterior, mas informando de onde veio o dado (cabeçalho `X-Fonte`).
 * Usada apenas nas consultas ao IBGE e ao ViaCEP, as únicas que dependem de
 * um serviço de terceiro.
 */
export async function pedirComFonte<Dado>(
  caminho: string,
): Promise<{ valor: Dado; fonte: FonteDoDado | null }> {
  const resposta = await executar(caminho, {});
  return {
    valor: (await resposta.json()) as Dado,
    fonte: resposta.headers.get("X-Fonte") as FonteDoDado | null,
  };
}

/**
 * Baixa um arquivo gerado pela API (PDF ou CSV).
 *
 * Um `<a href>` apontando direto para a rota não funcionaria: o navegador
 * seguiria o link sem o cabeçalho `Authorization`, e a API responderia 401.
 * Então o arquivo é buscado como qualquer outra requisição e entregue ao
 * navegador a partir da memória, por um link temporário.
 *
 * `abrirEmAba` distingue os dois casos: o PDF abre no visualizador, porque
 * quem pede quer conferir antes de guardar; o CSV baixa, porque o navegador
 * não tem o que mostrar.
 */
export async function baixarArquivo(
  caminho: string,
  nome: string,
  abrirEmAba = false,
): Promise<void> {
  const resposta = await executar(caminho, {});
  const endereco = URL.createObjectURL(await resposta.blob());

  // Abrir uma aba depois de uma espera pode ser barrado pelo bloqueador de
  // pop-ups: para o navegador, só é "pedido do usuário" o que acontece logo
  // após o clique, e gerar o documento leva algum tempo. Quando isso acontece,
  // `window.open` devolve nulo e o arquivo é baixado — um download nunca é
  // bloqueado, e o usuário fica com o documento de qualquer forma.
  const aba = abrirEmAba ? window.open(endereco, "_blank", "noopener") : null;

  if (aba === null) {
    const ancora = document.createElement("a");
    ancora.href = endereco;
    ancora.download = nome;
    document.body.appendChild(ancora);
    ancora.click();
    ancora.remove();
  }

  // Revogar imediatamente cancelaria o download que acabou de começar; um
  // minuto é tempo de sobra para o navegador ter lido o conteúdo.
  window.setTimeout(() => URL.revokeObjectURL(endereco), 60_000);
}

/**
 * Busca uma imagem da API e devolve um endereço que o `<img>` consegue usar.
 *
 * Mesmo motivo do arquivo acima: a rota do QR code exige autenticação, e o
 * `src` de uma imagem é carregado pelo navegador sem o cabeçalho
 * `Authorization`. Quem chama precisa liberar o endereço depois (com
 * `URL.revokeObjectURL`), e por isso a tela guarda esse valor no seu estado.
 */
export async function pedirImagem(caminho: string): Promise<string> {
  const resposta = await executar(caminho, {});
  return URL.createObjectURL(await resposta.blob());
}

/**
 * Monta a parte de consulta da URL, descartando filtros vazios.
 *
 * Mandar `status=` vazio não é o mesmo que não mandar `status`: o primeiro
 * faria o FastAPI recusar a requisição por valor inválido de enumeração.
 */
export function consulta(parametros: Record<string, string | number | undefined | null>): string {
  const partes = new URLSearchParams();
  for (const [nome, valor] of Object.entries(parametros)) {
    if (valor !== undefined && valor !== null && valor !== "") {
      partes.set(nome, String(valor));
    }
  }
  const texto = partes.toString();
  return texto === "" ? "" : `?${texto}`;
}

/**
 * Busca uma listagem inteira, para alimentar campos de seleção.
 *
 * As listagens da API são paginadas em no máximo 100 registros por página,
 * limite que protege o servidor. Os catálogos usados nos formulários — tipos
 * de resíduo, organizações aptas — são bem menores que isso, então uma única
 * página basta; o limite fica explícito aqui em vez de escondido em cada tela.
 */
export async function pedirCatalogo<Item>(
  caminho: string,
  parametros: Record<string, string | number | undefined> = {},
): Promise<Item[]> {
  const pagina = await pedir<Pagina<Item>>(
    `${caminho}${consulta({ ...parametros, tamanho: 100 })}`,
  );
  return pagina.itens;
}
