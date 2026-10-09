"""Testes das validacoes de CNPJ e CEP.

Logica pura, sem banco nem HTTP: sao os testes mais rapidos da suite e os que
protegem a regra mais facil de quebrar sem perceber.
"""

import pytest

from app.validacoes import (
    apenas_digitos,
    cnpj_valido,
    completar_cnpj,
    formatar_cnpj,
    normalizar_cep,
    normalizar_cnpj,
)


class TestCnpj:
    @pytest.mark.parametrize(
        "cnpj",
        [
            "11.222.333/0001-81",  # com mascara
            "11222333000181",  # sem mascara
            "00.000.000/0001-91",
        ],
    )
    def test_aceita_cnpj_valido(self, cnpj: str) -> None:
        assert cnpj_valido(cnpj) is True

    @pytest.mark.parametrize(
        ("cnpj", "motivo"),
        [
            ("11.222.333/0001-82", "digito verificador errado"),
            ("11222333000", "digitos faltando"),
            ("11222333000181999", "digitos sobrando"),
            ("00000000000000", "todos os digitos iguais"),
            ("11111111111111", "todos os digitos iguais"),
            ("", "vazio"),
            ("abcdefghijklmn", "sem digitos"),
        ],
    )
    def test_recusa_cnpj_invalido(self, cnpj: str, motivo: str) -> None:
        assert cnpj_valido(cnpj) is False, f"deveria recusar: {motivo}"

    def test_normalizar_remove_a_mascara(self) -> None:
        assert normalizar_cnpj("11.222.333/0001-81") == "11222333000181"

    def test_normalizar_levanta_erro_em_cnpj_invalido(self) -> None:
        with pytest.raises(ValueError, match="CNPJ inválido"):
            normalizar_cnpj("11.222.333/0001-82")

    def test_completar_gera_cnpj_que_passa_na_validacao(self) -> None:
        """Garante que os dados ficticios do seed e dos testes sao validos."""
        cnpj = completar_cnpj("112223330001")
        assert cnpj == "11222333000181"
        assert cnpj_valido(cnpj)

    def test_completar_exige_doze_digitos(self) -> None:
        with pytest.raises(ValueError, match="12 dígitos"):
            completar_cnpj("1122233")

    def test_formatar_aplica_a_mascara(self) -> None:
        assert formatar_cnpj("11222333000181") == "11.222.333/0001-81"


class TestCep:
    def test_normalizar_remove_o_hifen(self) -> None:
        assert normalizar_cep("74000-000") == "74000000"

    @pytest.mark.parametrize("cep", ["7400000", "740000000", "", "abcdefgh"])
    def test_recusa_cep_com_tamanho_errado(self, cep: str) -> None:
        with pytest.raises(ValueError, match="8 dígitos"):
            normalizar_cep(cep)


def test_apenas_digitos_descarta_o_resto() -> None:
    assert apenas_digitos("11.222-333/0001 81") == "11222333000181"
