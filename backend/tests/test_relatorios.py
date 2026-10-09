"""Testes dos relatórios, dos documentos gerados e do painel.

O cenário é montado com números redondos de propósito — 2 t, 500 kg e 1000 L —
para que os totais esperados possam ser conferidos de cabeça, e para que uma
conta errada apareça como um número errado, e não como uma diferença de
arredondamento difícil de julgar.

O que cada bloco cobre:

* `TestResumo`      - os totais, a separação entre massa e volume e o período;
* `TestDivergencias`- a contagem de itens fora da tolerância de 5% (RN05);
* `TestVisibilidade`- a regra RN07 aplicada a relatório e documento;
* `TestCsv`         - formato do arquivo e uma linha por item;
* `TestPdf`         - o conteúdo dos dois PDFs, lido de volta do arquivo;
* `TestQrCode`      - a imagem e o endereço que ela carrega;
* `TestPainel`      - os indicadores, inclusive o desvio de aterro.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.database import agora_utc
from app.documentos import qr
from app.enums import ClasseResiduo, PerfilUsuario, UnidadeMedida
from app.models import Manifesto, TipoResiduo, Usuario
from app.security import gerar_hash_senha
from tests.conftest import SENHA_TESTE, autenticar
from tests.test_autenticacao import conferir_formato_do_problema
from tests.test_manifestos import corpo_de_emissao, emitir, executar

RESUMO = "/api/v1/relatorios/resumo"
RESUMO_PDF = "/api/v1/relatorios/resumo.pdf"
CSV = "/api/v1/relatorios/manifestos.csv"
INDICADORES = "/api/v1/dashboard/indicadores"


@pytest.fixture
def oleo(sessao: Session) -> TipoResiduo:
    """Um segundo resíduo, de outra classe e medido em volume.

    O catálogo padrão dos testes tem um único tipo, em tonelada. Sem um
    segundo tipo não dá para verificar o agrupamento por classe nem a
    separação entre massa e volume, que é a decisão central do relatório.
    """
    tipo = TipoResiduo(
        codigo="130205",
        descricao="Óleo lubrificante usado",
        classe=ClasseResiduo.I,
        unidade_padrao=UnidadeMedida.L,
    )
    sessao.add(tipo)
    sessao.commit()
    return tipo


def destinar(
    cliente: TestClient,
    dados: dict,
    *,
    quantidade: float,
    unidade: str,
    destinacao: str,
    tipo_residuo_id: int | None = None,
    recebida: float | None = None,
) -> dict:
    """Emite um manifesto e o leva até a destinação final.

    Só manifestos destinados entram no resumo, então todo cenário de
    relatório precisa percorrer o fluxo inteiro. `recebida` permite conferir
    uma quantidade diferente da declarada, que é como se produz uma
    divergência.
    """
    manifesto = emitir(
        cliente,
        dados,
        itens=[
            {
                "tipo_residuo_id": tipo_residuo_id or dados["tipo_residuo"].id,
                "quantidade_declarada": quantidade,
                "unidade": unidade,
                "acondicionamento": "CACAMBA",
            }
        ],
    )
    identificador = manifesto["id"]
    item = manifesto["itens"][0]

    assert executar(cliente, "transportador@teste.com.br", identificador, "coleta").status_code == 200
    assert executar(
        cliente,
        "destinador@teste.com.br",
        identificador,
        "recebimento",
        {"itens": [{"item_id": item["id"], "quantidade_recebida": recebida or quantidade}]},
    ).status_code == 200
    assert executar(
        cliente,
        "destinador@teste.com.br",
        identificador,
        "destinacao",
        {"tipo_destinacao": destinacao},
    ).status_code == 200

    return manifesto


@pytest.fixture
def cenario(cliente: TestClient, dados: dict, oleo: TipoResiduo) -> dict:
    """Três manifestos destinados, com totais conferíveis de cabeça.

    * 2 t recicladas      -> 2.000 kg de massa recuperada
    * 500 kg aterrados    ->   500 kg de massa disposta
    * 1.000 L coprocessados -> 1 m3 de volume (nenhuma massa)

    Massa total 2.500 kg, dos quais 2.000 kg recuperados: desvio de aterro de
    80%. O óleo não entra nessa conta porque é volume, e somá-lo à massa
    exigiria arbitrar uma densidade.
    """
    reciclado = destinar(cliente, dados, quantidade=2, unidade="T", destinacao="RECICLAGEM")
    aterrado = destinar(cliente, dados, quantidade=500, unidade="KG", destinacao="ATERRO")
    coprocessado = destinar(
        cliente,
        dados,
        quantidade=1000,
        unidade="L",
        destinacao="COPROCESSAMENTO",
        tipo_residuo_id=oleo.id,
    )

    return {"reciclado": reciclado, "aterrado": aterrado, "coprocessado": coprocessado}


def linha(linhas: list[dict], chave: str) -> dict:
    """Localiza uma linha do relatório pela chave do grupo."""
    encontrada = [atual for atual in linhas if atual["chave"] == chave]
    assert encontrada, f"a chave {chave} não apareceu no relatório"
    return encontrada[0]


class TestResumo:
    def test_totais_do_periodo(self, cliente: TestClient, cenario: dict) -> None:
        """2 t + 500 kg = 2.500 kg; os 1.000 L viram 1 m3, em coluna própria."""
        corpo = cliente.get(RESUMO, headers=autenticar(cliente, "admin@teste.com.br")).json()

        assert corpo["total"]["massa_kg"] == 2500.0
        assert corpo["total"]["volume_m3"] == 1.0
        assert corpo["total"]["manifestos"] == 3
        assert corpo["total"]["itens"] == 3

    def test_massa_e_volume_nao_se_misturam(
        self, cliente: TestClient, cenario: dict
    ) -> None:
        """O óleo aparece só em volume; os demais, só em massa."""
        corpo = cliente.get(RESUMO, headers=autenticar(cliente, "admin@teste.com.br")).json()

        oleo = linha(corpo["por_tipo"], "130205")
        assert oleo["massa_kg"] == 0.0
        assert oleo["volume_m3"] == 1.0

        outro = linha(corpo["por_tipo"], "020202")
        assert outro["massa_kg"] == 2500.0
        assert outro["volume_m3"] == 0.0

    def test_agrupamento_por_classe(self, cliente: TestClient, cenario: dict) -> None:
        corpo = cliente.get(RESUMO, headers=autenticar(cliente, "admin@teste.com.br")).json()

        assert linha(corpo["por_classe"], "IIA")["massa_kg"] == 2500.0
        assert linha(corpo["por_classe"], "I")["volume_m3"] == 1.0

    def test_agrupamento_por_destinacao(self, cliente: TestClient, cenario: dict) -> None:
        corpo = cliente.get(RESUMO, headers=autenticar(cliente, "admin@teste.com.br")).json()

        assert linha(corpo["por_destinacao"], "RECICLAGEM")["massa_kg"] == 2000.0
        assert linha(corpo["por_destinacao"], "ATERRO")["massa_kg"] == 500.0
        assert linha(corpo["por_destinacao"], "COPROCESSAMENTO")["volume_m3"] == 1.0

    def test_manifesto_nao_destinado_fica_de_fora(
        self, cliente: TestClient, dados: dict, cenario: dict
    ) -> None:
        """O resumo mede destinação: carga ainda em trânsito não entra."""
        em_transito = emitir(cliente, dados)
        executar(cliente, "transportador@teste.com.br", em_transito["id"], "coleta")

        corpo = cliente.get(RESUMO, headers=autenticar(cliente, "admin@teste.com.br")).json()

        assert corpo["total"]["manifestos"] == 3

    def test_destinacao_fora_do_periodo_fica_de_fora(
        self, cliente: TestClient, sessao: Session, cenario: dict
    ) -> None:
        """A data que recorta o período é a da destinação, não a da emissão."""
        manifesto = sessao.get(Manifesto, cenario["reciclado"]["id"])
        manifesto.destinado_em = agora_utc() - timedelta(days=400)
        sessao.commit()

        cabecalho = autenticar(cliente, "admin@teste.com.br")
        padrao = cliente.get(RESUMO, headers=cabecalho).json()
        alargado = cliente.get(RESUMO, headers=cabecalho, params={"inicio": "2020-01-01"}).json()

        assert padrao["total"]["massa_kg"] == 500.0
        assert alargado["total"]["massa_kg"] == 2500.0

    def test_periodo_invertido_e_recusado(self, cliente: TestClient, dados: dict) -> None:
        resposta = cliente.get(
            RESUMO,
            headers=autenticar(cliente, "admin@teste.com.br"),
            params={"inicio": "2026-10-01", "fim": "2026-09-01"},
        )

        corpo = conferir_formato_do_problema(resposta, 422, "REGRA_VIOLADA")
        assert "invertido" in corpo["detail"]

    def test_exige_autenticacao(self, cliente: TestClient, dados: dict) -> None:
        conferir_formato_do_problema(cliente.get(RESUMO), 401, "NAO_AUTENTICADO")


class TestDivergencias:
    def test_item_fora_da_tolerancia_e_contado(
        self, cliente: TestClient, dados: dict
    ) -> None:
        """100 kg declarados e 80 recebidos: 20% de diferença, acima dos 5%."""
        destinar(
            cliente, dados, quantidade=100, unidade="KG", destinacao="ATERRO", recebida=80
        )
        destinar(cliente, dados, quantidade=100, unidade="KG", destinacao="ATERRO")

        corpo = cliente.get(RESUMO, headers=autenticar(cliente, "admin@teste.com.br")).json()

        assert corpo["divergencias"] == {
            "itens_conferidos": 2,
            "itens_divergentes": 1,
            "percentual": 50.0,
        }

    def test_relatorio_usa_a_quantidade_recebida(
        self, cliente: TestClient, dados: dict
    ) -> None:
        """O que vale é o que chegou ao destino, não o que o gerador declarou."""
        destinar(
            cliente, dados, quantidade=100, unidade="KG", destinacao="ATERRO", recebida=80
        )

        corpo = cliente.get(RESUMO, headers=autenticar(cliente, "admin@teste.com.br")).json()

        assert corpo["total"]["massa_kg"] == 80.0


class TestVisibilidade:
    def test_relatorio_de_outra_organizacao_nao_entra(
        self, cliente: TestClient, dados: dict, cenario: dict, sessao: Session
    ) -> None:
        """Um usuário que não participa de nenhum manifesto vê o relatório zerado."""
        sessao.add(
            Usuario(
                nome="Usuário de Fora",
                email="fora@teste.com.br",
                senha_hash=gerar_hash_senha(SENHA_TESTE),
                perfil=PerfilUsuario.USUARIO,
                organizacao_id=dados["transportador_vencido"].id,
            )
        )
        sessao.commit()

        corpo = cliente.get(RESUMO, headers=autenticar(cliente, "fora@teste.com.br")).json()

        assert corpo["total"]["massa_kg"] == 0.0
        assert corpo["por_tipo"] == []

    def test_pdf_de_manifesto_alheio_e_recusado(
        self, cliente: TestClient, dados: dict, cenario: dict
    ) -> None:
        resposta = cliente.get(
            f"/api/v1/manifestos/{cenario['reciclado']['id']}/pdf",
            headers=autenticar(cliente, "transportador@teste.com.br"),
        )
        assert resposta.status_code == 200

        # O transportador participa; o destinador de outro manifesto não muda
        # isso. Quem não participa é barrado pela mesma regra do detalhe.
        de_fora = cliente.get(
            "/api/v1/manifestos/99999/pdf",
            headers=autenticar(cliente, "gerador@teste.com.br"),
        )
        conferir_formato_do_problema(de_fora, 404, "RECURSO_NAO_ENCONTRADO")


class TestCsv:
    def test_formato_do_arquivo(self, cliente: TestClient, cenario: dict) -> None:
        """UTF-8 com BOM e separador ponto e vírgula: o que o Excel em
        português abre com um duplo clique."""
        resposta = cliente.get(CSV, headers=autenticar(cliente, "admin@teste.com.br"))

        assert resposta.status_code == 200
        assert resposta.headers["content-type"].startswith("text/csv")
        assert "attachment" in resposta.headers["content-disposition"]
        assert resposta.content.startswith(b"\xef\xbb\xbf")

        linhas = resposta.content.decode("utf-8-sig").strip().splitlines()
        assert linhas[0].startswith("numero;status;emitido_em")
        # Três manifestos de um item cada, mais o cabeçalho.
        assert len(linhas) == 4

    def test_uma_linha_por_item(self, cliente: TestClient, dados: dict, oleo: TipoResiduo) -> None:
        """Manifesto com dois resíduos vira duas linhas, com o número repetido."""
        emitir(
            cliente,
            dados,
            itens=[
                {
                    "tipo_residuo_id": dados["tipo_residuo"].id,
                    "quantidade_declarada": 3,
                    "unidade": "T",
                    "acondicionamento": "CACAMBA",
                },
                {
                    "tipo_residuo_id": oleo.id,
                    "quantidade_declarada": 200,
                    "unidade": "L",
                    "acondicionamento": "TAMBOR",
                },
            ],
        )

        conteudo = cliente.get(CSV, headers=autenticar(cliente, "admin@teste.com.br")).content
        linhas = conteudo.decode("utf-8-sig").strip().splitlines()

        assert len(linhas) == 3
        assert linhas[1].split(";")[0] == linhas[2].split(";")[0]
        # Quantidade com vírgula decimal, como a planilha brasileira lê.
        assert "3,000" in linhas[1]

    def test_respeita_os_filtros_da_listagem(
        self, cliente: TestClient, dados: dict, cenario: dict
    ) -> None:
        emitir(cliente, dados)

        conteudo = cliente.get(
            CSV,
            headers=autenticar(cliente, "admin@teste.com.br"),
            params={"status": "EMITIDO"},
        ).content
        linhas = conteudo.decode("utf-8-sig").strip().splitlines()

        assert len(linhas) == 2


class TestPdf:
    def texto_do_pdf(self, conteudo: bytes) -> str:
        """Lê o PDF de volta e devolve o texto de todas as páginas.

        Verificar o conteúdo, e não apenas que o arquivo foi gerado, é o que
        prova que os dados certos chegaram ao documento.
        """
        import io

        leitor = PdfReader(io.BytesIO(conteudo))
        return "\n".join(pagina.extract_text() for pagina in leitor.pages)

    def test_manifesto_em_pdf(self, cliente: TestClient, cenario: dict) -> None:
        resposta = cliente.get(
            f"/api/v1/manifestos/{cenario['reciclado']['id']}/pdf",
            headers=autenticar(cliente, "gerador@teste.com.br"),
        )

        assert resposta.status_code == 200
        assert resposta.headers["content-type"] == "application/pdf"
        assert resposta.content.startswith(b"%PDF")

        texto = self.texto_do_pdf(resposta.content)
        assert cenario["reciclado"]["numero"] in texto
        assert "Gerador Teste SA" in texto
        assert "Reciclagem" in texto
        # O histórico das quatro transições acompanha o documento.
        assert "Em transporte" in texto

    def test_resumo_em_pdf(self, cliente: TestClient, cenario: dict) -> None:
        resposta = cliente.get(
            RESUMO_PDF, headers=autenticar(cliente, "admin@teste.com.br")
        )

        assert resposta.status_code == 200
        assert resposta.headers["content-type"] == "application/pdf"

        texto = self.texto_do_pdf(resposta.content)
        assert "Resumo de resíduos destinados" in texto
        assert "Todas as organizações" in texto
        # Número no formato brasileiro: ponto de milhar e vírgula decimal.
        assert "2.500,000" in texto

    def test_pdf_do_usuario_traz_a_propria_organizacao(
        self, cliente: TestClient, cenario: dict
    ) -> None:
        """O cabeçalho diz de quem são os dados — um relatório sem isso é ambíguo."""
        resposta = cliente.get(
            RESUMO_PDF, headers=autenticar(cliente, "gerador@teste.com.br")
        )

        assert "Gerador Teste SA" in self.texto_do_pdf(resposta.content)


class TestQrCode:
    def test_imagem_do_qrcode(self, cliente: TestClient, cenario: dict) -> None:
        resposta = cliente.get(
            f"/api/v1/manifestos/{cenario['reciclado']['id']}/qrcode.png",
            headers=autenticar(cliente, "gerador@teste.com.br"),
        )

        assert resposta.status_code == 200
        assert resposta.headers["content-type"] == "image/png"
        assert resposta.content.startswith(b"\x89PNG")

    def test_endereco_aponta_para_a_tela_e_usa_o_token(self) -> None:
        """O QR leva à tela do sistema, identificando o manifesto pelo token."""
        endereco = qr.endereco_do_manifesto("abc-123")

        assert endereco.endswith("/qr/abc-123")
        assert endereco.startswith("http")


class TestPainel:
    def test_desvio_de_aterro(self, cliente: TestClient, cenario: dict) -> None:
        """2.000 kg recuperados de 2.500 kg destinados: 80%."""
        corpo = cliente.get(INDICADORES, headers=autenticar(cliente, "admin@teste.com.br")).json()

        assert corpo["desvio_de_aterro"]["massa_recuperada_kg"] == 2000.0
        assert corpo["desvio_de_aterro"]["massa_total_kg"] == 2500.0
        assert corpo["desvio_de_aterro"]["percentual"] == 80.0

    def test_sem_destinacao_o_percentual_e_nulo(
        self, cliente: TestClient, dados: dict
    ) -> None:
        """Zero diria que nada foi recuperado; nulo diz que não há o que medir."""
        corpo = cliente.get(INDICADORES, headers=autenticar(cliente, "admin@teste.com.br")).json()

        assert corpo["desvio_de_aterro"]["percentual"] is None

    def test_pendentes_por_status(self, cliente: TestClient, dados: dict) -> None:
        """Os três estados não finais aparecem sempre, inclusive zerados."""
        emitir(cliente, dados)
        em_transporte = emitir(cliente, dados)
        executar(cliente, "transportador@teste.com.br", em_transporte["id"], "coleta")

        corpo = cliente.get(INDICADORES, headers=autenticar(cliente, "admin@teste.com.br")).json()
        pendentes = {item["status"]: item["total"] for item in corpo["pendentes_por_status"]}

        # O segundo manifesto saiu de EMITIDO ao ser coletado.
        assert pendentes == {"EMITIDO": 1, "EM_TRANSPORTE": 1, "RECEBIDO": 0}

    def test_mes_corrente(self, cliente: TestClient, cenario: dict) -> None:
        corpo = cliente.get(INDICADORES, headers=autenticar(cliente, "admin@teste.com.br")).json()

        assert corpo["mes"]["manifestos_emitidos"] == 3
        assert corpo["mes"]["manifestos_destinados"] == 3
        assert corpo["mes"]["massa_kg"] == 2500.0

    def test_serie_mensal_cobre_a_janela_inteira(
        self, cliente: TestClient, cenario: dict
    ) -> None:
        """Seis meses, mesmo os sem movimento: o gráfico não pode ter buracos."""
        corpo = cliente.get(INDICADORES, headers=autenticar(cliente, "admin@teste.com.br")).json()

        assert len(corpo["serie_mensal"]) == 6
        assert corpo["serie_mensal"][-1]["massa_kg"] == 2500.0
        assert corpo["serie_mensal"][0]["massa_kg"] == 0.0

    def test_licenca_vencida_entra_no_alerta(
        self, cliente: TestClient, dados: dict
    ) -> None:
        """A transportadora com licença vencida é o alerta que o painel mostra."""
        corpo = cliente.get(INDICADORES, headers=autenticar(cliente, "admin@teste.com.br")).json()

        alertas = {item["razao_social"]: item for item in corpo["licencas_a_vencer"]}
        assert "Transportador Vencido SA" in alertas
        assert alertas["Transportador Vencido SA"]["vencida"] is True
        assert alertas["Transportador Vencido SA"]["dias_restantes"] < 0

    def test_usuario_ve_apenas_a_propria_licenca(
        self, cliente: TestClient, dados: dict
    ) -> None:
        """O alerta do usuário comum é sobre a licença da organização dele."""
        corpo = cliente.get(INDICADORES, headers=autenticar(cliente, "gerador@teste.com.br")).json()

        assert corpo["licencas_a_vencer"] == []

    def test_exige_autenticacao(self, cliente: TestClient, dados: dict) -> None:
        conferir_formato_do_problema(cliente.get(INDICADORES), 401, "NAO_AUTENTICADO")
