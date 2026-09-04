"""Filtro de nivel: nos quedamos con junior, descartamos senior.

Tres puertas, y la regla que lo gobierna todo: LA NEGATIVA TIENE PRIORIDAD
SOBRE LA POSITIVA. "Senior Product Designer" contiene "Designer" y contiene
"Product", pero no es una oferta junior. Si el orden se invirtiera, el radar
se llenaria de puestos senior y el filtro no serviria de nada.
"""

from __future__ import annotations

from ..config import CompiledPatterns
from ..models import SeniorityLabel, SeniorityVerdict
from ..normalize import normalize_text, normalize_title


def _hits(patterns, text: str) -> list[str]:
    found = []
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            found.append(match.group(0).strip())
    return found


def classify_seniority(
    title_raw: str,
    description: str | None,
    li_seniority_field: str | None,
    patterns: CompiledPatterns,
) -> SeniorityVerdict:
    title = normalize_title(title_raw)

    # --- Puerta A: es una oferta de diseno digital? ---
    role_hits = _hits(patterns.role_positive, title)
    if not role_hits:
        return SeniorityVerdict(
            label=SeniorityLabel.NOT_DESIGN,
            confidence=1.0,
            explanation="El titulo no menciona ningun rol de diseno.",
        )
    role_excluded = _hits(patterns.role_exclude, title)
    if role_excluded:
        return SeniorityVerdict(
            label=SeniorityLabel.NOT_DESIGN,
            confidence=1.0,
            role_hits=role_hits,
            explanation=f"Diseno, pero no del que buscamos: {', '.join(role_excluded)}.",
        )

    # --- Puerta B: negativa (la critica) ---
    negative = _hits(patterns.sen_negative, title)
    # Los numeros romanos se buscan sobre el titulo con su caja original.
    negative += _hits(patterns.sen_negative_cased, title_raw)

    # --- Puerta C: positiva ---
    positive = _hits(patterns.sen_positive, title)
    weak = _hits(patterns.sen_weak_positive, title)

    if negative and positive:
        # "Junior/Senior UX Designer": la oferta cubre dos niveles. No la tiramos,
        # pero tampoco la damos por buena: que la mire una persona.
        return SeniorityVerdict(
            label=SeniorityLabel.AMBIGUOUS,
            confidence=0.5,
            positive_hits=positive,
            negative_hits=negative,
            role_hits=role_hits,
            explanation=(
                f"El titulo mezcla niveles: {', '.join(positive)} junto a "
                f"{', '.join(negative)}. Requiere revision humana."
            ),
        )
    if negative:
        return SeniorityVerdict(
            label=SeniorityLabel.NOT_JUNIOR,
            confidence=0.95,
            negative_hits=negative,
            role_hits=role_hits,
            explanation=f"Titulo de nivel superior: {', '.join(negative)}.",
        )
    if positive:
        return SeniorityVerdict(
            label=SeniorityLabel.JUNIOR,
            confidence=0.95,
            positive_hits=positive,
            role_hits=role_hits,
            explanation=f"Titulo junior explicito: {', '.join(positive)}.",
        )

    # --- El titulo calla: rescate por descripcion y por el campo de LinkedIn ---
    body = normalize_text(description)
    desc_negative = _hits(patterns.desc_sen_negative, body)
    if desc_negative:
        return SeniorityVerdict(
            label=SeniorityLabel.NOT_JUNIOR,
            confidence=0.8,
            negative_hits=desc_negative,
            role_hits=role_hits,
            explanation=f"La oferta pide experiencia de nivel superior: {desc_negative[0]}.",
        )

    desc_positive = _hits(patterns.desc_sen_positive, body)
    li_field = normalize_text(li_seniority_field)
    li_junior = any(marker in li_field for marker in
                    ("entry level", "nivel inicial", "internship", "practicas", "becario"))
    if desc_positive or li_junior:
        evidence = desc_positive or [li_seniority_field or "campo de LinkedIn"]
        return SeniorityVerdict(
            label=SeniorityLabel.JUNIOR_BY_DESC,
            confidence=0.6,
            positive_hits=evidence,
            role_hits=role_hits,
            explanation=(
                "El titulo no indica nivel, pero el cuerpo si: "
                f"{', '.join(str(e) for e in evidence)}."
            ),
        )

    if weak:
        return SeniorityVerdict(
            label=SeniorityLabel.AMBIGUOUS,
            confidence=0.35,
            positive_hits=weak,
            role_hits=role_hits,
            explanation=f"Solo una senal debil de nivel: {', '.join(weak)}.",
        )

    return SeniorityVerdict(
        label=SeniorityLabel.AMBIGUOUS,
        confidence=0.3,
        role_hits=role_hits,
        explanation="Oferta de diseno sin ninguna indicacion de nivel.",
    )
