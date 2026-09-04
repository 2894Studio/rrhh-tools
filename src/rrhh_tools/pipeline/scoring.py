"""Modelo de priorizacion (0-100).

Cada factor devuelve un valor 0-1 y una explicacion en texto. La puntuacion es
la suma ponderada, y el informe muestra el desglose completo: si una empresa
esta arriba, se puede ver exactamente por que.

REGLA DE DISENO QUE NO SE DEBE ROMPER
------------------------------------
`first_designer_signal` y `multiple_open_design_roles` NO deben acoplarse.
Si el primero se infiriera del numero de vacantes, ambos serian proxy del
tamano de la empresa y el modelo contaria lo mismo dos veces, en sentidos
opuestos. Por eso "primer disenador" exige evidencia TEXTUAL explicita, y el
numero de vacantes se lee solo como "mas plazas para nuestros perfiles".
"""

from __future__ import annotations

from datetime import date

from ..config import Settings
from ..dates import days_since
from ..models import (
    Classification, CompanyLabel, JobPosting, LocationBucket,
    ScoreComponent, SeniorityLabel,
)
from ..normalize import normalize_text

_LOCATION_VALUES = {
    LocationBucket.MADRID: (1.0, "Madrid, donde está el equipo"),
    LocationBucket.REMOTE_ES: (0.85, "remoto desde España"),
    LocationBucket.REST_ES: (0.4, "resto de España"),
    LocationBucket.OUTSIDE_ES: (0.0, "fuera de España"),
    LocationBucket.UNKNOWN: (0.3, "ubicación sin determinar"),
}

# El encaje se mide contra los perfiles de 2894, que son junior. Un senior en
# la lista no es un error: es contexto de mercado, y puntua bajo en ESTE factor
# sin dejar de aparecer. Quien quiera la foto completa usa los filtros.
_SENIORITY_VALUES = {
    SeniorityLabel.JUNIOR: (1.0, "título junior explícito"),
    SeniorityLabel.JUNIOR_BY_DESC: (0.6, "nivel junior deducido del cuerpo de la oferta"),
    SeniorityLabel.MID: (0.3, "nivel intermedio"),
    SeniorityLabel.SENIOR: (0.05, "nivel senior: no encaja con los perfiles"),
    SeniorityLabel.LEAD: (0.0, "puesto de responsabilidad: no encaja con los perfiles"),
}


def _end_client_value(classification: Classification) -> tuple[float, str]:
    if classification.label != CompanyLabel.END_CLIENT:
        return 0.0, f"no es cliente final ({classification.category_label.lower()})"
    if classification.confidence >= 0.9:
        return 1.0, "cliente final con alta confianza"
    if classification.confidence >= 0.7:
        return 0.85, "cliente final probable"
    return 0.4, "posible cliente final, sin confirmar"


def _count_matches(patterns, text: str) -> list[str]:
    return [m.group(0) for p in patterns if (m := p.search(text))]


def _ai_value(settings: Settings, text: str) -> tuple[float, str]:
    hits = _count_matches(settings.patterns.ai, text)
    unique = sorted(set(h.strip() for h in hits))
    if len(unique) >= 3:
        return 1.0, f"la oferta habla de IA en varios sitios ({', '.join(unique[:3])})"
    if unique:
        return 0.6, f"la oferta menciona IA ({', '.join(unique)})"
    # 0.2 de base: que no mencione IA no descalifica a la empresa como objetivo.
    return 0.2, "sin mención de IA"


def _plural_days(days: int) -> str:
    return "1 día" if days == 1 else f"{days} días"


def _recency_value(job: JobPosting, today: date) -> tuple[float, str]:
    days = days_since(job.posted_at, today)
    if days is None:
        return 0.5, "sin fecha de publicación"
    if days <= 3:
        base, label = 1.0, f"publicada hace {_plural_days(days)}"
    elif days <= 7:
        base, label = 0.9, f"publicada hace {_plural_days(days)}"
    elif days <= 14:
        base, label = 0.7, f"publicada hace {_plural_days(days)}"
    elif days <= 30:
        base, label = 0.4, f"publicada hace {_plural_days(days)}"
    else:
        base, label = 0.15, f"publicada hace {_plural_days(days)}, puede estar cerrada"
    # Se mezcla hacia el valor neutro segun la confianza de la fecha: "hace 2
    # semanas" es un rango, no un instante, y no debe pesar como uno.
    confidence = job.posted_confidence
    value = base * confidence + 0.5 * (1 - confidence)
    if confidence < 1.0:
        label += " (fecha aproximada)"
    return value, label


def _first_designer_value(settings: Settings, text: str) -> tuple[float, str]:
    strong = _count_matches(settings.patterns.first_designer_strong, text)
    if strong:
        return 1.0, "la oferta dice que será su primera persona de diseño"
    mature = _count_matches(settings.patterns.first_designer_mature, text)
    if mature:
        return 0.2, "ya tiene una organización de diseño montada"
    return 0.5, "sin señales sobre la madurez de su equipo de diseño"


def _volume_value(n_design_jobs: int, n_junior: int) -> tuple[float, str]:
    """Cuenta TODAS las vacantes de diseño, de cualquier nivel.

    Antes solo contaba las junior, asi que una empresa con un senior y dos mid
    figuraba con "1 vacante abierta". El factor decia medir cuanta demanda de
    diseño tiene la empresa y no lo hacia; ahora si.
    """
    detalle = f"{n_design_jobs} vacantes de diseño abiertas"
    if n_junior and n_junior != n_design_jobs:
        detalle += f", {n_junior} de ellas junior"
    if n_design_jobs >= 3:
        return 1.0, detalle
    if n_design_jobs == 2:
        return 0.7, detalle
    return 0.3, "1 vacante de diseño abierta"


def score_company(
    classification: Classification,
    jobs: list[JobPosting],
    settings: Settings,
    today: date | None = None,
) -> tuple[float, list[ScoreComponent], str]:
    """Puntua una empresa a partir de sus ofertas vivas.

    Los factores de empresa se calculan una vez; los de oferta toman el maximo
    entre sus vacantes, porque lo que se vende es el mejor encaje disponible.
    """
    today = today or date.today()
    weights = settings.weights
    corpus = normalize_text("\n".join(job.haystack for job in jobs))

    # --- factores de empresa ---
    ec_value, ec_why = _end_client_value(classification)
    fd_value, fd_why = _first_designer_value(settings, corpus)
    n_junior = sum(1 for j in jobs if j.seniority and j.seniority.label.es_junior)
    vol_value, vol_why = _volume_value(len(jobs), n_junior)

    # --- factores de oferta: maximo entre las vacantes ---
    best_sen, best_loc, best_ai, best_rec = (0.0, ""), (0.0, ""), (0.0, ""), (0.0, "")
    best_job_id, best_job_total = None, -1.0
    for job in jobs:
        label = job.seniority.label if job.seniority else SeniorityLabel.MID
        sen = _SENIORITY_VALUES.get(label, (0.3, "nivel intermedio"))
        loc = _LOCATION_VALUES[job.location_bucket]
        ai = _ai_value(settings, normalize_text(job.haystack))
        rec = _recency_value(job, today)
        best_sen = max(best_sen, sen, key=lambda x: x[0])
        best_loc = max(best_loc, loc, key=lambda x: x[0])
        best_ai = max(best_ai, ai, key=lambda x: x[0])
        best_rec = max(best_rec, rec, key=lambda x: x[0])
        total = (sen[0] * weights["seniority_match"] + loc[0] * weights["location_fit"]
                 + ai[0] * weights["ai_relevance"] + rec[0] * weights["recency"])
        if total > best_job_total:
            best_job_total, best_job_id = total, job.job_id

    components = [
        ScoreComponent(name="end_client_confidence", label="Es cliente final",
                       weight=weights["end_client_confidence"], value=ec_value, explanation=ec_why),
        ScoreComponent(name="seniority_match", label="Encaje de nivel",
                       weight=weights["seniority_match"], value=best_sen[0], explanation=best_sen[1]),
        ScoreComponent(name="location_fit", label="Encaje de ubicación",
                       weight=weights["location_fit"], value=best_loc[0], explanation=best_loc[1]),
        ScoreComponent(name="ai_relevance", label="Relevancia de IA",
                       weight=weights["ai_relevance"], value=best_ai[0], explanation=best_ai[1]),
        ScoreComponent(name="recency", label="Frescura",
                       weight=weights["recency"], value=best_rec[0], explanation=best_rec[1]),
        ScoreComponent(name="first_designer_signal", label="Equipo de diseño por construir",
                       weight=weights["first_designer_signal"], value=fd_value, explanation=fd_why),
        ScoreComponent(name="multiple_open_design_roles", label="Vacantes abiertas",
                       weight=weights["multiple_open_design_roles"], value=vol_value, explanation=vol_why),
    ]
    score = round(sum(c.points for c in components), 1)
    return score, components, _build_why(score, components)


def _upper_first(text: str) -> str:
    """Mayuscula inicial conservando el resto.

    str.capitalize() pone en minuscula todo lo demas, y convertia
    "remoto desde España" en "Remoto desde españa".
    """
    return text[:1].upper() + text[1:] if text else text


def _build_why(score: float, components: list[ScoreComponent]) -> str:
    """Frase legible: los dos factores que mas suman y el que mas lastra."""
    ranked = sorted(components, key=lambda c: c.points, reverse=True)
    top = [c for c in ranked if c.value >= 0.6][:2]
    # El lastre se mide por puntos perdidos frente al maximo del factor.
    drag = max(components, key=lambda c: c.weight * (1 - c.value))
    parts = []
    if top:
        parts.append(" · ".join(_upper_first(c.explanation) for c in top) + ".")
    else:
        parts.append("Sin factores fuertes a favor.")
    if drag.value < 0.5:
        parts.append(f"Lastre: {drag.explanation}.")
    return " ".join(parts)
