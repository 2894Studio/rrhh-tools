"""Clasificador de rol de diseño.

El orden de comprobación es intencionado y es lo único delicado de este módulo:

    AI  →  UX/UI  →  producto  →  UX  →  UI  →  otro

**AI gana siempre.** Un "AI Product Designer" se etiqueta `AI`, no `PRODUCT`,
porque poder aislar de un vistazo el diseño con IA es la razón de existir de
este clasificador: es el diferencial de los perfiles de 2894. Para no perder
información, el rol que habría salido si no fuera IA se guarda como secundario
y la ficha muestra los dos.

UX/UI va antes que UX y que UI porque en España es el título más común y, si se
comprobara UX primero, todos los "UX/UI Designer" se etiquetarían como UX y la
categoría combinada quedaría siempre vacía.
"""

from __future__ import annotations

from ..config import CompiledPatterns
from ..models import Rol, RolVerdict
from ..normalize import normalize_title


def _hits(patterns, text: str) -> list[str]:
    return [m.group(0).strip() for p in patterns if (m := p.search(text))]


def _rol_base(title: str, patterns: CompiledPatterns) -> tuple[Rol, list[str]]:
    """Rol ignorando la IA. Es lo que se guarda como secundario."""
    for rol, pats in (
        (Rol.UXUI, patterns.rol_uxui),
        (Rol.PRODUCT, patterns.rol_product),
        (Rol.UX, patterns.rol_ux),
        (Rol.UI, patterns.rol_ui),
    ):
        hits = _hits(pats, title)
        if hits:
            return rol, hits
    return Rol.OTRO, []


def classify_rol(
    title_raw: str,
    description: str | None,
    patterns: CompiledPatterns,
) -> RolVerdict:
    title = normalize_title(title_raw)

    ai_hits = _hits(patterns.rol_ai, title)
    if ai_hits:
        base, _ = _rol_base(title, patterns)
        return RolVerdict(
            label=Rol.AI, secundario=base if base != Rol.OTRO else None,
            hits=ai_hits,
            explanation=f"El título habla de diseño con IA: {', '.join(ai_hits)}.",
        )

    rol, hits = _rol_base(title, patterns)
    if rol != Rol.OTRO:
        return RolVerdict(
            label=rol, hits=hits,
            explanation=f"Rol de {rol.etiqueta.lower()}: {', '.join(hits)}.",
        )

    return RolVerdict(
        label=Rol.OTRO,
        explanation="Oferta de diseño digital sin un rol más concreto en el título.",
    )
