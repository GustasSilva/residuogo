// Pagina de consulta: conversa so com o web service do proprio projeto (/api).

const LIMITES_DE_GOIAS = [[-19.5, -53.25], [-12.4, -45.9]];
const ESTILO_DA_ORIGEM = { radius: 7, color: "#fff", weight: 2, fillColor: "#000", fillOpacity: 1 };
const PARECE_CEP = /^[\d\s.-]+$/;

const formulario = document.getElementById("busca");
const campoLocal = document.getElementById("local");
const campoMaterial = document.getElementById("material");
const campoRaio = document.getElementById("raio");
const botaoBuscar = document.getElementById("buscar");
const mensagem = document.getElementById("mensagem");
const cabecalho = document.getElementById("cabecalho");
const avisos = document.getElementById("avisos");
const instrucao = document.getElementById("instrucao");
const tabela = document.getElementById("tabela");
const linhas = document.getElementById("linhas");

let mapa = null;
let camadaDaBusca = null;
let marcadores = [];
let selecionado = null;
let origemAtual = null; // o que esta sendo buscado: { local } ou { lat, lon }
let buscaEmAndamento = null;

// Tudo que vem do mapa aberto entra na pagina como texto, nunca como HTML.
function criar(tag, atributos = {}, ...filhos) {
  const elemento = document.createElement(tag);
  Object.assign(elemento, atributos);
  elemento.append(...filhos);
  return elemento;
}

function mostrarMensagem(texto, ehErro = false) {
  mensagem.textContent = texto;
  mensagem.className = ehErro ? "erro" : "";
}

function indicarBusca(buscando) {
  document.body.classList.toggle("buscando", buscando);
  botaoBuscar.disabled = buscando;
  botaoBuscar.textContent = buscando ? "Buscando..." : "Buscar pontos";
}

// APS-TRECHO 8: A pagina consumindo o web service
async function chamarApi(caminho, opcoes) {
  let resposta;
  try {
    resposta = await fetch(caminho, opcoes);
  } catch (erro) {
    if (erro.name === "AbortError") throw erro;
    throw new Error("O servidor do ResíduoGO não respondeu. Verifique se ele está ligado.");
  }
  const corpo = await resposta.json().catch(() => null);
  if (!resposta.ok) {
    throw new Error(corpo?.detail ?? "A consulta falhou. Tente novamente.");
  }
  return corpo;
}

function parametrosDaBusca(origem) {
  const parametros = new URLSearchParams({ raio_km: campoRaio.value, ...origem });
  if (campoMaterial.value) parametros.set("material", campoMaterial.value);
  return parametros;
}

async function buscar(origem) {
  // Uma busca nova cancela a anterior, para a resposta antiga nao sobrescrever a nova.
  buscaEmAndamento?.abort();
  const busca = new AbortController();
  buscaEmAndamento = busca;
  const origemAnterior = origemAtual;
  origemAtual = origem;

  const parametros = parametrosDaBusca(origem);
  indicarBusca(true);
  mostrarMensagem("Procurando pontos...");
  const demora = setTimeout(() => {
    mostrarMensagem("O OpenStreetMap está demorando. Se ele não responder, usamos os dados guardados.");
  }, 3000);

  try {
    const dados = await chamarApi(`/api/pontos?${parametros}`, { signal: busca.signal });
    if (busca.signal.aborted) return;
    if (origem.lat) campoLocal.value = "";
    mostrarMensagem("");
    mostrarResultado(dados, parametros);
  } catch (erro) {
    if (erro.name === "AbortError") return;
    origemAtual = origemAnterior;
    mostrarMensagem(erro.message, true);
  } finally {
    clearTimeout(demora);
    if (buscaEmAndamento === busca) indicarBusca(false);
  }
}
// APS-FIM

function limpar() {
  buscaEmAndamento?.abort();
  buscaEmAndamento = null;
  origemAtual = null;
  selecionado = null;
  marcadores = [];

  formulario.reset();
  indicarBusca(false);
  mostrarMensagem("");
  cabecalho.hidden = true;
  avisos.replaceChildren();
  linhas.replaceChildren();
  tabela.hidden = true;
  instrucao.hidden = false;

  if (mapa) {
    camadaDaBusca.clearLayers();
    mapa.fitBounds(LIMITES_DE_GOIAS);
  }
  campoLocal.focus();
}

function mostrarResultado(dados, parametros) {
  cabecalho.hidden = false;
  instrucao.hidden = true;
  selecionado = null;

  const local = dados.origem.precisao === "mapa" ? "do ponto escolhido no mapa" : `de ${dados.origem.descricao}`;
  document.getElementById("resumo").textContent = tituloDoResultado(dados, local);

  const linkCsv = document.getElementById("csv");
  linkCsv.href = `/api/pontos.csv?${parametros}`;
  linkCsv.hidden = dados.total === 0;

  const textos = [...dados.avisos];
  if (dados.fora_do_raio && dados.total > 0) {
    textos.unshift(`Não há pontos até ${dados.raio_km} km. A lista mostra os mais próximos, mesmo que mais longe.`);
  }
  if (PARECE_CEP.test(parametros.get("local") ?? "") && dados.origem.precisao !== "endereço") {
    textos.push(`A rua não foi localizada no mapa. As distâncias contam a partir do ${dados.origem.precisao}.`);
  }
  avisos.replaceChildren(...textos.map((texto) => criar("p", { className: "aviso", textContent: texto })));

  linhas.replaceChildren(...dados.pontos.map(criarLinha));
  tabela.hidden = dados.total === 0;

  // Um problema no mapa nao pode esconder a lista, que ja esta pronta.
  try {
    desenharResultadoNoMapa(dados);
  } catch (erro) {
    console.error(erro);
  }
}

function tituloDoResultado(dados, local) {
  if (dados.total === 0) return `Nenhum ponto aceita esse material perto ${local}`;
  if (dados.fora_do_raio) {
    return dados.total === 1 ? `O ponto mais próximo ${local}` : `Os ${dados.total} pontos mais próximos ${local}`;
  }
  const quantidade = dados.total === 1 ? "1 ponto" : `${dados.total} pontos`;
  return `${quantidade} até ${dados.raio_km} km ${local}`;
}

function criarLinha(ponto, indice) {
  const nome = criar("button", {
    type: "button",
    className: "nome-ponto",
    textContent: ponto.nome,
    onclick: () => selecionar(indice),
  });

  const celulaPonto = criar("td", {}, nome);
  for (const texto of [
    ponto.nome.includes(ponto.tipo) ? "" : ponto.tipo,
    ponto.endereco,
    ponto.horario,
    ponto.telefone,
    ponto.observacao,
  ]) {
    if (texto) celulaPonto.append(criar("span", { className: "detalhe", textContent: texto }));
  }
  celulaPonto.append(criarMateriais(ponto.materiais));

  const rota = `https://www.google.com/maps/dir/?api=1&destination=${ponto.latitude},${ponto.longitude}`;
  celulaPonto.append(
    criar("span", { className: "detalhe" },
      criar("a", { href: rota, target: "_blank", rel: "noopener", textContent: "Como chegar" })),
  );

  return criar("tr", {
    id: `linha-${indice}`,
    onmouseenter: () => destacarNoMapa(indice),
    onmouseleave: () => destacarNoMapa(selecionado),
  },
    criar("td", { className: "numero", textContent: indice + 1 }),
    celulaPonto,
    criar("td", { className: "distancia", textContent: textoDaDistancia(ponto) }),
  );
}

function textoDaDistancia(ponto) {
  return `${ponto.distancia_km.toLocaleString("pt-BR")} km`;
}

function criarMateriais(materiais) {
  if (materiais.length === 0) {
    return criar("span", { className: "detalhe", textContent: "Materiais aceitos não informados." });
  }
  return criar("ul", { className: "materiais" },
    ...materiais.map((material) =>
      criar("li", {},
        criar("span", { className: `cor cor-${material.chave}` }),
        criar("span", { textContent: material.rotulo }),
      ),
    ),
  );
}

function iniciarMapa() {
  const areaMapa = document.getElementById("mapa");
  if (!window.L) {
    areaMapa.textContent = "Não foi possível carregar o mapa. A busca pelo campo acima continua funcionando.";
    return;
  }

  // Com o fechamento automatico, clicar no mapa com um ponto aberto so fecharia o ponto.
  mapa = L.map(areaMapa, { closePopupOnClick: false }).fitBounds(LIMITES_DE_GOIAS);
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; colaboradores do OpenStreetMap",
  }).addTo(mapa);
  camadaDaBusca = L.layerGroup().addTo(mapa);

  mapa.on("click", (evento) => {
    // Marca o local na hora, para o clique ter resposta antes de a busca terminar.
    const marca = L.circleMarker(evento.latlng, { ...ESTILO_DA_ORIGEM, interactive: false }).addTo(mapa);
    const ponto = { lat: evento.latlng.lat.toFixed(5), lon: evento.latlng.lng.toFixed(5) };
    buscar(ponto).finally(() => marca.remove());
  });

  chamarApi("/api/goias").then((contorno) => {
    L.geoJSON(contorno, {
      style: { color: "#0b5ea8", weight: 2, fill: false, interactive: false },
    }).addTo(mapa);
  }).catch(() => {
    // O contorno so ajuda a enxergar o estado: a busca funciona sem ele.
  });
}

function desenharResultadoNoMapa(dados) {
  if (!mapa) return;

  camadaDaBusca.clearLayers();
  const origem = [dados.origem.latitude, dados.origem.longitude];
  L.circle(origem, {
    radius: dados.raio_km * 1000,
    color: "#5c5c5c",
    weight: 1,
    fill: false,
    interactive: false,
  }).addTo(camadaDaBusca);
  L.circleMarker(origem, ESTILO_DA_ORIGEM).bindTooltip("Local da busca").addTo(camadaDaBusca);

  marcadores = dados.pontos.map((ponto, indice) => {
    const marcador = L.marker([ponto.latitude, ponto.longitude], {
      icon: iconeNumerado(indice + 1, false),
      title: ponto.nome,
    });
    marcador.bindPopup(
      criar("div", {},
        criar("strong", { textContent: `${indice + 1}. ${ponto.nome}` }),
        criar("div", { textContent: textoDaDistancia(ponto) }),
      ),
    );
    marcador.on("click", () => selecionar(indice, true));
    return marcador.addTo(camadaDaBusca);
  });

  // Os mais proximos podem ficar fora do circulo: o mapa precisa mostrar todos.
  const area = L.latLng(origem).toBounds(dados.raio_km * 2000);
  marcadores.forEach((marcador) => area.extend(marcador.getLatLng()));
  mapa.fitBounds(area);
}

function iconeNumerado(numero, ativo) {
  return L.divIcon({
    className: "",
    html: `<span class="marcador${ativo ? " ativo" : ""}">${numero}</span>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
    popupAnchor: [0, -12],
  });
}

function destacarNoMapa(indice) {
  marcadores.forEach((marcador, posicao) => {
    marcador.setIcon(iconeNumerado(posicao + 1, posicao === indice));
    marcador.setZIndexOffset(posicao === indice ? 1000 : 0);
  });
}

function selecionar(indice, veioDoMapa = false) {
  selecionado = indice;
  document.querySelector("tr.selecionada")?.classList.remove("selecionada");
  const linha = document.getElementById(`linha-${indice}`);
  linha.classList.add("selecionada");
  destacarNoMapa(indice);

  if (veioDoMapa) {
    linha.scrollIntoView({ block: "nearest" });
  } else {
    marcadores[indice]?.openPopup();
  }
}

async function carregarMunicipios() {
  try {
    const municipios = await chamarApi("/api/municipios");
    document.getElementById("municipios").replaceChildren(
      ...municipios.map((m) => criar("option", { value: m.nome, label: `Região de ${m.regiao}` })),
    );
  } catch {
    // Sem as sugestoes, digitar continua funcionando.
  }
}

async function carregarMateriais() {
  try {
    const materiais = await chamarApi("/api/materiais");
    campoMaterial.append(
      ...materiais.map((m) => criar("option", { value: m.chave, textContent: m.rotulo })),
    );
  } catch {
    // Sem a lista, a busca continua funcionando com "Qualquer material".
  }
}

campoLocal.addEventListener("input", (evento) => {
  if (PARECE_CEP.test(campoLocal.value)) {
    // O CEP busca sozinho quando fica completo.
    const digitos = campoLocal.value.replace(/\D/g, "").slice(0, 8);
    campoLocal.value = digitos.length > 5 ? `${digitos.slice(0, 5)}-${digitos.slice(5)}` : digitos;
    if (digitos.length === 8) buscar({ local: campoLocal.value });
    return;
  }

  // Escolher um municipio nas sugestoes busca na hora. O resto espera o Enter ou o
  // botao, porque o Nominatim nao permite uma consulta a cada letra digitada.
  const escolheuNaLista = !evento.inputType || evento.inputType === "insertReplacementText";
  if (escolheuNaLista && campoLocal.value.trim()) buscar({ local: campoLocal.value.trim() });
});

// Mudar um filtro refaz a busca atual.
for (const filtro of [campoMaterial, campoRaio]) {
  filtro.addEventListener("change", () => {
    if (origemAtual) buscar(origemAtual);
  });
}

formulario.addEventListener("submit", (evento) => {
  evento.preventDefault();
  const texto = campoLocal.value.trim();
  if (texto) {
    buscar({ local: texto });
  } else if (origemAtual) {
    buscar(origemAtual);
  } else {
    mostrarMensagem("Digite um local ou clique no mapa.", true);
    campoLocal.focus();
  }
});

document.getElementById("limpar").addEventListener("click", limpar);

iniciarMapa();
carregarMunicipios();
carregarMateriais();
