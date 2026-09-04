"""Normalizacion de nombres de empresa, titulos y ubicaciones.

Todo lo que compara texto en este proyecto pasa antes por aqui. Es importante
que la normalizacion sea la MISMA en los dos lados de cualquier comparacion:
si la denylist se normaliza distinto que el nombre que llega de LinkedIn, el
matching falla en silencio.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

_PUNCT = re.compile(r"[^a-z0-9]+")
_WS = re.compile(r"\s+")

# Ruido de titulos de oferta: menciones de genero, modalidad y ciudad que no
# aportan nada al comparar dos titulos entre si.
_TITLE_NOISE = [
    r"\(\s*[mhfdxwv]\s*[/|]\s*[mhfdxwv]\s*([/|]\s*[mhfdxwv]\s*)?\)",  # (m/f/d), (h/m/x)
    r"\b[mhfdxwv]\s*[/|]\s*[mhfdxwv]\s*([/|]\s*[mhfdxwv])?\b",
    r"\((remoto|remote|hibrido|presencial|teletrabajo)\)",
    r"\b(remoto|remote|hibrido|hybrid|presencial|teletrabajo|onsite|on site)\b",
    r"\b(madrid|barcelona|valencia|sevilla|bilbao|malaga|espana|spain)\b",
    r"\b(full[ -]?time|part[ -]?time|jornada completa|media jornada)\b",
]

# Tokens de nivel: se quitan al construir el "nucleo" de un titulo, para que
# "Junior UX Designer" y "UX Designer" se reconozcan como el mismo puesto al
# deduplicar reposts.
_SENIORITY_TOKENS = {
    "junior", "jr", "senior", "sr", "snr", "lead", "principal", "staff",
    "becario", "becaria", "beca", "practicas", "trainee", "intern",
    "internship", "graduate", "entry", "level", "nivel", "inicial",
    "associate", "asociado", "asociada", "i", "ii", "iii", "iv",
}


def strip_accents(text: str) -> str:
    """NFKD + descarte de marcas diacriticas. 'Telefonica' -> 'telefonica'.

    Efecto secundario util: 'senior' colapsa a 'senior' sin reglas extra.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def basic_norm(text: str) -> str:
    """Minusculas, sin acentos, sin puntuacion, espacios colapsados."""
    if not text:
        return ""
    out = strip_accents(text).lower().replace("&", " and ")
    out = _PUNCT.sub(" ", out)
    return _WS.sub(" ", out).strip()


@dataclass
class NormalizedName:
    display: str
    norm: str
    tokens: set[str] = field(default_factory=set)
    compact: str = ""

    @property
    def is_short_single_token(self) -> bool:
        """Nombres cortos de un solo token no pueden usar fuzzy.

        'Indra', 'VASS', 'GFT', 'Babel' colisionarian con demasiadas cosas.
        """
        return len(self.tokens) == 1 and len(self.norm) < 8


def normalize_company_name(raw: str, legal_suffixes: set[str] | None = None) -> NormalizedName:
    """Normaliza un nombre de empresa recortando sufijos legales SOLO al final.

    Nunca en medio: 'Grupo Bimbo' debe conservar 'grupo' porque va delante y
    forma parte del nombre; 'Bimbo Grupo' si perderia el sufijo.
    """
    suffixes = legal_suffixes or set()
    norm = basic_norm(raw)
    parts = norm.split()
    # Recorte iterativo por la cola: "Acme Solutions S.L.U." -> "acme solutions".
    # Se prueban colas de hasta 4 tokens porque la puntuacion fragmenta los
    # sufijos con puntos: "S.L.U." llega ya partido en ["s", "l", "u"].
    changed = True
    while changed and parts:
        changed = False
        for k in range(min(4, len(parts)), 0, -1):
            tail = parts[-k:]
            if " ".join(tail) in suffixes or "".join(tail) in suffixes:
                del parts[-k:]
                changed = True
                break
    if not parts:  # el nombre era solo sufijos; nos quedamos con el original
        parts = norm.split()
    norm = " ".join(parts)
    return NormalizedName(
        display=raw.strip(),
        norm=norm,
        tokens=set(parts),
        compact=norm.replace(" ", ""),
    )


def normalize_title(raw: str) -> str:
    """Titulo normalizado, conservando los tokens de nivel.

    El orden importa: el ruido se limpia sobre el texto con su puntuacion
    todavia puesta. Si se quitara la puntuacion primero, "(m/f/d)" ya seria
    "m f d" y ninguna regex de ruido podria reconocerlo.
    """
    if not raw:
        return ""
    out = strip_accents(raw).lower()
    # Genero a la espanola: "disenador/a" -> "disenador", antes de tocar las barras.
    out = re.sub(r"([a-z]{3,})\s*/\s*[ao]\b", r"\1", out)
    for pattern in _TITLE_NOISE:
        out = re.sub(pattern, " ", out)
    out = _PUNCT.sub(" ", out)
    return _WS.sub(" ", out).strip()


def title_core(raw: str) -> str:
    """Nucleo del titulo: sin nivel, sin genero, sin ciudad, tokens ordenados.

    Es la clave para detectar reposts del mismo puesto con titulo retocado.
    Ordenar los tokens hace que 'UX/UI Designer' y 'Designer UI UX' coincidan.
    """
    tokens = [
        t for t in normalize_title(raw).split()
        if t not in _SENIORITY_TOKENS and len(t) > 1
    ]
    return " ".join(sorted(tokens))


def normalize_text(raw: str | None) -> str:
    """Normalizacion para descripciones largas. Conserva estructura de palabras."""
    if not raw:
        return ""
    out = strip_accents(raw).lower()
    out = re.sub(r"[^a-z0-9\s\-+/]", " ", out)
    return _WS.sub(" ", out).strip()
