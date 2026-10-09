"""Normalizacao e validacao de documentos brasileiros.

Separado dos schemas porque e logica pura, sem dependencia de framework: pode
ser testada isoladamente e reaproveitada pelo servico SOAP, que recebe CNPJ
como parametro e nao passa pelo Pydantic.

Convencao do projeto: CNPJ e CEP sao guardados **somente com digitos**. A
mascara ("00.000.000/0001-00") existe apenas na exibicao. Guardar os dois
formatos no banco tornaria a restricao de unicidade inutil, porque o mesmo
CNPJ poderia ser cadastrado duas vezes com pontuacao diferente.
"""

# Pesos usados no calculo dos digitos verificadores do CNPJ. A sequencia
# comeca em 2 e sobe ate 9, reiniciando - e definida pela Receita Federal.
_PESOS_PRIMEIRO_DIGITO = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_SEGUNDO_DIGITO = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)


def apenas_digitos(texto: str) -> str:
    """Remove tudo que nao for digito."""
    return "".join(caractere for caractere in texto if caractere.isdigit())


def _digito_verificador(digitos: str, pesos: tuple[int, ...]) -> str:
    """Calcula um digito verificador pelo metodo do modulo 11.

    Multiplica cada digito pelo seu peso, soma tudo e tira o resto por 11.
    Resto menor que 2 resulta em digito zero; nos outros casos, o digito e
    11 menos o resto.
    """
    soma = sum(int(digito) * peso for digito, peso in zip(digitos, pesos))
    resto = soma % 11
    return "0" if resto < 2 else str(11 - resto)


def cnpj_valido(cnpj: str) -> bool:
    """Confere se o CNPJ tem 14 digitos e digitos verificadores coerentes.

    Validar os digitos verificadores (e nao apenas o tamanho) e o que impede
    o cadastro de numeros digitados errado ou inventados, que depois
    inviabilizariam cruzar os dados com orgaos ambientais.
    """
    digitos = apenas_digitos(cnpj)

    if len(digitos) != 14:
        return False

    # Sequencias de um unico digito repetido passam no calculo do modulo 11,
    # mas nao sao CNPJ validos; precisam ser recusadas explicitamente.
    if digitos == digitos[0] * 14:
        return False

    primeiro = _digito_verificador(digitos[:12], _PESOS_PRIMEIRO_DIGITO)
    segundo = _digito_verificador(digitos[:13], _PESOS_SEGUNDO_DIGITO)
    return digitos[12:] == primeiro + segundo


def normalizar_cnpj(valor: str) -> str:
    """Devolve o CNPJ apenas com digitos, recusando o que for invalido.

    Levanta `ValueError`, que o Pydantic converte automaticamente em erro de
    validacao 422 com o nome do campo.
    """
    digitos = apenas_digitos(valor)
    if not cnpj_valido(digitos):
        raise ValueError("CNPJ inválido: verifique os dígitos informados.")
    return digitos


def normalizar_cep(valor: str) -> str:
    """Devolve o CEP apenas com digitos, exigindo os 8 digitos."""
    digitos = apenas_digitos(valor)
    if len(digitos) != 8:
        raise ValueError("CEP deve ter 8 dígitos.")
    return digitos


def formatar_cnpj(cnpj: str) -> str:
    """Aplica a mascara do CNPJ para exibicao (PDF e telas)."""
    digitos = apenas_digitos(cnpj)
    if len(digitos) != 14:
        return cnpj
    return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:]}"


def formatar_cep(cep: str) -> str:
    """Aplica a mascara do CEP para exibicao."""
    digitos = apenas_digitos(cep)
    if len(digitos) != 8:
        return cep
    return f"{digitos[:5]}-{digitos[5:]}"


def completar_cnpj(base: str) -> str:
    """Calcula os dois digitos verificadores de uma base de 12 digitos.

    Serve para montar CNPJ ficticios que passam na validacao do sistema - o
    que os dados de demonstracao (`scripts/seed.py`) e os testes precisam.
    Inventar os digitos a mao produziria CNPJ que o proprio sistema recusa.
    """
    digitos = apenas_digitos(base)
    if len(digitos) != 12:
        raise ValueError("A base do CNPJ deve ter exatamente 12 dígitos.")

    primeiro = _digito_verificador(digitos, _PESOS_PRIMEIRO_DIGITO)
    segundo = _digito_verificador(digitos + primeiro, _PESOS_SEGUNDO_DIGITO)
    return digitos + primeiro + segundo
