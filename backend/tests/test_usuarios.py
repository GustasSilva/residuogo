"""Testes da alteracao de usuarios e da troca da propria senha.

Cobrem os dois casos de uso que o cadastro sozinho nao resolvia: tirar o
acesso de quem saiu da empresa e devolver o acesso a quem esqueceu a senha.
"""

from fastapi.testclient import TestClient

from tests.conftest import SENHA_TESTE, autenticar
from tests.test_autenticacao import conferir_formato_do_problema

NOVA_SENHA = "outraSenha456"


def entrar(cliente: TestClient, email: str, senha: str):
    """Tenta o login e devolve a resposta, seja ela qual for."""
    return cliente.post("/api/v1/auth/login", json={"email": email, "senha": senha})


def alterar(cliente: TestClient, cabecalho: dict, usuario_id: int, **ajustes):
    """Envia uma alteracao de usuario, com nome e situacao validos por padrao."""
    corpo = {"nome": "Nome Alterado", "ativo": True}
    corpo.update(ajustes)
    return cliente.put(f"/api/v1/usuarios/{usuario_id}", headers=cabecalho, json=corpo)


def trocar_senha(cliente: TestClient, cabecalho: dict, senha_atual: str, nova_senha: str):
    return cliente.put(
        "/api/v1/auth/senha",
        headers=cabecalho,
        json={"senha_atual": senha_atual, "nova_senha": nova_senha},
    )


class TestAlteracaoPeloAdmin:
    def test_desativar_bloqueia_o_login(self, cliente: TestClient, dados: dict) -> None:
        admin = autenticar(cliente, "admin@teste.com.br")

        resposta = alterar(cliente, admin, dados["usuario_gerador"].id, ativo=False)

        assert resposta.status_code == 200
        assert resposta.json()["ativo"] is False
        recusa = entrar(cliente, "gerador@teste.com.br", SENHA_TESTE)
        corpo = conferir_formato_do_problema(recusa, 401, "NAO_AUTENTICADO")
        assert "desativado" in corpo["detail"].lower()

    def test_desativar_invalida_o_token_em_uso(self, cliente: TestClient, dados: dict) -> None:
        """O efeito e imediato: quem estava logado perde o acesso na requisicao seguinte."""
        admin = autenticar(cliente, "admin@teste.com.br")
        gerador = autenticar(cliente, "gerador@teste.com.br")

        alterar(cliente, admin, dados["usuario_gerador"].id, ativo=False)
        resposta = cliente.get("/api/v1/manifestos", headers=gerador)

        conferir_formato_do_problema(resposta, 401, "NAO_AUTENTICADO")

    def test_reativar_devolve_o_acesso(self, cliente: TestClient, dados: dict) -> None:
        admin = autenticar(cliente, "admin@teste.com.br")
        usuario_id = dados["usuario_gerador"].id

        alterar(cliente, admin, usuario_id, ativo=False)
        alterar(cliente, admin, usuario_id, ativo=True)

        assert entrar(cliente, "gerador@teste.com.br", SENHA_TESTE).status_code == 200

    def test_nova_senha_substitui_a_antiga(self, cliente: TestClient, dados: dict) -> None:
        admin = autenticar(cliente, "admin@teste.com.br")

        alterar(cliente, admin, dados["usuario_gerador"].id, nova_senha=NOVA_SENHA)

        assert entrar(cliente, "gerador@teste.com.br", NOVA_SENHA).status_code == 200
        assert entrar(cliente, "gerador@teste.com.br", SENHA_TESTE).status_code == 401

    def test_sem_nova_senha_a_senha_continua_a_mesma(
        self, cliente: TestClient, dados: dict
    ) -> None:
        admin = autenticar(cliente, "admin@teste.com.br")

        resposta = alterar(cliente, admin, dados["usuario_gerador"].id, nome="Gerador Renomeado")

        assert resposta.json()["nome"] == "Gerador Renomeado"
        assert entrar(cliente, "gerador@teste.com.br", SENHA_TESTE).status_code == 200

    def test_admin_nao_desativa_a_si_mesmo(self, cliente: TestClient, dados: dict) -> None:
        admin = autenticar(cliente, "admin@teste.com.br")

        resposta = alterar(cliente, admin, dados["admin"].id, ativo=False)

        corpo = conferir_formato_do_problema(resposta, 422, "REGRA_VIOLADA")
        assert "próprio usuário" in corpo["detail"]

    def test_nova_senha_curta_e_recusada(self, cliente: TestClient, dados: dict) -> None:
        admin = autenticar(cliente, "admin@teste.com.br")

        resposta = alterar(cliente, admin, dados["usuario_gerador"].id, nova_senha="curta")

        corpo = conferir_formato_do_problema(resposta, 422, "DADOS_INVALIDOS")
        assert any(erro["campo"] == "nova_senha" for erro in corpo["erros"])

    def test_usuario_comum_nao_altera(self, cliente: TestClient, dados: dict) -> None:
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        resposta = alterar(cliente, cabecalho, dados["usuario_transportador"].id, ativo=False)

        conferir_formato_do_problema(resposta, 403, "PERMISSAO_NEGADA")

    def test_usuario_inexistente_devolve_404(self, cliente: TestClient, dados: dict) -> None:
        admin = autenticar(cliente, "admin@teste.com.br")

        resposta = alterar(cliente, admin, 9999)

        conferir_formato_do_problema(resposta, 404, "RECURSO_NAO_ENCONTRADO")


class TestTrocaDaPropriaSenha:
    def test_troca_com_a_senha_atual_certa(self, cliente: TestClient, dados: dict) -> None:
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        resposta = trocar_senha(cliente, cabecalho, SENHA_TESTE, NOVA_SENHA)

        assert resposta.status_code == 204
        assert entrar(cliente, "gerador@teste.com.br", NOVA_SENHA).status_code == 200
        assert entrar(cliente, "gerador@teste.com.br", SENHA_TESTE).status_code == 401

    def test_senha_atual_errada_e_422_e_nao_401(self, cliente: TestClient, dados: dict) -> None:
        """Um 401 faria o front-end encerrar a sessao de quem so errou um campo."""
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        resposta = trocar_senha(cliente, cabecalho, "senhaErrada", NOVA_SENHA)

        conferir_formato_do_problema(resposta, 422, "REGRA_VIOLADA")
        assert entrar(cliente, "gerador@teste.com.br", SENHA_TESTE).status_code == 200

    def test_nova_senha_curta_e_recusada(self, cliente: TestClient, dados: dict) -> None:
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        resposta = trocar_senha(cliente, cabecalho, SENHA_TESTE, "curta")

        corpo = conferir_formato_do_problema(resposta, 422, "DADOS_INVALIDOS")
        assert any(erro["campo"] == "nova_senha" for erro in corpo["erros"])

    def test_sem_token_e_recusado(self, cliente: TestClient, dados: dict) -> None:
        resposta = cliente.put(
            "/api/v1/auth/senha", json={"senha_atual": SENHA_TESTE, "nova_senha": NOVA_SENHA}
        )

        conferir_formato_do_problema(resposta, 401, "NAO_AUTENTICADO")
