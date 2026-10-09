"""Schemas Pydantic: o contrato publico da API.

Os models (`models.py`) descrevem o banco; os schemas descrevem o que entra e
o que sai pela API. Manter os dois separados e o que permite, por exemplo,
receber uma senha em texto e nunca devolve-la, ou aceitar um CNPJ com mascara
e guardar apenas os digitos.

Convencao de nomes usada no projeto:

* `...Criar`  - dados que o cliente envia para criar um registro;
* `...Saida`  - dados que a API devolve;
* `...Resumo` - versao reduzida, usada quando o registro aparece aninhado
                dentro de outro (evita respostas gigantes e repetidas).

As descricoes dos campos (`Field(description=...)`) aparecem automaticamente
no Swagger, em `/docs`.
"""

from datetime import date, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.enums import (
    Acondicionamento,
    ClasseResiduo,
    PapelOrganizacao,
    PerfilUsuario,
    StatusManifesto,
    TipoDestinacao,
    UnidadeMedida,
)
from app.validacoes import normalizar_cep, normalizar_cnpj, normalizar_codigo_ibge

# `from_attributes=True` autoriza o Pydantic a ler os dados de um objeto do
# SQLAlchemy (por atributo) e nao apenas de um dicionario. E o que permite
# devolver `organizacao` direto de uma rota, sem conversao manual.
LEITURA_ORM = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Paginacao
# ---------------------------------------------------------------------------

TipoItem = TypeVar("TipoItem")


class Pagina(BaseModel, Generic[TipoItem]):
    """Envelope padrao das listagens.

    Toda rota que lista registros devolve esta estrutura, com qualquer tipo de
    item dentro. Um formato unico evita que cada tela do front-end tenha de
    lidar com uma forma diferente de paginar.
    """

    itens: list[TipoItem]
    total: int = Field(description="Total de registros que atendem ao filtro.")
    pagina: int = Field(description="Pagina atual, comecando em 1.")
    tamanho: int = Field(description="Quantidade de registros por pagina.")
    paginas: int = Field(description="Numero total de paginas.")


# ---------------------------------------------------------------------------
# Autenticacao
# ---------------------------------------------------------------------------


class LoginEntrada(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=1)


class TokenSaida(BaseModel):
    """Resposta do login.

    `tipo` segue o padrao HTTP Bearer: o cliente deve enviar o token no
    cabecalho `Authorization: Bearer <token>`.
    """

    token: str
    tipo: str = "Bearer"
    expira_em_minutos: int


# ---------------------------------------------------------------------------
# Organizacao
# ---------------------------------------------------------------------------


class OrganizacaoBase(BaseModel):
    razao_social: str = Field(min_length=3, max_length=120)
    papel: PapelOrganizacao = Field(description="Posicao no ciclo do residuo.")
    cep: str = Field(description="Com ou sem mascara; e guardado so com digitos.")
    logradouro: str = Field(min_length=3, max_length=160)
    numero: str = Field(min_length=1, max_length=20)
    bairro: str = Field(min_length=2, max_length=80)
    municipio_ibge_codigo: str = Field(
        min_length=7, max_length=7, description="Codigo IBGE do municipio (7 digitos)."
    )
    municipio_nome: str = Field(min_length=2, max_length=80)
    licenca_numero: str = Field(min_length=1, max_length=40)
    licenca_validade: date = Field(description="Data de vencimento da licenca ambiental.")

    @field_validator("cep")
    @classmethod
    def _validar_cep(cls, valor: str) -> str:
        return normalizar_cep(valor)

    @field_validator("municipio_ibge_codigo")
    @classmethod
    def _validar_municipio(cls, valor: str) -> str:
        return normalizar_codigo_ibge(valor)


class OrganizacaoCriar(OrganizacaoBase):
    cnpj: str = Field(description="Com ou sem mascara; os digitos verificadores sao conferidos.")

    @field_validator("cnpj")
    @classmethod
    def _validar_cnpj(cls, valor: str) -> str:
        return normalizar_cnpj(valor)


class OrganizacaoResumo(BaseModel):
    """Organizacao como ela aparece dentro de um manifesto."""

    model_config = LEITURA_ORM

    id: int
    razao_social: str
    cnpj: str
    papel: PapelOrganizacao
    municipio_nome: str


class OrganizacaoSaida(OrganizacaoBase):
    model_config = LEITURA_ORM

    id: int
    cnpj: str
    ativo: bool
    criado_em: datetime


# ---------------------------------------------------------------------------
# Usuario
# ---------------------------------------------------------------------------


class UsuarioCriar(BaseModel):
    nome: str = Field(min_length=3, max_length=120)
    email: EmailStr
    senha: str = Field(min_length=8, max_length=72, description="Minimo de 8 caracteres.")
    perfil: PerfilUsuario = PerfilUsuario.USUARIO
    organizacao_id: int | None = Field(
        default=None, description="Obrigatorio para USUARIO; deve ficar vazio para ADMIN."
    )

    @model_validator(mode="after")
    def _validar_vinculo(self) -> "UsuarioCriar":
        """Garante a coerencia entre perfil e vinculo com organizacao.

        O ADMIN atua sobre o sistema inteiro e por isso nao pertence a nenhuma
        organizacao; o USUARIO opera em nome de uma, e sem esse vinculo nao
        haveria como decidir o que ele pode fazer (regra RN01).
        """
        if self.perfil is PerfilUsuario.ADMIN and self.organizacao_id is not None:
            raise ValueError("Usuário ADMIN não pode estar vinculado a uma organização.")
        if self.perfil is PerfilUsuario.USUARIO and self.organizacao_id is None:
            raise ValueError("Usuário comum precisa estar vinculado a uma organização.")
        return self


class UsuarioSaida(BaseModel):
    """Usuario devolvido pela API. Nunca inclui a senha nem o hash dela."""

    model_config = LEITURA_ORM

    id: int
    nome: str
    email: EmailStr
    perfil: PerfilUsuario
    ativo: bool
    organizacao_id: int | None


class UsuarioLogadoSaida(UsuarioSaida):
    """Resposta de `/auth/me`.

    Traz a organizacao completa porque o front-end precisa do papel dela para
    decidir quais botoes de acao mostrar em cada manifesto.
    """

    organizacao: OrganizacaoResumo | None


# ---------------------------------------------------------------------------
# Tipo de residuo
# ---------------------------------------------------------------------------


class TipoResiduoCriar(BaseModel):
    codigo: str = Field(
        min_length=1, max_length=20, description="Codigo da Lista Brasileira de Residuos."
    )
    descricao: str = Field(min_length=3, max_length=160)
    classe: ClasseResiduo = Field(description="Classificacao da NBR 10004.")
    unidade_padrao: UnidadeMedida


class TipoResiduoSaida(TipoResiduoCriar):
    model_config = LEITURA_ORM

    id: int


# ---------------------------------------------------------------------------
# Manifesto
# ---------------------------------------------------------------------------


class UsuarioResumo(BaseModel):
    """Autor de uma movimentacao, como aparece na linha do tempo."""

    model_config = LEITURA_ORM

    id: int
    nome: str
    perfil: PerfilUsuario


class ItemManifestoCriar(BaseModel):
    """Uma linha de residuo informada na emissao.

    `gt=0` implementa a parte da regra RN08 que exige quantidade positiva: a
    validacao acontece aqui, na entrada, para que o erro volte apontando o
    campo e o indice do item.
    """

    tipo_residuo_id: int
    quantidade_declarada: float = Field(gt=0, description="Precisa ser maior que zero.")
    unidade: UnidadeMedida
    acondicionamento: Acondicionamento


class ManifestoCriar(BaseModel):
    """Dados da emissao de um manifesto.

    O gerador nao e informado: ele e a organizacao do usuario que emite.
    `min_length=1` completa a regra RN08, que exige ao menos um item.
    """

    transportador_id: int
    destinador_id: int
    itens: list[ItemManifestoCriar] = Field(min_length=1)
    observacoes: str | None = Field(default=None, max_length=1000)


class ColetaEntrada(BaseModel):
    """Confirmacao de coleta, feita pelo transportador."""

    placa_veiculo: str = Field(min_length=7, max_length=10)
    motorista_nome: str = Field(min_length=3, max_length=120)
    observacao: str | None = Field(default=None, max_length=500)


class ItemRecebido(BaseModel):
    """Conferencia de um item na chegada ao destino."""

    item_id: int
    quantidade_recebida: float = Field(ge=0, description="Pode ser zero; nao pode ser negativa.")


class RecebimentoEntrada(BaseModel):
    """Recebimento da carga, feito pelo destinador.

    Todos os itens do manifesto precisam ser conferidos (regra RN05); quais
    faltaram e verificado no servico, que conhece os itens daquele manifesto.
    """

    itens: list[ItemRecebido] = Field(min_length=1)
    observacao: str | None = Field(default=None, max_length=500)


class RecusaEntrada(BaseModel):
    """Recusa da carga. O motivo e obrigatorio (regra RN06)."""

    motivo_recusa: str = Field(min_length=10, max_length=500, description="Obrigatório.")


class DestinacaoEntrada(BaseModel):
    """Destinacao final. O tipo de tratamento e obrigatorio (regra RN06)."""

    tipo_destinacao: TipoDestinacao
    observacao: str | None = Field(default=None, max_length=500)


class CancelamentoEntrada(BaseModel):
    """Cancelamento pelo gerador, possivel apenas antes da coleta."""

    observacao: str | None = Field(default=None, max_length=500)


class ItemManifestoSaida(BaseModel):
    model_config = LEITURA_ORM

    id: int
    tipo_residuo: TipoResiduoSaida
    quantidade_declarada: float
    quantidade_recebida: float | None
    unidade: UnidadeMedida
    acondicionamento: Acondicionamento
    divergente: bool


class MovimentacaoSaida(BaseModel):
    """Um passo da linha do tempo do manifesto."""

    model_config = LEITURA_ORM

    id: int
    status_anterior: StatusManifesto | None
    status_novo: StatusManifesto
    data_hora: datetime
    observacao: str | None
    usuario: UsuarioResumo


class ManifestoResumo(BaseModel):
    """Manifesto como aparece na listagem: sem itens, para a resposta ficar leve."""

    model_config = LEITURA_ORM

    id: int
    numero: str | None
    status: StatusManifesto
    gerador: OrganizacaoResumo
    transportador: OrganizacaoResumo
    destinador: OrganizacaoResumo
    tipo_destinacao: TipoDestinacao | None
    emitido_em: datetime
    atualizado_em: datetime


class ManifestoSaida(ManifestoResumo):
    """Manifesto completo, com itens e dados de cada etapa."""

    placa_veiculo: str | None
    motorista_nome: str | None
    motivo_recusa: str | None
    observacoes: str | None
    qr_token: str
    coletado_em: datetime | None
    recebido_em: datetime | None
    destinado_em: datetime | None
    itens: list[ItemManifestoSaida]


# ---------------------------------------------------------------------------
# Localidades (IBGE e ViaCEP)
# ---------------------------------------------------------------------------


class MunicipioSaida(BaseModel):
    """Municipio como a tela de cadastro o consome."""

    codigo: str = Field(description="Codigo IBGE do municipio, com 7 digitos.")
    nome: str


class EnderecoCepSaida(BaseModel):
    """Endereco devolvido pela consulta de CEP.

    Os nomes dos campos sao iguais aos de `OrganizacaoCriar` de proposito: a
    tela de cadastro recebe esta resposta e preenche o formulario campo a
    campo, sem traducao no meio.

    `logradouro` e `bairro` podem vir vazios: CEP de zona rural e CEP geral de
    municipio pequeno identificam a cidade, nao a rua.
    """

    cep: str = Field(description="Somente digitos, como o sistema guarda.")
    logradouro: str
    bairro: str
    municipio_nome: str
    municipio_ibge_codigo: str
    uf: str = Field(description="Sigla do estado, com 2 letras.")


# ---------------------------------------------------------------------------
# Relatorios e painel
# ---------------------------------------------------------------------------


class LinhaRelatorio(BaseModel):
    """Uma linha de qualquer agrupamento do resumo.

    Massa e volume aparecem em colunas separadas, e uma das duas costuma ser
    zero: converter volume em massa exigiria arbitrar a densidade de cada
    residuo. As duas conversoes feitas sao exatas e dentro da mesma grandeza
    (1 t = 1000 kg; 1000 L = 1 m3).
    """

    chave: str = Field(description="Identificador do grupo (codigo, classe, destinacao).")
    rotulo: str = Field(description="O mesmo grupo escrito para leitura humana.")
    massa_kg: float
    volume_m3: float
    manifestos: int = Field(description="Manifestos distintos que compoem a linha.")
    itens: int


class LinhaMensal(LinhaRelatorio):
    """Linha da serie do painel, com a data que ordena o grafico."""

    inicio: date


class DivergenciasSaida(BaseModel):
    """Itens em que o recebido diferiu do declarado acima da tolerancia (RN05)."""

    itens_conferidos: int
    itens_divergentes: int
    percentual: float


class ResumoSaida(BaseModel):
    """Resumo de um periodo, considerando apenas manifestos ja destinados."""

    inicio: date
    fim: date
    total: LinhaRelatorio
    por_tipo: list[LinhaRelatorio]
    por_classe: list[LinhaRelatorio]
    por_destinacao: list[LinhaRelatorio]
    divergencias: DivergenciasSaida


class ResumoDoMes(BaseModel):
    """Os numeros do mes corrente mostrados nos cartoes do painel."""

    inicio: date
    fim: date
    manifestos_emitidos: int = Field(description="Emitidos no mes, qualquer status.")
    manifestos_destinados: int
    massa_kg: float
    volume_m3: float


class PendentesPorStatus(BaseModel):
    """Quantos manifestos aguardam acao em cada estado nao final."""

    status: StatusManifesto
    rotulo: str
    total: int


class DesvioDeAterro(BaseModel):
    """Proporcao da massa recuperada em relacao a massa total destinada.

    `percentual` e nulo quando nada foi destinado no periodo: zero daria a
    entender que nada foi recuperado, o que e diferente de nao haver dado.
    """

    meses: int
    massa_recuperada_kg: float
    massa_total_kg: float
    percentual: float | None


class LicencaAVencer(BaseModel):
    """Licenca ambiental vencida ou proxima do vencimento.

    `dias_restantes` negativo indica licenca ja vencida - a que impede a
    emissao de novos manifestos pela regra RN04.
    """

    organizacao_id: int
    razao_social: str
    papel: PapelOrganizacao
    licenca_numero: str
    licenca_validade: date
    dias_restantes: int
    vencida: bool


class IndicadoresSaida(BaseModel):
    """Tudo o que o painel inicial mostra, em uma unica resposta.

    Reunir os seis blocos evita que a tela monte o painel com numeros apurados
    em instantes diferentes.
    """

    referencia: date
    mes: ResumoDoMes
    pendentes_por_status: list[PendentesPorStatus]
    desvio_de_aterro: DesvioDeAterro
    por_destinacao: list[LinhaRelatorio]
    serie_mensal: list[LinhaMensal]
    licencas_a_vencer: list[LicencaAVencer]
