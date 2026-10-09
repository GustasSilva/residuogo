"""Conversao e formatacao de datas entre UTC e o fuso local.

O sistema guarda todo instante em UTC (ver `database.py`), mas o usuario pensa
em horario de Goias: o periodo "01/10 a 31/10" e o mes dele, nao o mes em UTC.
Esta diferenca aparece em tres lugares - filtros de periodo, numero do
manifesto e relatorios - e e sutil: um manifesto destinado as 22h do dia 31
seria contado no mes seguinte se o recorte fosse feito em UTC.

Concentrar a conversao aqui garante que os tres usem exatamente o mesmo
critario. O fuso vem da configuracao (`fuso_local`), nao fixo no codigo.
"""

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.config import config


def fuso_local() -> ZoneInfo:
    """Fuso configurado para o sistema (por padrao, America/Sao_Paulo)."""
    return ZoneInfo(config.fuso_local)


def hoje_local() -> date:
    """Data de hoje no fuso local.

    `date.today()` usa o fuso do servidor, que pode estar em UTC: as 21h de
    Goias ele ja responderia o dia seguinte.
    """
    return datetime.now(fuso_local()).date()


def inicio_do_dia_em_utc(dia: date) -> datetime:
    """Instante UTC em que o dia local informado comeca.

    Usado nos filtros de periodo: a comparacao acontece em UTC, que e como as
    datas estao gravadas, mas o recorte e o do dia local.
    """
    return datetime.combine(dia, time.min, tzinfo=fuso_local()).astimezone(timezone.utc)


def em_local(momento: datetime) -> datetime:
    """Converte um instante UTC para o fuso local."""
    return momento.astimezone(fuso_local())


def formatar(momento: datetime | None) -> str:
    """Data e hora no formato brasileiro, em horario local ("09/10/2026 14:35")."""
    return "" if momento is None else f"{em_local(momento):%d/%m/%Y %H:%M}"


def formatar_data(momento: datetime | date | None) -> str:
    """Apenas a data, em horario local ("09/10/2026")."""
    if momento is None:
        return ""
    if isinstance(momento, datetime):
        momento = em_local(momento).date()
    return f"{momento:%d/%m/%Y}"


def primeiro_dia_do_mes(referencia: date, meses_atras: int = 0) -> date:
    """Primeiro dia do mes de `referencia`, recuando `meses_atras` meses.

    O calculo passa pelo numero absoluto do mes (ano x 12 + mes) para nao
    precisar tratar a virada de ano como caso especial.
    """
    total_de_meses = referencia.year * 12 + (referencia.month - 1) - meses_atras
    return date(total_de_meses // 12, total_de_meses % 12 + 1, 1)


def ultimo_dia_do_mes(referencia: date) -> date:
    """Ultimo dia do mes de `referencia`.

    Obtido como o dia anterior ao primeiro dia do mes seguinte (recuar menos
    um mes e avancar um), o que dispensa saber quantos dias o mes tem e acerta
    fevereiro em ano bissexto.
    """
    return primeiro_dia_do_mes(referencia, meses_atras=-1) - timedelta(days=1)
