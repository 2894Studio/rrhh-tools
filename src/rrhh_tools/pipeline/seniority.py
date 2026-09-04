"""Clasificador de nivel.

CAMBIO DE CRITERIO IMPORTANTE
-----------------------------
Esto era una puerta: lo que no fuera junior salía del pipeline. Ahora es una
ETIQUETA. Lo único que se descarta es lo que no es diseño digital; un senior se
marca como senior y el informe deja filtrarlo.

El orden de comprobación sigue importando, pero por otro motivo. Antes "la
negativa gana a la positiva" evitaba que "Senior Product Designer" se colara
como junior. Ahora evita que se etiquete mal: lead gana a senior, y ambos ganan
a junior cuando el título mezcla los dos.
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

    # --- ¿Es diseño digital? Lo único que sigue siendo una puerta. ---
    role_hits = _hits(patterns.role_positive, title)
    if not role_hits:
        return SeniorityVerdict(
            label=SeniorityLabel.NOT_DESIGN,
            confidence=1.0,
            explanation="El título no menciona ningún rol de diseño.",
        )
    role_excluded = _hits(patterns.role_exclude, title)
    if role_excluded:
        return SeniorityVerdict(
            label=SeniorityLabel.NOT_DESIGN,
            confidence=1.0,
            role_hits=role_hits,
            explanation=f"Diseño, pero no del que buscamos: {', '.join(role_excluded)}.",
        )

    lead = _hits(patterns.sen_lead, title)
    senior = _hits(patterns.sen_senior, title)
    # Los números romanos van sobre el título con su caja original.
    senior += _hits(patterns.sen_senior_cased, title_raw)
    junior = _hits(patterns.sen_positive, title)
    weak = _hits(patterns.sen_weak_positive, title)

    # --- Lead gana a todo: "Senior Design Lead" es lead. ---
    if lead:
        return SeniorityVerdict(
            label=SeniorityLabel.LEAD, confidence=0.95,
            negative_hits=lead, positive_hits=junior, role_hits=role_hits,
            explanation=f"Puesto de responsabilidad: {', '.join(lead)}.",
        )

    if senior and junior:
        # "Junior/Senior UX Designer": la oferta cubre dos niveles. Se queda en
        # el nivel más alto para no prometer lo que no es, y se dice claramente.
        return SeniorityVerdict(
            label=SeniorityLabel.SENIOR, confidence=0.5,
            negative_hits=senior, positive_hits=junior, role_hits=role_hits,
            explanation=(
                f"El título mezcla niveles: {', '.join(junior)} junto a "
                f"{', '.join(senior)}. Se cuenta como senior por prudencia."
            ),
        )
    if senior:
        return SeniorityVerdict(
            label=SeniorityLabel.SENIOR, confidence=0.95,
            negative_hits=senior, role_hits=role_hits,
            explanation=f"Título de nivel senior: {', '.join(senior)}.",
        )
    if junior:
        return SeniorityVerdict(
            label=SeniorityLabel.JUNIOR, confidence=0.95,
            positive_hits=junior, role_hits=role_hits,
            explanation=f"Título junior explícito: {', '.join(junior)}.",
        )

    # --- El título calla: lo aclara el cuerpo, si puede. ---
    body = normalize_text(description)
    desc_senior = _hits(patterns.desc_sen_negative, body)
    if desc_senior:
        return SeniorityVerdict(
            label=SeniorityLabel.SENIOR, confidence=0.8,
            negative_hits=desc_senior, role_hits=role_hits,
            explanation=f"La oferta pide experiencia de nivel senior: {desc_senior[0]}.",
        )

    desc_junior = _hits(patterns.desc_sen_positive, body)
    li_field = normalize_text(li_seniority_field)
    li_junior = any(marker in li_field for marker in
                    ("entry level", "nivel inicial", "internship", "practicas", "becario"))
    if desc_junior or li_junior:
        evidence = desc_junior or [li_seniority_field or "campo de LinkedIn"]
        return SeniorityVerdict(
            label=SeniorityLabel.JUNIOR_BY_DESC, confidence=0.6,
            positive_hits=[str(e) for e in evidence], role_hits=role_hits,
            explanation=("El título no indica nivel, pero el cuerpo sí: "
                         f"{', '.join(str(e) for e in evidence)}."),
        )

    desc_mid = _hits(patterns.desc_sen_mid, body)
    if desc_mid:
        return SeniorityVerdict(
            label=SeniorityLabel.MID, confidence=0.7,
            role_hits=role_hits,
            explanation=f"La oferta pide experiencia intermedia: {desc_mid[0]}.",
        )
    if weak:
        return SeniorityVerdict(
            label=SeniorityLabel.MID, confidence=0.5,
            positive_hits=weak, role_hits=role_hits,
            explanation=f"Señal débil de nivel: {', '.join(weak)}.",
        )

    # Un título de diseño sin marca de nivel es, en la práctica, un mid.
    # Llamarlo "ambiguo" no aportaba nada y llenaba de dudas una lista entera.
    return SeniorityVerdict(
        label=SeniorityLabel.MID, confidence=0.4,
        role_hits=role_hits,
        explanation="Sin marca de nivel en el título ni en el cuerpo: se cuenta como mid.",
    )
