"""Testes do hash de senha e dos tokens JWT."""

from datetime import timedelta

import jwt
import pytest

from app.config import config
from app.database import agora_utc
from app.security import criar_token, gerar_hash_senha, ler_token, senha_confere


class TestHashDeSenha:
    def test_senha_correta_confere(self) -> None:
        hash_gerado = gerar_hash_senha("minhaSenha123")
        assert senha_confere("minhaSenha123", hash_gerado) is True

    def test_senha_errada_nao_confere(self) -> None:
        hash_gerado = gerar_hash_senha("minhaSenha123")
        assert senha_confere("outraSenha", hash_gerado) is False

    def test_mesma_senha_gera_hashes_diferentes(self) -> None:
        """O sal aleatorio impede descobrir senhas iguais comparando hashes."""
        assert gerar_hash_senha("igual") != gerar_hash_senha("igual")

    def test_a_senha_original_nao_aparece_no_hash(self) -> None:
        assert "minhaSenha123" not in gerar_hash_senha("minhaSenha123")

    def test_recusa_senha_acima_do_limite_do_bcrypt(self) -> None:
        with pytest.raises(ValueError, match="72 bytes"):
            gerar_hash_senha("x" * 73)

    def test_hash_malformado_nao_derruba_a_verificacao(self) -> None:
        assert senha_confere("qualquer", "isso-nao-e-um-hash") is False


class TestToken:
    def test_token_devolve_o_usuario_que_o_gerou(self) -> None:
        assert ler_token(criar_token(42)) == 42

    def test_token_alterado_e_recusado(self) -> None:
        token = criar_token(42)
        # Troca o ultimo caractere, invalidando a assinatura.
        adulterado = token[:-1] + ("A" if token[-1] != "A" else "B")
        with pytest.raises(jwt.InvalidTokenError):
            ler_token(adulterado)

    def test_token_assinado_com_outro_segredo_e_recusado(self) -> None:
        intruso = jwt.encode({"sub": "1"}, "outro-segredo", algorithm=config.jwt_algoritmo)
        with pytest.raises(jwt.InvalidTokenError):
            ler_token(intruso)

    def test_token_expirado_e_recusado(self) -> None:
        passado = agora_utc() - timedelta(hours=1)
        expirado = jwt.encode(
            {"sub": "1", "iat": passado - timedelta(hours=1), "exp": passado},
            config.jwt_segredo,
            algorithm=config.jwt_algoritmo,
        )
        with pytest.raises(jwt.ExpiredSignatureError):
            ler_token(expirado)

    def test_token_sem_identificacao_e_recusado(self) -> None:
        sem_sub = jwt.encode({"iat": agora_utc()}, config.jwt_segredo, algorithm=config.jwt_algoritmo)
        with pytest.raises(jwt.InvalidTokenError):
            ler_token(sem_sub)
