// Pagina de consulta: conversa so com o web service do proprio projeto (/api).

const campoCep = document.getElementById("cep");
const campoMunicipio = document.getElementById("municipio");
const campoMaterial = document.getElementById("material");
const campoRaio = document.getElementById("raio");
const botao = document.getElementById("buscar");
const mensagem = document.getElementById("mensagem");
const areaResultado = document.getElementById("resultado");

let mapa = null;
let camadaPontos = null;
let marcadores = [];

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

// APS-TRECHO 7: A pagina consumindo o web service
async function chamarApi(caminho) {
  let resposta;
  try {
    resposta = await fetch(caminho);
  } catch {
    throw new Error("O servidor do ResíduoGO não respondeu. Verifique se ele está ligado.");
  }
  const corpo = await resposta.json().catch(() => null);
  if (!resposta.ok) {
    throw new Error(corpo?.detail ?? "A consulta falhou. Tente novamente.");
  }
  return corpo;
}

function parametrosDaBusca() {
  const parametros = new URLSearchParams({ raio_km: campoRaio.value });
  if (campoCep.value.trim()) parametros.set("cep", campoCep.value.trim());
  if (campoMunicipio.value) parametros.set("municipio", campoMunicipio.value);
  if (campoMaterial.value) parametros.set("material", campoMaterial.value);
  return parametros;
}

async function buscar(evento) {
  evento.preventDefault();

  if (!campoCep.value.trim() && !campoMunicipio.value) {
    mostrarMensagem("Informe um CEP ou escolha um município.", true);
    campoCep.focus();
    return;
  }

  botao.disabled = true;
  botao.textContent = "Buscando...";
  mostrarMensagem("Consultando os pontos. Pode levar até 20 segundos.");

  try {
    const parametros = parametrosDaBusca();
    const dados = await chamarApi(`/api/pontos?${parametros}`);
    mostrarMensagem("");
    mostrarResultado(dados, parametros);
  } catch (erro) {
    areaResultado.hidden = true;
    mostrarMensagem(erro.message, true);
  } finally {
    botao.disabled = false;
    botao.textContent = "Buscar pontos";
  }
}
// APS-FIM

function mostrarResultado(dados, parametros) {
  areaResultado.hidden = false;

  const quantidade = dados.total === 1 ? "1 ponto" : `${dados.total} pontos`;
  document.getElementById("resumo").textContent =
    dados.total === 0
      ? `Nenhum ponto até ${dados.raio_km} km de ${dados.origem.descricao}`
      : `${quantidade} até ${dados.raio_km} km de ${dados.origem.descricao}`;

  const linkCsv = document.getElementById("csv");
  linkCsv.href = `/api/pontos.csv?${parametros}`;
  linkCsv.hidden = dados.total === 0;

  const avisos = [...dados.avisos];
  if (dados.total === 0) {
    avisos.unshift("Aumente a distância ou procure por outro município.");
  }
  if (parametros.has("cep") && dados.origem.precisao !== "endereço") {
    avisos.push(`A rua não foi localizada no mapa. As distâncias contam a partir do ${dados.origem.precisao}.`);
  }
  document.getElementById("avisos").replaceChildren(
    ...avisos.map((aviso) => criar("p", { className: "aviso", textContent: aviso })),
  );

  document.getElementById("linhas").replaceChildren(...dados.pontos.map(criarLinha));
  document.getElementById("tabela").hidden = dados.total === 0;

  // Um problema no mapa nao pode esconder a lista, que ja esta pronta.
  try {
    desenharMapa(dados);
  } catch (erro) {
    console.error(erro);
    document.getElementById("mapa").textContent = "Não foi possível desenhar o mapa. A lista continua valendo.";
  }
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

  return criar("tr", { id: `linha-${indice}` },
    criar("td", { className: "numero", textContent: indice + 1 }),
    celulaPonto,
    criar("td", { className: "distancia", textContent: `${ponto.distancia_km.toLocaleString("pt-BR")} km` }),
  );
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

function desenharMapa(dados) {
  const areaMapa = document.getElementById("mapa");
  if (!window.L) {
    areaMapa.textContent = "Não foi possível carregar o mapa. A lista continua valendo.";
    return;
  }

  if (!mapa) {
    mapa = L.map(areaMapa);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; colaboradores do OpenStreetMap",
    }).addTo(mapa);
    camadaPontos = L.layerGroup().addTo(mapa);
  }

  camadaPontos.clearLayers();
  const origem = [dados.origem.latitude, dados.origem.longitude];
  L.circle(origem, {
    radius: dados.raio_km * 1000,
    color: "#5c5c5c",
    weight: 1,
    fill: false,
    interactive: false,
  }).addTo(camadaPontos);
  L.circleMarker(origem, { radius: 7, color: "#fff", weight: 2, fillColor: "#000", fillOpacity: 1 })
    .bindTooltip("Local da busca")
    .addTo(camadaPontos);

  marcadores = dados.pontos.map((ponto, indice) => {
    const marcador = L.marker([ponto.latitude, ponto.longitude], {
      icon: iconeNumerado(indice + 1, false),
      title: ponto.nome,
    });
    marcador.bindPopup(criar("strong", { textContent: `${indice + 1}. ${ponto.nome}` }));
    marcador.on("click", () => selecionar(indice, false));
    return marcador.addTo(camadaPontos);
  });

  // O mapa pode ter nascido com a secao escondida e precisa remedir o espaco.
  mapa.invalidateSize();
  mapa.fitBounds(L.latLng(origem).toBounds(dados.raio_km * 2000));
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

function selecionar(indice, abrirNoMapa = true) {
  document.querySelector("tr.selecionada")?.classList.remove("selecionada");
  document.getElementById(`linha-${indice}`)?.classList.add("selecionada");

  marcadores.forEach((marcador, posicao) => {
    marcador.setIcon(iconeNumerado(posicao + 1, posicao === indice));
  });

  if (abrirNoMapa && marcadores[indice]) {
    marcadores[indice].openPopup();
  }
}

async function carregarMunicipios() {
  try {
    const municipios = await chamarApi("/api/municipios");
    const regioes = new Map();
    for (const municipio of municipios) {
      if (!regioes.has(municipio.regiao)) regioes.set(municipio.regiao, []);
      regioes.get(municipio.regiao).push(municipio);
    }
    const grupos = [...regioes.keys()].sort((a, b) => a.localeCompare(b, "pt-BR")).map((regiao) =>
      criar("optgroup", { label: `Região de ${regiao}` },
        ...regioes.get(regiao).map((m) => criar("option", { value: m.codigo, textContent: m.nome })),
      ),
    );
    campoMunicipio.replaceChildren(criar("option", { value: "", textContent: "Escolha um município" }), ...grupos);
  } catch (erro) {
    campoMunicipio.replaceChildren(criar("option", { value: "", textContent: "Lista indisponível, use o CEP" }));
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

campoCep.addEventListener("input", () => {
  const digitos = campoCep.value.replace(/\D/g, "").slice(0, 8);
  campoCep.value = digitos.length > 5 ? `${digitos.slice(0, 5)}-${digitos.slice(5)}` : digitos;
  if (digitos) campoMunicipio.value = "";
});

campoMunicipio.addEventListener("change", () => {
  if (campoMunicipio.value) campoCep.value = "";
});

document.getElementById("busca").addEventListener("submit", buscar);

carregarMunicipios();
carregarMateriais();
