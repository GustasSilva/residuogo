"""Formato das respostas da API, usado tambem pela documentacao em /docs."""

from pydantic import BaseModel


class Municipio(BaseModel):
    codigo: str
    nome: str
    regiao: str


class Material(BaseModel):
    chave: str
    rotulo: str


class Origem(BaseModel):
    descricao: str
    latitude: float
    longitude: float
    precisao: str


class Ponto(BaseModel):
    nome: str
    tipo: str
    endereco: str
    latitude: float
    longitude: float
    distancia_km: float
    materiais: list[Material]
    telefone: str
    horario: str


class RespostaPontos(BaseModel):
    origem: Origem
    raio_km: int
    material: str | None
    total: int
    pontos: list[Ponto]
    fora_do_raio: bool  # nada no raio: a lista traz os mais proximos numa area maior
