"""Testes do cadastro de organizacoes e das permissoes por perfil.

O teste mais importante deste arquivo e o do filtro `apenas_aptas`: ele cobre
a regra RN04 (licenca valida) no ponto em que ela e exposta ao front-end.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.enums import PapelOrganizacao
from app.errors import LicencaVencida, PapelInvalido
from app.services import organizacoes as servico
from tests.conftest import autenticar
from tests.test_autenticacao import conferir_formato_do_problema


def nova_organizacao(**ajustes) -> dict:
    """Monta o corpo de uma organizacao valida, permitindo sobrescrever campos."""
    corpo = {
        "razao_social": "Nova Empresa Ltda",
        "cnpj": "22.333.444/0001-81",
        "papel": "GERADOR",
        "cep": "74000-000",
        "logradouro": "Avenida Goiás",
        "numero": "500",
        "bairro": "Centro",
        "municipio_ibge_codigo": "5208707",
        "municipio_nome": "Goiânia",
        "licenca_numero": "LO-GO-2025-999",
        "licenca_validade": "2028-01-31",
    }
    corpo.update(ajustes)
    return corpo


class TestCadastro:
    def test_admin_cadastra_organizacao(self, cliente: TestClient, dados: dict) -> None:
        cabecalho = autenticar(cliente, "admin@teste.com.br")

        resposta = cliente.post("/api/v1/organizacoes", headers=cabecalho, json=nova_organizacao())

        assert resposta.status_code == 201
        corpo = resposta.json()
        # O CNPJ entrou com mascara e foi gravado somente com digitos.
        assert corpo["cnpj"] == "22333444000181"
        assert corpo["cep"] == "74000000"
        assert corpo["ativo"] is True

    def test_usuario_comum_nao_cadastra(self, cliente: TestClient, dados: dict) -> None:
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        resposta = cliente.post("/api/v1/organizacoes", headers=cabecalho, json=nova_organizacao())

        conferir_formato_do_problema(resposta, 403, "PERMISSAO_NEGADA")

    def test_sem_token_nao_cadastra(self, cliente: TestClient, dados: dict) -> None:
        resposta = cliente.post("/api/v1/organizacoes", json=nova_organizacao())
        conferir_formato_do_problema(resposta, 401, "NAO_AUTENTICADO")

    def test_cnpj_invalido_e_recusado(self, cliente: TestClient, dados: dict) -> None:
        cabecalho = autenticar(cliente, "admin@teste.com.br")

        resposta = cliente.post(
            "/api/v1/organizacoes",
            headers=cabecalho,
            json=nova_organizacao(cnpj="22.333.444/0001-99"),
        )

        corpo = conferir_formato_do_problema(resposta, 422, "DADOS_INVALIDOS")
        assert any(erro["campo"] == "cnpj" for erro in corpo["erros"])

    def test_cnpj_repetido_e_recusado(self, cliente: TestClient, dados: dict) -> None:
        cabecalho = autenticar(cliente, "admin@teste.com.br")
        cnpj_existente = dados["gerador"].cnpj

        resposta = cliente.post(
            "/api/v1/organizacoes",
            headers=cabecalho,
            json=nova_organizacao(cnpj=cnpj_existente),
        )

        corpo = conferir_formato_do_problema(resposta, 409, "CONFLITO")
        assert dados["gerador"].razao_social in corpo["detail"]


class TestListagem:
    def test_apenas_aptas_exclui_licenca_vencida(self, cliente: TestClient, dados: dict) -> None:
        """A regra RN04 vista pela listagem.

        Ha duas transportadoras no cenario; apenas uma tem licenca valida. A
        tela de novo manifesto usa este filtro, de modo que o usuario nunca
        consiga escolher uma transportadora que a emissao recusaria.
        """
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        todas = cliente.get(
            "/api/v1/organizacoes", headers=cabecalho, params={"papel": "TRANSPORTADOR"}
        ).json()
        aptas = cliente.get(
            "/api/v1/organizacoes",
            headers=cabecalho,
            params={"papel": "TRANSPORTADOR", "apenas_aptas": True},
        ).json()

        assert todas["total"] == 2
        assert aptas["total"] == 1
        assert aptas["itens"][0]["razao_social"] == dados["transportador"].razao_social

    def test_filtro_por_papel(self, cliente: TestClient, dados: dict) -> None:
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        corpo = cliente.get(
            "/api/v1/organizacoes", headers=cabecalho, params={"papel": "DESTINADOR"}
        ).json()

        assert corpo["total"] == 1
        assert corpo["itens"][0]["papel"] == "DESTINADOR"

    def test_busca_por_razao_social(self, cliente: TestClient, dados: dict) -> None:
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        corpo = cliente.get(
            "/api/v1/organizacoes", headers=cabecalho, params={"busca": "Destinador"}
        ).json()

        assert corpo["total"] == 1

    def test_paginacao_divide_o_resultado(self, cliente: TestClient, dados: dict) -> None:
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        corpo = cliente.get(
            "/api/v1/organizacoes", headers=cabecalho, params={"tamanho": 2}
        ).json()

        assert corpo["total"] == 4  # o cenario tem 4 organizacoes
        assert len(corpo["itens"]) == 2
        assert corpo["paginas"] == 2

    def test_tamanho_de_pagina_acima_do_limite_e_recusado(
        self, cliente: TestClient, dados: dict
    ) -> None:
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        resposta = cliente.get(
            "/api/v1/organizacoes", headers=cabecalho, params={"tamanho": 500}
        )

        conferir_formato_do_problema(resposta, 422, "DADOS_INVALIDOS")

    def test_organizacao_inexistente_devolve_404(self, cliente: TestClient, dados: dict) -> None:
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        resposta = cliente.get("/api/v1/organizacoes/9999", headers=cabecalho)

        conferir_formato_do_problema(resposta, 404, "RECURSO_NAO_ENCONTRADO")


class TestRegraDeAptidao:
    """Testes diretos do servico, sem passar pela API.

    A mesma regra que a listagem usa como filtro SQL e aplicada aqui a um
    objeto carregado. Os dois caminhos precisam concordar: e isso que garante
    que o front-end e o back-end nunca divirjam sobre quem esta apto.
    """

    def test_organizacao_regular_passa(self, dados: dict) -> None:
        servico.exigir_apta(
            dados["transportador"], PapelOrganizacao.TRANSPORTADOR, "transportador"
        )

    def test_licenca_vencida_levanta_erro(self, dados: dict) -> None:
        with pytest.raises(LicencaVencida) as erro:
            servico.exigir_apta(
                dados["transportador_vencido"], PapelOrganizacao.TRANSPORTADOR, "transportador"
            )

        assert erro.value.codigo == "LICENCA_VENCIDA"
        assert erro.value.status == 422

    def test_papel_errado_levanta_erro(self, dados: dict) -> None:
        with pytest.raises(PapelInvalido) as erro:
            servico.exigir_apta(
                dados["gerador"], PapelOrganizacao.TRANSPORTADOR, "transportador"
            )

        assert erro.value.codigo == "PAPEL_INVALIDO"

    def test_organizacao_desativada_levanta_erro(self, dados: dict) -> None:
        dados["transportador"].ativo = False

        with pytest.raises(PapelInvalido, match="desativada"):
            servico.exigir_apta(
                dados["transportador"], PapelOrganizacao.TRANSPORTADOR, "transportador"
            )

    def test_licenca_que_vence_hoje_ainda_vale(self, dados: dict) -> None:
        """A comparacao e `>=`: a licenca vale durante todo o dia do vencimento."""
        dados["transportador"].licenca_validade = date.today()

        servico.exigir_apta(
            dados["transportador"], PapelOrganizacao.TRANSPORTADOR, "transportador"
        )

    def test_licenca_vencida_ontem_nao_vale(self, dados: dict) -> None:
        dados["transportador"].licenca_validade = date.today() - timedelta(days=1)

        with pytest.raises(LicencaVencida):
            servico.exigir_apta(
                dados["transportador"], PapelOrganizacao.TRANSPORTADOR, "transportador"
            )
