/**
 * Conversão de valores da API para o que a tela mostra.
 *
 * A API fala em formatos técnicos — número com ponto decimal, data em ISO
 * 8601, CNPJ só com dígitos — e a tela precisa do formato brasileiro. Reunir
 * essas conversões aqui evita que a mesma data apareça escrita de duas formas
 * em duas telas.
 */

/** Usado onde o dado é opcional e não há o que mostrar. */
const VAZIO = "—";

/**
 * Número no formato brasileiro: ponto nos milhares, vírgula nos decimais.
 *
 * Três casas é o padrão dos relatórios do backend, e não é exagero: massa em
 * toneladas convertida para quilos, ou volume em litros convertido para metros
 * cúbicos, produz valores em que a terceira casa é significativa (1000 L =
 * 1,000 m³).
 */
export function numero(valor: number, casas = 3): string {
  return valor.toLocaleString("pt-BR", {
    minimumFractionDigits: casas,
    maximumFractionDigits: casas,
  });
}

export function inteiro(valor: number): string {
  return valor.toLocaleString("pt-BR");
}

/**
 * Massa ou volume em um cartão de indicador.
 *
 * Em um número grande as casas decimais só atrapalham a leitura, e o cartão
 * não é o lugar de conferir precisão — as tabelas e o CSV mostram o valor
 * cheio. Em um número pequeno, ao contrário, arredondar para inteiro poderia
 * transformar 0,4 kg em "0".
 */
export function grandeza(valor: number): string {
  return numero(valor, valor >= 100 ? 0 : 3);
}

export function percentual(valor: number | null, casas = 1): string {
  if (valor === null) return VAZIO;
  return `${numero(valor, casas)}%`;
}

/**
 * Converte uma data em `AAAA-MM-DD` para o fuso local, campo por campo.
 *
 * `new Date("2026-10-09")` é interpretado pelo JavaScript como meia-noite em
 * UTC; no Brasil isso cai às 21h do dia anterior, e a tela mostraria 08/10.
 * Montar a data com ano, mês e dia separados evita o erro — que é silencioso
 * e, por aparecer só perto da virada do dia, difícil de notar depois.
 */
function dataLocal(texto: string): Date {
  const [ano, mes, dia] = texto.split("-").map(Number);
  return new Date(ano, mes - 1, dia);
}

/** Data em `AAAA-MM-DD` (o tipo `date` da API) como 09/10/2026. */
export function data(texto: string | null): string {
  if (!texto) return VAZIO;
  return dataLocal(texto).toLocaleDateString("pt-BR");
}

/**
 * Data e hora em ISO 8601 (o tipo `datetime` da API) como 09/10/2026 14:32.
 *
 * Aqui o texto traz o fuso, então o próprio `Date` resolve a conversão para o
 * horário local — o backend guarda tudo em UTC de propósito.
 */
export function dataEHora(texto: string | null): string {
  if (!texto) return VAZIO;
  return new Date(texto).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Mês de referência de uma barra do gráfico: "out/26". */
export function mesCurto(texto: string): string {
  const momento = dataLocal(texto);
  const mes = momento.toLocaleDateString("pt-BR", { month: "short" }).replace(".", "");
  return `${mes}/${String(momento.getFullYear()).slice(2)}`;
}

/** Data de hoje em `AAAA-MM-DD`, que é o formato do `<input type="date">`. */
export function hoje(): string {
  const agora = new Date();
  const mes = String(agora.getMonth() + 1).padStart(2, "0");
  const dia = String(agora.getDate()).padStart(2, "0");
  return `${agora.getFullYear()}-${mes}-${dia}`;
}

export function cnpj(digitos: string): string {
  if (digitos.length !== 14) return digitos;
  return digitos.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");
}

export function cep(digitos: string): string {
  if (digitos.length !== 8) return digitos;
  return `${digitos.slice(0, 5)}-${digitos.slice(5)}`;
}

/** Mantém apenas os dígitos do que foi digitado, para enviar à API. */
export function somenteDigitos(texto: string): string {
  return texto.replace(/\D/g, "");
}
