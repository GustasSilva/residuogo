"""Configuracao da aplicacao.

Todos os parametros ajustaveis ficam concentrados aqui e podem ser
sobrescritos por variaveis de ambiente ou por um arquivo `.env` na raiz do
backend. Os valores padrao sao suficientes para rodar o projeto sem nenhuma
configuracao previa.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Configuracao(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_nome: str = "ResíduoGO"
    app_versao: str = "1.0.0"

    # SQLite em arquivo: nao exige servidor de banco instalado.
    # Para migrar para PostgreSQL basta trocar esta URL.
    database_url: str = "sqlite:///./residuogo.db"

    # Chave de assinatura do JWT. Em um sistema real viria do ambiente e
    # nunca do codigo; aqui o padrao existe para o projeto rodar sem setup.
    jwt_segredo: str = "troque-este-segredo-em-producao"
    jwt_algoritmo: str = "HS256"
    jwt_expiracao_minutos: int = 480  # 8 horas: cobre um dia de uso

    # Custo do bcrypt: cada unidade dobra o tempo de calculo do hash. O padrao
    # 12 e o recomendado para uso real; a suite de testes o reduz para que
    # centenas de logins nao levem minutos.
    bcrypt_custo: int = 12

    # Origens liberadas no CORS (porta padrao do Vite no front-end).
    cors_origens: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Integracoes externas (IBGE e ViaCEP).
    http_timeout_segundos: float = 5.0
    http_tentativas: int = 2  # 1 chamada original + 1 nova tentativa

    # Fuso usado onde a data local importa: o ano do numero do manifesto e os
    # periodos dos relatorios. O armazenamento continua sempre em UTC.
    fuso_local: str = "America/Sao_Paulo"

    # Validade do cache em memoria das APIs externas, em segundos.
    cache_municipios_ttl: int = 60 * 60 * 24 * 30  # 30 dias
    cache_cep_ttl: int = 60 * 60 * 24 * 7  # 7 dias


config = Configuracao()
