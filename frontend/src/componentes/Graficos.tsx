/**
 * Os gráficos do painel, feitos com CSS.
 *
 * São dois formatos: barras horizontais, para comparar categorias (massa por
 * destinação), e colunas, para a série dos últimos seis meses. Nenhum dos dois
 * precisa de biblioteca de gráficos: cada barra é uma `div` cuja largura (ou
 * altura) é uma porcentagem do maior valor da série. Uma biblioteca de
 * gráficos somaria algumas centenas de kilobytes e uma API própria para
 * desenhar o que aqui são seis linhas de CSS.
 *
 * A barra é a parte visual; o valor vem escrito ao lado dela em todos os
 * casos, porque é o número que o usuário anota no relatório — não o
 * comprimento da barra.
 */

export interface Fatia {
  rotulo: string;
  valor: number;
  /** O valor já formatado para leitura, com unidade. */
  texto: string;
  /** Destinação que dispõe o resíduo em vez de recuperá-lo: outra cor. */
  disposicao?: boolean;
}

/**
 * Proporção do maior valor da lista, em porcentagem.
 *
 * Com todos os valores zerados não há escala possível, e qualquer divisão
 * daria `NaN`; nesse caso as barras ficam vazias, o que é a leitura correta.
 */
function proporcao(valor: number, maior: number): string {
  if (maior <= 0) return "0%";
  return `${(valor / maior) * 100}%`;
}

export function Barras({ fatias }: { fatias: Fatia[] }) {
  const maior = Math.max(...fatias.map((fatia) => fatia.valor), 0);

  return (
    <div className="barras">
      {fatias.map((fatia) => (
        <div key={fatia.rotulo}>
          <div className="barra-topo">
            <span>{fatia.rotulo}</span>
            <span className="numero">{fatia.texto}</span>
          </div>
          <div className="barra-trilha">
            <div
              className={fatia.disposicao === true ? "barra-preenchida disposicao" : "barra-preenchida"}
              style={{ width: proporcao(fatia.valor, maior) }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * A série mensal, em colunas.
 *
 * A última coluna é o mês corrente e aparece preenchida, porque é o único mês
 * ainda incompleto da série: comparar a altura dele com a dos anteriores
 * levaria a conclusões erradas sem esse aviso visual.
 */
export function Colunas({ fatias }: { fatias: Fatia[] }) {
  const maior = Math.max(...fatias.map((fatia) => fatia.valor), 0);

  return (
    <div className="serie">
      {fatias.map((fatia, indice) => (
        <div className="serie-coluna" key={fatia.rotulo}>
          <span className="serie-valor">{fatia.texto}</span>
          <div className="serie-area">
            <div
              className={indice === fatias.length - 1 ? "serie-haste cheia" : "serie-haste"}
              style={{ height: proporcao(fatia.valor, maior) }}
            />
          </div>
          <span className="serie-rotulo">{fatia.rotulo}</span>
        </div>
      ))}
    </div>
  );
}

/** Barra única repartida entre duas parcelas que somam o total. */
export function Proporcao({ parte, total }: { parte: number; total: number }) {
  const fatia = total <= 0 ? 0 : (parte / total) * 100;

  return (
    <div className="proporcao">
      <span className="cor-recuperacao" style={{ width: `${fatia}%` }} />
      <span className="cor-disposicao" style={{ width: `${100 - fatia}%` }} />
    </div>
  );
}
