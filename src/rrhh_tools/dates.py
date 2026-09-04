"""Parseo de las fechas relativas de LinkedIn.

LinkedIn no da fecha absoluta en las tarjetas: da "hace 2 semanas". Eso es un
rango, no un instante. Devolvemos el punto medio del rango junto con una
CONFIANZA, y el scoring pondera la frescura por esa confianza. Nunca se
renderiza una fecha exacta inventada a partir de un texto impreciso.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from .normalize import strip_accents

# unidad -> (dias por unidad, confianza del punto medio)
_UNITS: dict[str, tuple[float, float]] = {
    "segundo": (0.0, 1.0), "second": (0.0, 1.0),
    "minuto": (0.0, 1.0), "minute": (0.0, 1.0),
    "hora": (0.04, 1.0), "hour": (0.04, 1.0),
    "dia": (1.0, 1.0), "day": (1.0, 1.0),
    "semana": (7.0, 0.6), "week": (7.0, 0.6),
    "mes": (30.0, 0.3), "month": (30.0, 0.3),
    "ano": (365.0, 0.2), "year": (365.0, 0.2),
}

_REL = re.compile(
    r"(?:hace\s+)?(\d+)\s*"
    r"(segundos?|minutos?|horas?|dias?|semanas?|meses|mes|anos?|"
    r"seconds?|minutes?|hours?|days?|weeks?|months?|years?)"
    r"(?:\s+ago)?",
    re.IGNORECASE,
)
_JUST_NOW = re.compile(r"\b(justo ahora|ahora mismo|just now|hoy|today|new|nuevo)\b", re.I)


def _singular(unit: str) -> str:
    """Singulariza la unidad.

    "mes" y "meses" son el caso especial: un rstrip("s") ingenuo convierte
    "mes" en "me" y deja de reconocerse.
    """
    u = unit.lower()
    if u in ("mes", "meses"):
        return "mes"
    return u.rstrip("s")


def parse_relative_date(text: str | None, today: date | None = None) -> tuple[date | None, float]:
    """'hace 2 semanas' -> (fecha estimada, confianza).

    Devuelve (None, 0.5) si no se reconoce nada: en el scoring, 0.5 es el
    valor neutro de frescura, para no premiar ni castigar lo desconocido.
    """
    if not text:
        return None, 0.5
    today = today or date.today()
    normalized = strip_accents(text).lower()

    if _JUST_NOW.search(normalized):
        return today, 1.0

    match = _REL.search(normalized)
    if not match:
        return None, 0.5

    amount = int(match.group(1))
    unit = _singular(match.group(2))
    if unit not in _UNITS:
        return None, 0.5

    days_per_unit, confidence = _UNITS[unit]
    days_ago = amount * days_per_unit
    # Punto medio del rango: "hace 2 semanas" cubre entre 14 y 21 dias atras.
    if days_per_unit >= 7:
        days_ago += days_per_unit / 2
    return today - timedelta(days=round(days_ago)), confidence


def days_since(posted: date | None, today: date | None = None) -> int | None:
    if posted is None:
        return None
    return ((today or date.today()) - posted).days
