"""Testes das integracoes com o IBGE e o ViaCEP.

Nenhum teste aqui acessa a internet: o `respx` intercepta as chamadas do
`httpx` e devolve a resposta que o teste determinar. Alem de deixar a suite
rapida e previsivel, e o que torna possivel testar de proposito o que nao se
consegue provocar em um servico de terceiro - tempo limite, erro 500 e
indisponibilidade total.

O que cada bloco cobre:

* `TestMunicipios` - cache, ordenacao e a politica de nova tentativa;
* `TestCep` - traducao dos campos, CEP inexistente e CEP malformado;
* `TestFalhaDasApis` - o encadeamento cache vencido -> 503;
* `TestDiagnostico` - o `/health` nao chama as APIs externas.
"""

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from app.config import config
from app.integrations import ibge, viacep
from tests.conftest import autenticar
from tests.test_autenticacao import conferir_formato_do_problema

MUNICIPIOS = "/api/v1/localidades/municipios-go"
CEP = "/api/v1/localidades/cep/{cep}"

# Resposta do IBGE com a estrutura real, inclusive a microrregiao aninhada que
# o sistema descarta. A ordem esta trocada de proposito, para provar que a
# ordenacao e nossa.
RESPOSTA_IBGE = [
    {"id": 5222203, "nome": "Vila Propício", "microrregiao": {"id": 52008, "nome": "Entorno"}},
    {"id": 5208707, "nome": "Goiânia", "microrregiao": {"id": 52010, "nome": "Goiânia"}},
    {"id": 5200134, "nome": "Água Fria de Goiás", "microrregiao": {"id": 52008, "nome": "Entorno"}},
    {"id": 5200050, "nome": "Abadia de Goiás", "microrregiao": {"id": 52010, "nome": "Goiânia"}},
]

# Resposta do ViaCEP para 74130-010, como o servico a devolve.
RESPOSTA_VIACEP = {
    "cep": "74130-010",
    "logradouro": "Avenida Assis Chateaubriand",
    "complemento": "até 1272 - lado par",
    "unidade": "",
    "bairro": "Setor Oeste",
    "localidade": "Goiânia",
    "uf": "GO",
    "estado": "Goiás",
    "regiao": "Centro-Oeste",
    "ibge": "5208707",
    "gia": "",
    "ddd": "62",
    "siafi": "9373",
}


@pytest.fixture(autouse=True)
def cache_vazio():
    """Zera os caches antes e depois de cada teste.

    Os caches sao globais ao processo de proposito: e o que permite que uma
    consulta sirva todos os usuarios. Em troca, o teste precisa limpa-los, ou
    o resultado passaria a depender da ordem em que os testes rodam.
    """
    ibge.cache.limpar()
    viacep.cache.limpar()
    yield
    ibge.cache.limpar()
    viacep.cache.limpar()


def url_do_cep(cep: str) -> str:
    """URL que o sistema chama no ViaCEP para um CEP so com digitos."""
    return viacep.URL_CONSULTA.format(cep=cep)


class TestMunicipios:
    @respx.mock
    def test_lista_reduzida_e_em_ordem_alfabetica(
        self, cliente: TestClient, dados: dict
    ) -> None:
        """A resposta traz apenas codigo e nome, na ordem que uma pessoa espera."""
        respx.get(ibge.URL_MUNICIPIOS).mock(httpx.Response(200, json=RESPOSTA_IBGE))
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        resposta = cliente.get(MUNICIPIOS, headers=cabecalho)

        assert resposta.status_code == 200
        assert resposta.headers["X-Fonte"] == "api"

        corpo = resposta.json()
        # A microrregiao que o IBGE envia nao aparece na nossa resposta.
        assert set(corpo[0]) == {"codigo", "nome"}
        # "Água Fria" vem depois de "Abadia" e antes de "Goiânia": a ordenacao
        # ignora o acento.
        assert [municipio["nome"] for municipio in corpo] == [
            "Abadia de Goiás",
            "Água Fria de Goiás",
            "Goiânia",
            "Vila Propício",
        ]
        assert corpo[2]["codigo"] == "5208707"

    @respx.mock
    def test_segunda_consulta_sai_do_cache(self, cliente: TestClient, dados: dict) -> None:
        """A API externa e chamada uma vez, nao duas."""
        rota = respx.get(ibge.URL_MUNICIPIOS).mock(httpx.Response(200, json=RESPOSTA_IBGE))
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        primeira = cliente.get(MUNICIPIOS, headers=cabecalho)
        segunda = cliente.get(MUNICIPIOS, headers=cabecalho)

        assert rota.call_count == 1
        assert primeira.headers["X-Fonte"] == "api"
        assert segunda.headers["X-Fonte"] == "cache"
        assert primeira.json() == segunda.json()

    @respx.mock
    def test_falha_passageira_e_repetida(self, cliente: TestClient, dados: dict) -> None:
        """Um erro 500 e tentado de novo, e a segunda resposta atende o usuario."""
        rota = respx.get(ibge.URL_MUNICIPIOS).mock(
            side_effect=[httpx.Response(500), httpx.Response(200, json=RESPOSTA_IBGE)]
        )
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        resposta = cliente.get(MUNICIPIOS, headers=cabecalho)

        assert rota.call_count == config.http_tentativas == 2
        assert resposta.status_code == 200

    @respx.mock
    def test_erro_de_requisicao_nao_e_repetido(
        self, cliente: TestClient, dados: dict
    ) -> None:
        """Um 4xx nao vale nova tentativa: a resposta seria a mesma."""
        rota = respx.get(ibge.URL_MUNICIPIOS).mock(httpx.Response(400))
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        resposta = cliente.get(MUNICIPIOS, headers=cabecalho)

        assert rota.call_count == 1
        conferir_formato_do_problema(resposta, 503, "SERVICO_EXTERNO_INDISPONIVEL")

    @respx.mock
    def test_formato_inesperado_e_tratado_como_falha(
        self, cliente: TestClient, dados: dict
    ) -> None:
        """Resposta bem formada, mas sem os campos esperados, nao vira erro 500 nosso."""
        respx.get(ibge.URL_MUNICIPIOS).mock(
            httpx.Response(200, json=[{"codigo_novo": 5208707}])
        )
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        resposta = cliente.get(MUNICIPIOS, headers=cabecalho)

        conferir_formato_do_problema(resposta, 503, "SERVICO_EXTERNO_INDISPONIVEL")

    def test_exige_autenticacao(self, cliente: TestClient, dados: dict) -> None:
        resposta = cliente.get(MUNICIPIOS)
        conferir_formato_do_problema(resposta, 401, "NAO_AUTENTICADO")


class TestCep:
    @respx.mock
    def test_endereco_chega_com_os_campos_do_cadastro(
        self, cliente: TestClient, dados: dict
    ) -> None:
        """Os nomes do ViaCEP sao traduzidos para os do nosso formulario."""
        respx.get(url_do_cep("74130010")).mock(httpx.Response(200, json=RESPOSTA_VIACEP))
        cabecalho = autenticar(cliente, "admin@teste.com.br")

        resposta = cliente.get(CEP.format(cep="74130010"), headers=cabecalho)

        assert resposta.status_code == 200
        assert resposta.headers["X-Fonte"] == "api"
        assert resposta.json() == {
            # O ViaCEP devolve "74130-010"; o sistema guarda so os digitos.
            "cep": "74130010",
            "logradouro": "Avenida Assis Chateaubriand",
            "bairro": "Setor Oeste",
            # `localidade` e `ibge` viram os nomes usados na organizacao.
            "municipio_nome": "Goiânia",
            "municipio_ibge_codigo": "5208707",
            "uf": "GO",
        }

    @respx.mock
    def test_cep_com_mascara_na_url_e_aceito(self, cliente: TestClient, dados: dict) -> None:
        """A mascara sai antes de a rota rodar, e a chamada externa usa digitos."""
        rota = respx.get(url_do_cep("74130010")).mock(
            httpx.Response(200, json=RESPOSTA_VIACEP)
        )
        cabecalho = autenticar(cliente, "admin@teste.com.br")

        resposta = cliente.get(CEP.format(cep="74130-010"), headers=cabecalho)

        assert rota.call_count == 1
        assert resposta.status_code == 200
        assert resposta.json()["cep"] == "74130010"

    @respx.mock
    def test_cep_inexistente_devolve_404_e_nao_vai_para_o_cache(
        self, cliente: TestClient, dados: dict
    ) -> None:
        """O ViaCEP responde 200 avisando do erro no corpo; para nos e um 404."""
        rota = respx.get(url_do_cep("00000000")).mock(
            httpx.Response(200, json={"erro": "true"})
        )
        cabecalho = autenticar(cliente, "admin@teste.com.br")

        primeira = cliente.get(CEP.format(cep="00000000"), headers=cabecalho)
        cliente.get(CEP.format(cep="00000000"), headers=cabecalho)

        corpo = conferir_formato_do_problema(primeira, 404, "RECURSO_NAO_ENCONTRADO")
        assert "00000-000" in corpo["detail"]
        # "Nao existe" nao e resposta para guardar: a segunda consulta pergunta
        # de novo, porque o CEP pode ter passado a existir.
        assert rota.call_count == 2

    def test_cep_malformado_e_recusado_antes_da_chamada(
        self, cliente: TestClient, dados: dict
    ) -> None:
        """Formato errado e erro de validacao nosso, apontando o campo."""
        cabecalho = autenticar(cliente, "admin@teste.com.br")

        resposta = cliente.get(CEP.format(cep="123"), headers=cabecalho)

        corpo = conferir_formato_do_problema(resposta, 422, "DADOS_INVALIDOS")
        assert corpo["erros"][0]["campo"] == "cep"

    @respx.mock
    def test_segunda_consulta_do_mesmo_cep_sai_do_cache(
        self, cliente: TestClient, dados: dict
    ) -> None:
        rota = respx.get(url_do_cep("74130010")).mock(
            httpx.Response(200, json=RESPOSTA_VIACEP)
        )
        cabecalho = autenticar(cliente, "admin@teste.com.br")

        cliente.get(CEP.format(cep="74130010"), headers=cabecalho)
        segunda = cliente.get(CEP.format(cep="74130010"), headers=cabecalho)

        assert rota.call_count == 1
        assert segunda.headers["X-Fonte"] == "cache"


class TestFalhaDasApis:
    """O comportamento quando a API externa esta fora do ar."""

    @respx.mock
    def test_sem_cache_a_falha_vira_503(self, cliente: TestClient, dados: dict) -> None:
        """Unica situacao em que a queda do terceiro chega ao usuario."""
        respx.get(ibge.URL_MUNICIPIOS).mock(side_effect=httpx.ConnectTimeout)
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        resposta = cliente.get(MUNICIPIOS, headers=cabecalho)

        corpo = conferir_formato_do_problema(resposta, 503, "SERVICO_EXTERNO_INDISPONIVEL")
        assert "IBGE" in corpo["detail"]

    @respx.mock
    def test_com_cache_vencido_a_tela_continua_funcionando(
        self, cliente: TestClient, dados: dict, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Validade zero forca o vencimento; a API cai e o cache antigo atende."""
        monkeypatch.setattr(config, "cache_municipios_ttl", 0)
        rota = respx.get(ibge.URL_MUNICIPIOS).mock(httpx.Response(200, json=RESPOSTA_IBGE))
        cabecalho = autenticar(cliente, "gerador@teste.com.br")

        primeira = cliente.get(MUNICIPIOS, headers=cabecalho)
        assert primeira.headers["X-Fonte"] == "api"

        rota.mock(side_effect=httpx.ConnectTimeout)
        segunda = cliente.get(MUNICIPIOS, headers=cabecalho)

        assert segunda.status_code == 200
        # O aviso de que o dado e antigo, para o front-end poder mostra-lo.
        assert segunda.headers["X-Fonte"] == "cache-expirado"
        assert segunda.json() == primeira.json()

    @respx.mock
    def test_viacep_fora_do_ar_sem_cache_vira_503(
        self, cliente: TestClient, dados: dict
    ) -> None:
        respx.get(url_do_cep("75020000")).mock(side_effect=httpx.ConnectTimeout)
        cabecalho = autenticar(cliente, "admin@teste.com.br")

        resposta = cliente.get(CEP.format(cep="75020000"), headers=cabecalho)

        corpo = conferir_formato_do_problema(resposta, 503, "SERVICO_EXTERNO_INDISPONIVEL")
        assert "ViaCEP" in corpo["detail"]


class TestDiagnostico:
    @respx.mock
    def test_health_nao_chama_as_apis_externas(
        self, cliente: TestClient, dados: dict
    ) -> None:
        """Prova pelo proprio respx que o diagnostico nao depende de terceiros.

        Apenas a rota de municipios esta registrada. Se o `/health` tentasse
        consultar o IBGE de novo ou o ViaCEP, o `respx` recusaria a chamada e
        o teste falharia.
        """
        respx.get(ibge.URL_MUNICIPIOS).mock(httpx.Response(200, json=RESPOSTA_IBGE))
        cabecalho = autenticar(cliente, "gerador@teste.com.br")
        cliente.get(MUNICIPIOS, headers=cabecalho)

        resposta = cliente.get("/health")

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["status"] == "ok"
        # Uma consulta de municipios guardada, nenhum CEP.
        assert corpo["cache_externo"] == {"municipios": 1, "ceps": 0}
