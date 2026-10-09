"""Ponto de entrada da aplicacao.

Monta o app FastAPI e liga as pecas construidas nos outros modulos: as rotas
REST, o servico SOAP, os tradutores de erro e o CORS.

Para executar:

    uvicorn app.main:app --reload

Enderecos uteis depois de subir:

* http://127.0.0.1:8000/docs          - Swagger (documentacao interativa do REST)
* http://127.0.0.1:8000/soap/manifesto?wsdl - contrato WSDL do servico SOAP
* http://127.0.0.1:8000/health        - diagnostico da aplicacao
"""

import logging
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import config
from app.database import criar_tabelas
from app.dependencies import Sessao
from app.errors import registrar_handlers
from app.integrations import externo, ibge, viacep
from app.integrations.externo import CABECALHO_FONTE
from app.routers import (
    auth,
    localidades,
    manifestos,
    organizacoes,
    tipos_residuo,
    usuarios,
)
from app.soap import router as soap

# Formato de log com o horario e o nivel, para que a saida do servidor possa
# ser lida durante a apresentacao sem ferramenta auxiliar.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger("residuogo")

DESCRICAO = """
Sistema de rastreamento de resíduos sólidos para organizações do estado de Goiás.

Registra o ciclo completo de um lote de resíduo — **gerador → transportador →
destinador** — em um manifesto digital, que cada participante atualiza por esta API.

O sistema expõe os dois estilos de web service:

* **REST**, documentado aqui, em `/api/v1`;
* **SOAP**, com contrato WSDL em `/soap/manifesto?wsdl`.

Todas as respostas de erro seguem a **RFC 7807** (`application/problem+json`).
"""


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    """Prepara o ambiente antes de a aplicacao comecar a atender.

    Criar as tabelas na subida dispensa uma ferramenta de migracao: o banco e
    um arquivo SQLite que pode ser apagado e recriado a vontade. O que vem
    antes do `yield` roda na inicializacao; o que vem depois, no encerramento.
    """
    criar_tabelas()
    logger.info("Banco pronto em %s", config.database_url)
    yield
    # No encerramento: fecha o cliente HTTP compartilhado das integracoes.
    externo.encerrar_cliente()


app = FastAPI(
    title=config.app_nome,
    version=config.app_versao,
    description=DESCRICAO,
    lifespan=ciclo_de_vida,
)


@app.middleware("http")
async def identificar_requisicao(request: Request, chamar_proxima) -> Response:
    """Da um identificador curto a cada requisicao.

    O identificador aparece no log do servidor e volta no cabecalho
    `X-Request-Id`. Quando um usuario relata um erro, esse codigo e o que
    permite achar no log exatamente a requisicao que falhou - sem ele, seria
    preciso procurar por horario aproximado.
    """
    request.state.id_requisicao = uuid4().hex[:8]
    resposta = await chamar_proxima(request)
    resposta.headers["X-Request-Id"] = request.state.id_requisicao
    return resposta


# Adicionado por ultimo para ficar na camada mais externa: assim as respostas
# de erro tambem recebem os cabecalhos de CORS e o front-end consegue ler a
# mensagem do erro em vez de receber um erro de origem bloqueada.
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origens,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Cabecalhos que o navegador autoriza o front-end a ler. Sem declarar,
    # o `fetch` recebe a resposta mas nao enxerga estes dois.
    expose_headers=["X-Request-Id", CABECALHO_FONTE],
)

# Liga os tradutores de excecao -> resposta RFC 7807 (ver `errors.py`).
registrar_handlers(app)


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------

# Todas as rotas REST ficam sob /api/v1. O prefixo com versao permite, no
# futuro, publicar uma /api/v2 sem quebrar os clientes existentes.
api = APIRouter(prefix="/api/v1")
api.include_router(auth.router)
api.include_router(organizacoes.router)
api.include_router(usuarios.router)
api.include_router(tipos_residuo.router)
api.include_router(manifestos.router)
api.include_router(localidades.router)

app.include_router(api)

# O servico SOAP fica fora do prefixo /api/v1 porque nao e versionado pela
# URL: quem versiona um servico SOAP e o namespace declarado no WSDL.
app.include_router(soap.router)


@app.get("/", tags=["Diagnóstico"], summary="Identificação da aplicação")
def raiz() -> dict:
    """Aponta para a documentacao dos dois servicos."""
    return {
        "aplicacao": config.app_nome,
        "versao": config.app_versao,
        "documentacao_rest": "/docs",
        "contrato_soap": "/soap/manifesto?wsdl",
    }


@app.get("/health", tags=["Diagnóstico"], summary="Verifica se a aplicação está saudável")
def health(sessao: Sessao) -> dict:
    """Confere se a aplicacao consegue falar com o banco.

    Rota publica e deliberadamente simples: executa a consulta mais barata
    possivel (`SELECT 1`) apenas para provar que a conexao esta de pe. Nao
    devolve detalhe tecnico da falha, que iria para o log do servidor.

    Sobre as APIs externas, a rota informa apenas **quantas respostas estao em
    cache**, sem chamar o IBGE nem o ViaCEP. Consultar um terceiro aqui faria
    o diagnostico da nossa aplicacao depender da disponibilidade dele - e um
    balanceador de carga tiraria o sistema do ar por causa de uma queda que
    nao e nossa e que o cache ja cobre.
    """
    try:
        sessao.execute(text("SELECT 1"))
        banco_ok = True
    except Exception:
        logger.exception("Falha ao consultar o banco em /health")
        banco_ok = False

    return {
        "status": "ok" if banco_ok else "degradado",
        "banco": "ok" if banco_ok else "indisponivel",
        "versao": config.app_versao,
        "cache_externo": {
            "municipios": ibge.cache.tamanho(),
            "ceps": viacep.cache.tamanho(),
        },
    }
