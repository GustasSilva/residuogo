"""Testes da correcao de um tipo do catalogo de residuos."""

from fastapi.testclient import TestClient

from tests.conftest import autenticar
from tests.test_autenticacao import conferir_formato_do_problema

CORRECAO = {"descricao": "Tecido animal", "classe": "I", "unidade_padrao": "KG"}


class TestCorrecao:
    def test_admin_corrige_o_tipo(self, cliente: TestClient, dados: dict) -> None:
        admin = autenticar(cliente, "admin@teste.com.br")

        resposta = cliente.put(
            f"/api/v1/tipos-residuo/{dados['tipo_residuo'].id}", headers=admin, json=CORRECAO
        )

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["descricao"] == "Tecido animal"
        assert corpo["classe"] == "I"
        assert corpo["unidade_padrao"] == "KG"

    def test_codigo_nao_muda(self, cliente: TestClient, dados: dict) -> None:
        """Enviado no corpo, o codigo e ignorado: ele identifica o residuo."""
        admin = autenticar(cliente, "admin@teste.com.br")
        codigo_original = dados["tipo_residuo"].codigo

        resposta = cliente.put(
            f"/api/v1/tipos-residuo/{dados['tipo_residuo'].id}",
            headers=admin,
            json={**CORRECAO, "codigo": "999999"},
        )

        assert resposta.json()["codigo"] == codigo_original

    def test_usuario_comum_nao_corrige(self, cliente: TestClient, dados: dict) -> None:
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        resposta = cliente.put(
            f"/api/v1/tipos-residuo/{dados['tipo_residuo'].id}", headers=cabecalho, json=CORRECAO
        )

        conferir_formato_do_problema(resposta, 403, "PERMISSAO_NEGADA")

    def test_tipo_inexistente_devolve_404(self, cliente: TestClient, dados: dict) -> None:
        admin = autenticar(cliente, "admin@teste.com.br")

        resposta = cliente.put("/api/v1/tipos-residuo/9999", headers=admin, json=CORRECAO)

        conferir_formato_do_problema(resposta, 404, "RECURSO_NAO_ENCONTRADO")
