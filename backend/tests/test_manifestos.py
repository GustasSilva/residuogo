"""Testes do manifesto: emissão, máquina de estados e as regras RN01 a RN08.

Organização do arquivo, uma classe por assunto:

* `TestEmissao`      - RN04 e RN08
* `TestFluxoCompleto`- o caminho feliz de ponta a ponta
* `TestTransicoesInvalidas` - RN02, todas as combinações recusadas
* `TestPermissoes`   - RN01 e RN07
* `TestRecebimento`  - RN05, a tolerância de 5%
* `TestHistorico`    - RN03
"""

import pytest
from fastapi.testclient import TestClient

from app.enums import StatusManifesto
from tests.conftest import autenticar
from tests.test_autenticacao import conferir_formato_do_problema

ROTA = "/api/v1/manifestos"

# Todas as transições que a máquina de estados **não** permite. Declarar os
# casos como dados mantém o teste legível e faz com que acrescentar uma
# transição nova seja acrescentar uma linha.
TRANSICOES_RECUSADAS = [
    # (status de partida, ação tentada)
    (StatusManifesto.EMITIDO, "recebimento"),
    (StatusManifesto.EMITIDO, "recusa"),
    (StatusManifesto.EMITIDO, "destinacao"),
    (StatusManifesto.EM_TRANSPORTE, "coleta"),
    (StatusManifesto.EM_TRANSPORTE, "destinacao"),
    (StatusManifesto.EM_TRANSPORTE, "cancelamento"),
    (StatusManifesto.RECEBIDO, "coleta"),
    (StatusManifesto.RECEBIDO, "recebimento"),
    (StatusManifesto.RECEBIDO, "recusa"),
    (StatusManifesto.RECEBIDO, "cancelamento"),
    (StatusManifesto.DESTINADO, "coleta"),
    (StatusManifesto.DESTINADO, "recebimento"),
    (StatusManifesto.DESTINADO, "destinacao"),
    (StatusManifesto.RECUSADO, "recebimento"),
    (StatusManifesto.RECUSADO, "destinacao"),
    (StatusManifesto.CANCELADO, "coleta"),
    (StatusManifesto.CANCELADO, "recebimento"),
]


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------


def corpo_de_emissao(dados: dict, **ajustes) -> dict:
    corpo = {
        "transportador_id": dados["transportador"].id,
        "destinador_id": dados["destinador"].id,
        "observacoes": "Coleta mensal",
        "itens": [
            {
                "tipo_residuo_id": dados["tipo_residuo"].id,
                "quantidade_declarada": 10.0,
                "unidade": "T",
                "acondicionamento": "CACAMBA",
            }
        ],
    }
    corpo.update(ajustes)
    return corpo


def emitir(cliente: TestClient, dados: dict, **ajustes) -> dict:
    """Emite um manifesto como o gerador e devolve o corpo da resposta."""
    cabecalho = autenticar(cliente, "gerador@teste.com.br")
    resposta = cliente.post(ROTA, headers=cabecalho, json=corpo_de_emissao(dados, **ajustes))
    assert resposta.status_code == 201, resposta.text
    return resposta.json()


def executar(cliente: TestClient, email: str, manifesto_id: int, acao: str, corpo: dict | None = None):
    """Executa uma transição e devolve a resposta HTTP."""
    padroes = {
        "coleta": {"placa_veiculo": "ABC1D23", "motorista_nome": "João da Silva"},
        "recusa": {"motivo_recusa": "Carga fora da especificação declarada."},
        "destinacao": {"tipo_destinacao": "RECICLAGEM"},
        "cancelamento": {},
    }
    return cliente.post(
        f"{ROTA}/{manifesto_id}/{acao}",
        headers=autenticar(cliente, email),
        json=corpo if corpo is not None else padroes.get(acao, {}),
    )


def levar_ao_status(cliente: TestClient, dados: dict, destino: StatusManifesto) -> dict:
    """Emite um manifesto e o conduz até o status pedido.

    Usado pelos testes de transição inválida, que precisam de um manifesto em
    cada estado possível.
    """
    manifesto = emitir(cliente, dados)
    identificador = manifesto["id"]

    if destino is StatusManifesto.EMITIDO:
        return manifesto

    if destino is StatusManifesto.CANCELADO:
        assert executar(cliente, "gerador@teste.com.br", identificador, "cancelamento").status_code == 200
        return manifesto

    assert executar(cliente, "transportador@teste.com.br", identificador, "coleta").status_code == 200
    if destino is StatusManifesto.EM_TRANSPORTE:
        return manifesto

    if destino is StatusManifesto.RECUSADO:
        assert executar(cliente, "destinador@teste.com.br", identificador, "recusa").status_code == 200
        return manifesto

    recebimento = {
        "itens": [
            {"item_id": item["id"], "quantidade_recebida": item["quantidade_declarada"]}
            for item in manifesto["itens"]
        ]
    }
    assert executar(
        cliente, "destinador@teste.com.br", identificador, "recebimento", recebimento
    ).status_code == 200
    if destino is StatusManifesto.RECEBIDO:
        return manifesto

    assert executar(cliente, "destinador@teste.com.br", identificador, "destinacao").status_code == 200
    return manifesto


# ---------------------------------------------------------------------------
# Emissão
# ---------------------------------------------------------------------------


class TestEmissao:
    def test_gerador_emite_manifesto(self, cliente: TestClient, dados: dict) -> None:
        manifesto = emitir(cliente, dados)

        assert manifesto["status"] == "EMITIDO"
        assert manifesto["numero"].startswith("RGO-")
        assert manifesto["gerador"]["id"] == dados["gerador"].id
        assert len(manifesto["itens"]) == 1
        assert manifesto["itens"][0]["quantidade_recebida"] is None
        assert manifesto["qr_token"]

    def test_numero_segue_o_formato_e_nao_repete(self, cliente: TestClient, dados: dict) -> None:
        primeiro = emitir(cliente, dados)["numero"]
        segundo = emitir(cliente, dados)["numero"]

        # RGO-AAAA-NNNNNN
        partes = primeiro.split("-")
        assert partes[0] == "RGO"
        assert len(partes[1]) == 4 and partes[1].isdigit()
        assert len(partes[2]) == 6 and partes[2].isdigit()
        assert primeiro != segundo

    def test_transportador_com_licenca_vencida_e_recusado(
        self, cliente: TestClient, dados: dict
    ) -> None:
        """Regra RN04, o cenário que o seed existe para demonstrar."""
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        resposta = cliente.post(
            ROTA,
            headers=cabecalho,
            json=corpo_de_emissao(dados, transportador_id=dados["transportador_vencido"].id),
        )

        corpo = conferir_formato_do_problema(resposta, 422, "LICENCA_VENCIDA")
        assert dados["transportador_vencido"].razao_social in corpo["detail"]

    def test_participante_com_papel_errado_e_recusado(
        self, cliente: TestClient, dados: dict
    ) -> None:
        """Regra RN04: um destinador não pode ser indicado como transportador."""
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        resposta = cliente.post(
            ROTA,
            headers=cabecalho,
            json=corpo_de_emissao(dados, transportador_id=dados["destinador"].id),
        )

        conferir_formato_do_problema(resposta, 422, "PAPEL_INVALIDO")

    def test_organizacao_desativada_e_recusada(
        self, cliente: TestClient, dados: dict, sessao
    ) -> None:
        dados["transportador"].ativo = False
        sessao.commit()

        resposta = cliente.post(
            ROTA,
            headers=autenticar(cliente, "gerador@teste.com.br"),
            json=corpo_de_emissao(dados),
        )

        conferir_formato_do_problema(resposta, 422, "PAPEL_INVALIDO")

    def test_manifesto_sem_itens_e_recusado(self, cliente: TestClient, dados: dict) -> None:
        """Primeira metade da regra RN08."""
        resposta = cliente.post(
            ROTA,
            headers=autenticar(cliente, "gerador@teste.com.br"),
            json=corpo_de_emissao(dados, itens=[]),
        )

        corpo = conferir_formato_do_problema(resposta, 422, "DADOS_INVALIDOS")
        assert any(erro["campo"] == "itens" for erro in corpo["erros"])

    @pytest.mark.parametrize("quantidade", [0, -5])
    def test_quantidade_nao_positiva_e_recusada(
        self, cliente: TestClient, dados: dict, quantidade: float
    ) -> None:
        """Segunda metade da regra RN08."""
        itens = [
            {
                "tipo_residuo_id": dados["tipo_residuo"].id,
                "quantidade_declarada": quantidade,
                "unidade": "T",
                "acondicionamento": "GRANEL",
            }
        ]

        resposta = cliente.post(
            ROTA,
            headers=autenticar(cliente, "gerador@teste.com.br"),
            json=corpo_de_emissao(dados, itens=itens),
        )

        corpo = conferir_formato_do_problema(resposta, 422, "DADOS_INVALIDOS")
        assert any("quantidade_declarada" in erro["campo"] for erro in corpo["erros"])

    def test_tipo_de_residuo_inexistente_e_recusado(
        self, cliente: TestClient, dados: dict
    ) -> None:
        itens = [
            {
                "tipo_residuo_id": 9999,
                "quantidade_declarada": 1.0,
                "unidade": "KG",
                "acondicionamento": "TAMBOR",
            }
        ]

        resposta = cliente.post(
            ROTA,
            headers=autenticar(cliente, "gerador@teste.com.br"),
            json=corpo_de_emissao(dados, itens=itens),
        )

        corpo = conferir_formato_do_problema(resposta, 422, "REGRA_VIOLADA")
        assert "9999" in corpo["detail"]

    def test_destinador_nao_emite(self, cliente: TestClient, dados: dict) -> None:
        """Só o gerador emite: a emissão é um ato de quem produz o resíduo."""
        resposta = cliente.post(
            ROTA,
            headers=autenticar(cliente, "destinador@teste.com.br"),
            json=corpo_de_emissao(dados),
        )

        conferir_formato_do_problema(resposta, 422, "PAPEL_INVALIDO")

    def test_admin_nao_emite(self, cliente: TestClient, dados: dict) -> None:
        """O ADMIN não tem organização e portanto não assume papel no fluxo."""
        resposta = cliente.post(
            ROTA,
            headers=autenticar(cliente, "admin@teste.com.br"),
            json=corpo_de_emissao(dados),
        )

        conferir_formato_do_problema(resposta, 403, "PERMISSAO_NEGADA")

    def test_nada_e_gravado_quando_a_emissao_falha(
        self, cliente: TestClient, dados: dict
    ) -> None:
        """A validação acontece antes de qualquer INSERT."""
        cliente.post(
            ROTA,
            headers=autenticar(cliente, "gerador@teste.com.br"),
            json=corpo_de_emissao(dados, transportador_id=dados["transportador_vencido"].id),
        )

        listagem = cliente.get(ROTA, headers=autenticar(cliente, "gerador@teste.com.br")).json()
        assert listagem["total"] == 0


# ---------------------------------------------------------------------------
# Caminho completo
# ---------------------------------------------------------------------------


class TestFluxoCompleto:
    def test_ciclo_ate_a_destinacao(self, cliente: TestClient, dados: dict) -> None:
        """O caminho feliz inteiro, com os três papéis.

        É o roteiro da demonstração: emissão, coleta, recebimento e destinação.
        """
        manifesto = emitir(cliente, dados)
        identificador = manifesto["id"]

        coleta = executar(cliente, "transportador@teste.com.br", identificador, "coleta")
        assert coleta.status_code == 200
        assert coleta.json()["status"] == "EM_TRANSPORTE"
        assert coleta.json()["placa_veiculo"] == "ABC1D23"
        assert coleta.json()["coletado_em"] is not None

        recebimento = executar(
            cliente,
            "destinador@teste.com.br",
            identificador,
            "recebimento",
            {"itens": [{"item_id": manifesto["itens"][0]["id"], "quantidade_recebida": 10.0}]},
        )
        assert recebimento.status_code == 200
        assert recebimento.json()["status"] == "RECEBIDO"
        assert recebimento.json()["itens"][0]["quantidade_recebida"] == 10.0
        assert recebimento.json()["itens"][0]["divergente"] is False

        destinacao = executar(cliente, "destinador@teste.com.br", identificador, "destinacao")
        assert destinacao.status_code == 200
        corpo = destinacao.json()
        assert corpo["status"] == "DESTINADO"
        assert corpo["tipo_destinacao"] == "RECICLAGEM"
        assert corpo["destinado_em"] is not None

    def test_caminho_da_recusa(self, cliente: TestClient, dados: dict) -> None:
        manifesto = emitir(cliente, dados)
        identificador = manifesto["id"]

        executar(cliente, "transportador@teste.com.br", identificador, "coleta")
        recusa = executar(cliente, "destinador@teste.com.br", identificador, "recusa")

        assert recusa.status_code == 200
        assert recusa.json()["status"] == "RECUSADO"
        assert "especificação" in recusa.json()["motivo_recusa"]

    def test_caminho_do_cancelamento(self, cliente: TestClient, dados: dict) -> None:
        manifesto = emitir(cliente, dados)

        cancelamento = executar(
            cliente, "gerador@teste.com.br", manifesto["id"], "cancelamento"
        )

        assert cancelamento.status_code == 200
        assert cancelamento.json()["status"] == "CANCELADO"


# ---------------------------------------------------------------------------
# RN02: transições inválidas
# ---------------------------------------------------------------------------


class TestTransicoesInvalidas:
    @pytest.mark.parametrize(("partida", "acao"), TRANSICOES_RECUSADAS)
    def test_transicao_fora_do_diagrama_e_recusada(
        self, cliente: TestClient, dados: dict, partida: StatusManifesto, acao: str
    ) -> None:
        """Regra RN02, para todas as combinações recusadas pelo diagrama."""
        manifesto = levar_ao_status(cliente, dados, partida)

        # O destinador tem autoridade sobre três das ações e o gerador sobre
        # as outras; usar o ator certo garante que a recusa venha da máquina de
        # estados (409) e não da permissão (403).
        ator = {
            "coleta": "transportador@teste.com.br",
            "cancelamento": "gerador@teste.com.br",
        }.get(acao, "destinador@teste.com.br")

        corpo = {"itens": [{"item_id": i["id"], "quantidade_recebida": 1.0} for i in manifesto["itens"]]} if acao == "recebimento" else None
        resposta = executar(cliente, ator, manifesto["id"], acao, corpo)

        conferir_formato_do_problema(resposta, 409, "TRANSICAO_INVALIDA")

    def test_mensagem_de_estado_final_explica_a_situacao(
        self, cliente: TestClient, dados: dict
    ) -> None:
        manifesto = levar_ao_status(cliente, dados, StatusManifesto.DESTINADO)

        resposta = executar(cliente, "destinador@teste.com.br", manifesto["id"], "destinacao")

        corpo = conferir_formato_do_problema(resposta, 409, "TRANSICAO_INVALIDA")
        assert "estado final" in corpo["detail"]

    def test_mensagem_lista_as_transicoes_possiveis(
        self, cliente: TestClient, dados: dict
    ) -> None:
        manifesto = emitir(cliente, dados)

        resposta = executar(cliente, "destinador@teste.com.br", manifesto["id"], "destinacao")

        corpo = conferir_formato_do_problema(resposta, 409, "TRANSICAO_INVALIDA")
        assert "EM_TRANSPORTE" in corpo["detail"]
        assert "CANCELADO" in corpo["detail"]

    def test_coleta_repetida_e_recusada(self, cliente: TestClient, dados: dict) -> None:
        """Dois cliques no botão não movem o manifesto duas vezes."""
        manifesto = emitir(cliente, dados)

        primeira = executar(cliente, "transportador@teste.com.br", manifesto["id"], "coleta")
        segunda = executar(cliente, "transportador@teste.com.br", manifesto["id"], "coleta")

        assert primeira.status_code == 200
        conferir_formato_do_problema(segunda, 409, "TRANSICAO_INVALIDA")


# ---------------------------------------------------------------------------
# RN01 e RN07: permissões
# ---------------------------------------------------------------------------


class TestPermissoes:
    def test_gerador_nao_confirma_a_coleta(self, cliente: TestClient, dados: dict) -> None:
        """Regra RN01: a coleta é ato do transportador."""
        manifesto = emitir(cliente, dados)

        resposta = executar(cliente, "gerador@teste.com.br", manifesto["id"], "coleta")

        conferir_formato_do_problema(resposta, 403, "PERMISSAO_NEGADA")

    def test_transportador_nao_recebe_a_carga(self, cliente: TestClient, dados: dict) -> None:
        manifesto = levar_ao_status(cliente, dados, StatusManifesto.EM_TRANSPORTE)

        resposta = executar(
            cliente,
            "transportador@teste.com.br",
            manifesto["id"],
            "recebimento",
            {"itens": [{"item_id": manifesto["itens"][0]["id"], "quantidade_recebida": 10.0}]},
        )

        conferir_formato_do_problema(resposta, 403, "PERMISSAO_NEGADA")

    def test_transportadora_de_fora_nao_confirma_a_coleta(
        self, cliente: TestClient, dados: dict, sessao
    ) -> None:
        """Ter o papel de transportador não basta: é preciso ser o do manifesto.

        A recusa vem da verificação de visibilidade (RN07), que roda ao
        carregar o manifesto e já barra quem não participa dele — antes de a
        regra de papel (RN01) ser avaliada.
        """
        from app.models import Usuario
        from app.security import gerar_hash_senha

        intrusa = dados["transportador_vencido"]  # tem papel TRANSPORTADOR
        sessao.add(
            Usuario(
                nome="Usuario Intruso",
                email="intruso@teste.com.br",
                senha_hash=gerar_hash_senha("senhaDeTeste123"),
                perfil="USUARIO",
                organizacao_id=intrusa.id,
            )
        )
        sessao.commit()

        manifesto = emitir(cliente, dados)
        resposta = executar(cliente, "intruso@teste.com.br", manifesto["id"], "coleta")

        corpo = conferir_formato_do_problema(resposta, 403, "PERMISSAO_NEGADA")
        assert "não participa deste manifesto" in corpo["detail"]

    def test_organizacao_de_fora_nao_ve_o_manifesto(
        self, cliente: TestClient, dados: dict, sessao
    ) -> None:
        """Regra RN07 no detalhe."""
        from app.models import Usuario
        from app.security import gerar_hash_senha

        sessao.add(
            Usuario(
                nome="Usuario de Fora",
                email="fora@teste.com.br",
                senha_hash=gerar_hash_senha("senhaDeTeste123"),
                perfil="USUARIO",
                organizacao_id=dados["transportador_vencido"].id,
            )
        )
        sessao.commit()

        manifesto = emitir(cliente, dados)

        resposta = cliente.get(
            f"{ROTA}/{manifesto['id']}", headers=autenticar(cliente, "fora@teste.com.br")
        )

        conferir_formato_do_problema(resposta, 403, "PERMISSAO_NEGADA")

    def test_listagem_mostra_so_os_proprios_manifestos(
        self, cliente: TestClient, dados: dict, sessao
    ) -> None:
        """Regra RN07 na listagem, inclusive no total da paginação."""
        from app.models import Usuario
        from app.security import gerar_hash_senha

        sessao.add(
            Usuario(
                nome="Usuario de Fora",
                email="fora@teste.com.br",
                senha_hash=gerar_hash_senha("senhaDeTeste123"),
                perfil="USUARIO",
                organizacao_id=dados["transportador_vencido"].id,
            )
        )
        sessao.commit()
        emitir(cliente, dados)

        do_gerador = cliente.get(ROTA, headers=autenticar(cliente, "gerador@teste.com.br")).json()
        de_fora = cliente.get(ROTA, headers=autenticar(cliente, "fora@teste.com.br")).json()
        do_admin = cliente.get(ROTA, headers=autenticar(cliente, "admin@teste.com.br")).json()

        assert do_gerador["total"] == 1
        assert de_fora["total"] == 0
        assert do_admin["total"] == 1  # o ADMIN vê todos

    def test_os_tres_participantes_veem_o_manifesto(
        self, cliente: TestClient, dados: dict
    ) -> None:
        manifesto = emitir(cliente, dados)

        for email in (
            "gerador@teste.com.br",
            "transportador@teste.com.br",
            "destinador@teste.com.br",
        ):
            resposta = cliente.get(
                f"{ROTA}/{manifesto['id']}", headers=autenticar(cliente, email)
            )
            assert resposta.status_code == 200, f"{email} deveria ver o manifesto"

    def test_manifesto_inexistente_devolve_404(self, cliente: TestClient, dados: dict) -> None:
        resposta = cliente.get(
            f"{ROTA}/9999", headers=autenticar(cliente, "gerador@teste.com.br")
        )

        conferir_formato_do_problema(resposta, 404, "RECURSO_NAO_ENCONTRADO")


# ---------------------------------------------------------------------------
# RN05: recebimento e divergência
# ---------------------------------------------------------------------------


class TestRecebimento:
    def receber(self, cliente: TestClient, dados: dict, quantidade: float):
        """Emite, coleta e recebe com a quantidade informada."""
        manifesto = levar_ao_status(cliente, dados, StatusManifesto.EM_TRANSPORTE)
        return executar(
            cliente,
            "destinador@teste.com.br",
            manifesto["id"],
            "recebimento",
            {"itens": [{"item_id": manifesto["itens"][0]["id"], "quantidade_recebida": quantidade}]},
        )

    @pytest.mark.parametrize(
        ("recebida", "esperado_divergente", "comentario"),
        [
            (10.0, False, "exatamente o declarado"),
            (9.5, False, "5% a menos: no limite, não divergente"),
            (10.5, False, "5% a mais: no limite, não divergente"),
            (9.4, True, "6% a menos: divergente"),
            (10.6, True, "6% a mais: divergente"),
            (0.0, True, "nada chegou: divergente"),
        ],
    )
    def test_tolerancia_de_cinco_por_cento(
        self,
        cliente: TestClient,
        dados: dict,
        recebida: float,
        esperado_divergente: bool,
        comentario: str,
    ) -> None:
        """Regra RN05. O declarado é 10 toneladas em todos os casos."""
        resposta = self.receber(cliente, dados, recebida)

        assert resposta.status_code == 200
        item = resposta.json()["itens"][0]
        assert item["divergente"] is esperado_divergente, comentario
        assert item["quantidade_recebida"] == recebida

    def test_divergencia_nao_bloqueia_o_recebimento(
        self, cliente: TestClient, dados: dict
    ) -> None:
        """A divergência é registrada como alerta, não como impedimento."""
        resposta = self.receber(cliente, dados, 2.0)

        assert resposta.status_code == 200
        assert resposta.json()["status"] == "RECEBIDO"
        assert resposta.json()["itens"][0]["divergente"] is True

    def test_item_nao_conferido_e_recusado(self, cliente: TestClient, dados: dict) -> None:
        """Todos os itens precisam ter quantidade recebida informada."""
        itens = [
            {
                "tipo_residuo_id": dados["tipo_residuo"].id,
                "quantidade_declarada": 5.0,
                "unidade": "T",
                "acondicionamento": "GRANEL",
            },
            {
                "tipo_residuo_id": dados["tipo_residuo"].id,
                "quantidade_declarada": 3.0,
                "unidade": "T",
                "acondicionamento": "BIG_BAG",
            },
        ]
        manifesto = emitir(cliente, dados, itens=itens)
        executar(cliente, "transportador@teste.com.br", manifesto["id"], "coleta")

        resposta = executar(
            cliente,
            "destinador@teste.com.br",
            manifesto["id"],
            "recebimento",
            {"itens": [{"item_id": manifesto["itens"][0]["id"], "quantidade_recebida": 5.0}]},
        )

        corpo = conferir_formato_do_problema(resposta, 422, "REGRA_VIOLADA")
        assert "todos os itens" in corpo["detail"]

    def test_item_de_outro_manifesto_e_recusado(self, cliente: TestClient, dados: dict) -> None:
        outro = emitir(cliente, dados)
        manifesto = levar_ao_status(cliente, dados, StatusManifesto.EM_TRANSPORTE)

        resposta = executar(
            cliente,
            "destinador@teste.com.br",
            manifesto["id"],
            "recebimento",
            {"itens": [{"item_id": outro["itens"][0]["id"], "quantidade_recebida": 1.0}]},
        )

        corpo = conferir_formato_do_problema(resposta, 422, "REGRA_VIOLADA")
        assert "não pertencem" in corpo["detail"]

    def test_quantidade_negativa_e_recusada(self, cliente: TestClient, dados: dict) -> None:
        resposta = self.receber(cliente, dados, -1.0)

        conferir_formato_do_problema(resposta, 422, "DADOS_INVALIDOS")


# ---------------------------------------------------------------------------
# RN03 e RN06
# ---------------------------------------------------------------------------


class TestHistorico:
    def test_cada_transicao_grava_uma_movimentacao(
        self, cliente: TestClient, dados: dict
    ) -> None:
        """Regra RN03: o histórico reconstrói o caminho inteiro."""
        manifesto = levar_ao_status(cliente, dados, StatusManifesto.DESTINADO)

        historico = cliente.get(
            f"{ROTA}/{manifesto['id']}/historico",
            headers=autenticar(cliente, "gerador@teste.com.br"),
        ).json()

        caminho = [(passo["status_anterior"], passo["status_novo"]) for passo in historico]
        assert caminho == [
            (None, "EMITIDO"),  # a emissão não tem status anterior
            ("EMITIDO", "EM_TRANSPORTE"),
            ("EM_TRANSPORTE", "RECEBIDO"),
            ("RECEBIDO", "DESTINADO"),
        ]

    def test_o_historico_registra_quem_agiu(self, cliente: TestClient, dados: dict) -> None:
        manifesto = levar_ao_status(cliente, dados, StatusManifesto.EM_TRANSPORTE)

        historico = cliente.get(
            f"{ROTA}/{manifesto['id']}/historico",
            headers=autenticar(cliente, "gerador@teste.com.br"),
        ).json()

        assert historico[0]["usuario"]["nome"] == dados["usuario_gerador"].nome
        assert historico[1]["usuario"]["nome"] == "Usuario Transportador"

    def test_transicao_recusada_nao_deixa_rastro(self, cliente: TestClient, dados: dict) -> None:
        """Uma tentativa inválida não pode poluir o histórico."""
        manifesto = emitir(cliente, dados)
        executar(cliente, "destinador@teste.com.br", manifesto["id"], "destinacao")

        historico = cliente.get(
            f"{ROTA}/{manifesto['id']}/historico",
            headers=autenticar(cliente, "gerador@teste.com.br"),
        ).json()

        assert len(historico) == 1


class TestObrigatoriedadeRn06:
    def test_recusa_sem_motivo_e_recusada(self, cliente: TestClient, dados: dict) -> None:
        manifesto = levar_ao_status(cliente, dados, StatusManifesto.EM_TRANSPORTE)

        resposta = executar(
            cliente, "destinador@teste.com.br", manifesto["id"], "recusa", {}
        )

        corpo = conferir_formato_do_problema(resposta, 422, "DADOS_INVALIDOS")
        assert any(erro["campo"] == "motivo_recusa" for erro in corpo["erros"])

    def test_destinacao_sem_tipo_e_recusada(self, cliente: TestClient, dados: dict) -> None:
        manifesto = levar_ao_status(cliente, dados, StatusManifesto.RECEBIDO)

        resposta = executar(
            cliente, "destinador@teste.com.br", manifesto["id"], "destinacao", {}
        )

        corpo = conferir_formato_do_problema(resposta, 422, "DADOS_INVALIDOS")
        assert any(erro["campo"] == "tipo_destinacao" for erro in corpo["erros"])


class TestQrCode:
    def test_token_resolve_para_o_manifesto(self, cliente: TestClient, dados: dict) -> None:
        manifesto = emitir(cliente, dados)

        resposta = cliente.get(
            f"{ROTA}/qr/{manifesto['qr_token']}",
            headers=autenticar(cliente, "destinador@teste.com.br"),
        )

        assert resposta.status_code == 200
        assert resposta.json()["id"] == manifesto["id"]

    def test_token_desconhecido_devolve_404(self, cliente: TestClient, dados: dict) -> None:
        resposta = cliente.get(
            f"{ROTA}/qr/nao-existe", headers=autenticar(cliente, "gerador@teste.com.br")
        )

        conferir_formato_do_problema(resposta, 404, "RECURSO_NAO_ENCONTRADO")


class TestFiltros:
    def test_filtro_por_status(self, cliente: TestClient, dados: dict) -> None:
        levar_ao_status(cliente, dados, StatusManifesto.EM_TRANSPORTE)
        emitir(cliente, dados)
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        emitidos = cliente.get(ROTA, headers=cabecalho, params={"status": "EMITIDO"}).json()
        em_transporte = cliente.get(
            ROTA, headers=cabecalho, params={"status": "EM_TRANSPORTE"}
        ).json()

        assert emitidos["total"] == 1
        assert em_transporte["total"] == 1

    def test_filtro_por_numero(self, cliente: TestClient, dados: dict) -> None:
        manifesto = emitir(cliente, dados)
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        encontrados = cliente.get(
            ROTA, headers=cabecalho, params={"numero": manifesto["numero"][-6:]}
        ).json()

        assert encontrados["total"] == 1

    def test_filtro_por_participante(self, cliente: TestClient, dados: dict) -> None:
        emitir(cliente, dados)
        cabecalho = autenticar(cliente, "admin@teste.com.br")

        do_destinador = cliente.get(
            ROTA, headers=cabecalho, params={"participante_id": dados["destinador"].id}
        ).json()
        de_quem_nao_participa = cliente.get(
            ROTA, headers=cabecalho, params={"participante_id": dados["transportador_vencido"].id}
        ).json()

        assert do_destinador["total"] == 1
        assert de_quem_nao_participa["total"] == 0
