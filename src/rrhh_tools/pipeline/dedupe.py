"""Deduplicacion de ofertas y resolucion de identidad de empresa.

LinkedIn republica la misma oferta con el titulo retocado, y la misma empresa
aparece escrita de varias formas. Sin esto, una empresa saldria varias veces en
el informe y el factor de "vacantes abiertas" contaria repeticiones como
demanda real.
"""

from __future__ import annotations

import hashlib
from difflib import SequenceMatcher

from ..models import JobPosting
from ..normalize import title_core

FUZZY_TITLE = 0.90


def dedupe_key(job: JobPosting) -> str:
    raw = f"{job.company_key}|{title_core(job.title_raw)}|{job.location_bucket.value}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _prefer(a: JobPosting, b: JobPosting) -> tuple[JobPosting, JobPosting]:
    """Devuelve (ganadora, perdedora).

    Gana la publicacion mas reciente; a igualdad, la que viene de sesion
    iniciada, porque trae la descripcion completa.
    """
    if a.posted_at and b.posted_at and a.posted_at != b.posted_at:
        return (a, b) if a.posted_at > b.posted_at else (b, a)
    if a.source == "session" and b.source != "session":
        return a, b
    if b.source == "session" and a.source != "session":
        return b, a
    return (a, b) if len(a.description_text or "") >= len(b.description_text or "") else (b, a)


def _merge(winner: JobPosting, loser: JobPosting) -> JobPosting:
    winner.merged_ids = sorted(set(winner.merged_ids + [loser.job_id] + loser.merged_ids))
    winner.n_sightings += loser.n_sightings
    # La perdedora rellena huecos: puede traer campos que a la ganadora le faltan.
    if not winner.description_text and loser.description_text:
        winner.description_text = loser.description_text
    if not winner.li_industries and loser.li_industries:
        winner.li_industries = loser.li_industries
    if not winner.li_seniority_field and loser.li_seniority_field:
        winner.li_seniority_field = loser.li_seniority_field
    if not winner.company_linkedin_url and loser.company_linkedin_url:
        winner.company_linkedin_url = loser.company_linkedin_url
    return winner


def dedupe_jobs(jobs: list[JobPosting]) -> tuple[list[JobPosting], int]:
    """Tres pasadas: por id, por clave de repost, y fuzzy dentro de la empresa."""
    merged_count = 0

    # 1) mismo id de LinkedIn
    by_id: dict[str, JobPosting] = {}
    for job in jobs:
        existing = by_id.get(job.job_id)
        if existing is None:
            by_id[job.job_id] = job
        else:
            winner, loser = _prefer(existing, job)
            by_id[job.job_id] = _merge(winner, loser)
            merged_count += 1

    # 2) repost: misma empresa, mismo nucleo de titulo, misma zona
    by_key: dict[str, JobPosting] = {}
    for job in by_id.values():
        job.dedupe_key = dedupe_key(job)
        existing = by_key.get(job.dedupe_key)
        if existing is None:
            by_key[job.dedupe_key] = job
        else:
            winner, loser = _prefer(existing, job)
            by_key[job.dedupe_key] = _merge(winner, loser)
            merged_count += 1

    # 3) fuzzy de titulo DENTRO de la misma empresa (nunca entre empresas)
    survivors: list[JobPosting] = []
    for job in by_key.values():
        match = None
        for candidate in survivors:
            if candidate.company_key != job.company_key:
                continue
            if candidate.location_bucket != job.location_bucket:
                continue
            ratio = SequenceMatcher(None, title_core(candidate.title_raw),
                                    title_core(job.title_raw)).ratio()
            if ratio >= FUZZY_TITLE:
                match = candidate
                break
        if match is None:
            survivors.append(job)
        else:
            winner, loser = _prefer(match, job)
            merged = _merge(winner, loser)
            survivors[survivors.index(match)] = merged
            merged_count += 1

    return survivors, merged_count


def find_alias_suspicions(jobs: list[JobPosting]) -> list[str]:
    """Empresas con el mismo nombre normalizado pero distinta clave.

    No se fusionan automaticamente: unir "Acme" con "Acme Espana" puede ser
    correcto o puede ser un error, y equivocarse aqui contamina el informe.
    Se reportan para que una persona decida.
    """
    from ..normalize import basic_norm
    by_name: dict[str, set[str]] = {}
    display: dict[str, str] = {}
    for job in jobs:
        name = basic_norm(job.company_name_raw)
        if not name:
            continue
        by_name.setdefault(name, set()).add(job.company_key)
        display[name] = job.company_name_raw
    return [
        f"'{display[name]}' aparece con {len(keys)} identidades distintas: {sorted(keys)}"
        for name, keys in by_name.items() if len(keys) > 1
    ]
