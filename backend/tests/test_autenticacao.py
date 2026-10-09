"""Testes das rotas de autenticacao e do formato padronizado de erro.

Alem do login em si, este arquivo verifica que **toda** resposta de erro sai
no formato da RFC 7807 - inclusive os erros que o framework levanta por conta
propria, como rota inexistente. E a garantia de que o padrao nao tem furos.
"""

from fastapi.testclient import TestClient

from tests.conftest import SENHA_TESTE, autenticar

MIDIA_PROBLEMA = "application/problem+json"

# Campos que a RFC 7807 define, mais as duas extensoes do projeto.
CAMPOS_OBRIGATORIOS = {"type", "title", "status", "detail", "instance", "codigo", "erros"}


def conferir_formato_do_problema(resposta, status: int, codigo: str) -> dict:
    """Verifica que a resposta e um problema RFC 7807 bem formado.

    Reunir essas asserções em uma funcao evita repeti-las em cada teste e
    garante que o contrato cobrado seja sempre o mesmo.
    """
    assert resposta.status_code == status
    assert resposta.headers["content-type"].startswith(MIDIA_PROBLEMA)

    corpo = resposta.json()
    assert CAMPOS_OBRIGATORIOS <= corpo.keys()
    assert corpo["status"] == status
    assert corpo["codigo"] == codigo
    assert corpo["type"].endswith(codigo.lower().replace("_", "-"))
    assert corpo["detail"], "o campo detail não pode vir vazio"
    return corpo


class TestLogin:
    def test_login_valido_devolve_token(self, cliente: TestClient, dados: dict) -> None:
        resposta = cliente.post(
            "/api/v1/auth/login",
            json={"email": "admin@teste.com.br", "senha": SENHA_TESTE},
        )

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["tipo"] == "Bearer"
        assert corpo["token"]
        assert corpo["expira_em_minutos"] > 0

    def test_senha_errada_e_recusada(self, cliente: TestClient, dados: dict) -> None:
        resposta = cliente.post(
            "/api/v1/auth/login",
            json={"email": "admin@teste.com.br", "senha": "senhaErrada"},
        )
        conferir_formato_do_problema(resposta, 401, "NAO_AUTENTICADO")

    def test_email_inexistente_e_senha_errada_dao_a_mesma_resposta(
        self, cliente: TestClient, dados: dict
    ) -> None:
        """Mensagens iguais impedem descobrir quais e-mails estao cadastrados."""
        inexistente = cliente.post(
            "/api/v1/auth/login",
            json={"email": "ninguem@teste.com.br", "senha": SENHA_TESTE},
        )
        senha_errada = cliente.post(
            "/api/v1/auth/login",
            json={"email": "admin@teste.com.br", "senha": "errada"},
        )

        assert inexistente.status_code == senha_errada.status_code == 401
        assert inexistente.json()["detail"] == senha_errada.json()["detail"]

    def test_usuario_desativado_nao_entra(
        self, cliente: TestClient, dados: dict, sessao
    ) -> None:
        dados["admin"].ativo = False
        sessao.commit()

        resposta = cliente.post(
            "/api/v1/auth/login",
            json={"email": "admin@teste.com.br", "senha": SENHA_TESTE},
        )
        corpo = conferir_formato_do_problema(resposta, 401, "NAO_AUTENTICADO")
        assert "desativado" in corpo["detail"].lower()

    def test_email_mal_formado_cai_na_validacao(self, cliente: TestClient) -> None:
        resposta = cliente.post(
            "/api/v1/auth/login", json={"email": "nao-e-email", "senha": "x"}
        )
        corpo = conferir_formato_do_problema(resposta, 422, "DADOS_INVALIDOS")
        assert corpo["erros"], "erros[] deve apontar o campo invalido"
        assert corpo["erros"][0]["campo"] == "email"


class TestUsuarioLogado:
    def test_me_devolve_o_usuario_e_a_organizacao(
        self, cliente: TestClient, dados: dict
    ) -> None:
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        resposta = cliente.get("/api/v1/auth/me", headers=cabecalho)

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["email"] == "gerador@teste.com.br"
        assert corpo["perfil"] == "USUARIO"
        # O front-end depende deste papel para decidir quais acoes exibir.
        assert corpo["organizacao"]["papel"] == "GERADOR"

    def test_admin_nao_tem_organizacao(self, cliente: TestClient, dados: dict) -> None:
        cabecalho = autenticar(cliente, "admin@teste.com.br")

        corpo = cliente.get("/api/v1/auth/me", headers=cabecalho).json()

        assert corpo["perfil"] == "ADMIN"
        assert corpo["organizacao"] is None

    def test_sem_token_e_recusado(self, cliente: TestClient, dados: dict) -> None:
        conferir_formato_do_problema(
            cliente.get("/api/v1/auth/me"), 401, "NAO_AUTENTICADO"
        )

    def test_token_invalido_e_recusado(self, cliente: TestClient, dados: dict) -> None:
        resposta = cliente.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer token-inventado"}
        )
        conferir_formato_do_problema(resposta, 401, "NAO_AUTENTICADO")

    def test_nao_devolve_a_senha(self, cliente: TestClient, dados: dict) -> None:
        """A senha e o hash dela nunca podem sair pela API."""
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        texto = cliente.get("/api/v1/auth/me", headers=cabecalho).text

        assert "senha" not in texto
        assert "$2b$" not in texto  # inicio de um hash bcrypt


class TestPadronizacaoDeErros:
    def test_rota_inexistente_tambem_sai_em_problem_json(self, cliente: TestClient) -> None:
        conferir_formato_do_problema(
            cliente.get("/api/v1/nao-existe"), 404, "RECURSO_NAO_ENCONTRADO"
        )

    def test_metodo_nao_permitido_tambem_sai_em_problem_json(
        self, cliente: TestClient
    ) -> None:
        conferir_formato_do_problema(
            cliente.delete("/api/v1/auth/login"), 405, "METODO_NAO_PERMITIDO"
        )

    def test_mensagens_de_erro_estao_em_portugues(self, cliente: TestClient) -> None:
        """O framework responde em ingles por padrao; a traducao e nossa."""
        corpo = cliente.get("/api/v1/nao-existe").json()
        assert corpo["detail"] != "Not Found"

    def test_o_cabecalho_de_rastreio_acompanha_a_resposta(self, cliente: TestClient) -> None:
        resposta = cliente.get("/health")
        assert resposta.headers.get("X-Request-Id")


class TestDiagnostico:
    def test_health_e_publico_e_ve_o_banco(self, cliente: TestClient) -> None:
        resposta = cliente.get("/health")

        assert resposta.status_code == 200
        assert resposta.json() == {
            "status": "ok",
            "banco": "ok",
            "versao": resposta.json()["versao"],
        }
