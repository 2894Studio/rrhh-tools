"""Agrupacion de ofertas en empresas y reparto en los cuatro bloques.

El entregable son EMPRESAS, no ofertas: lo que 2894 va a hacer es llamar a una
empresa, no a una vacante. Por eso el informe se ordena por empresa y las
vacantes cuelgan debajo.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from ..config import Settings
from ..models import Block, Company, JobPosting
from .classifier import CompanyClassifier
from .scoring import score_company


def group_into_companies(
    jobs: list[JobPosting],
    classifier: CompanyClassifier,
    settings: Settings,
    today: date | None = None,
    orden: str = "reciente",
) -> dict[Block, list[Company]]:
    """Agrupa por empresa y ordena cada bloque.

    `orden="reciente"` (por defecto) pone primero a quien acaba de publicar:
    para actuar sobre una vacante lo primero es que siga abierta. `"prioridad"`
    recupera el orden por puntuacion. El orden se decide AQUI, en el servidor,
    para que quien abra el informe sin JavaScript vea el orden anunciado.
    """
    by_key: dict[str, list[JobPosting]] = defaultdict(list)
    for job in jobs:
        by_key[job.company_key].append(job)

    blocks: dict[Block, list[Company]] = {b: [] for b in Block}

    for key, company_jobs in by_key.items():
        display = _most_common_spelling(company_jobs)
        aliases = sorted({j.company_name_raw for j in company_jobs if j.company_name_raw != display})
        industries = sorted({i for j in company_jobs for i in j.li_industries})
        slug = _company_slug(company_jobs)

        # Se clasifica con TODAS las descripciones juntas: los heuristicos de
        # texto son mucho mas fiables sobre el conjunto que sobre una sola oferta.
        combined = "\n".join(j.description_text or "" for j in company_jobs)
        classification = classifier.classify(
            display, combined or None, slug, industries
        )

        score, components, why = score_company(classification, company_jobs, settings, today)
        best_id = _best_job_id(company_jobs, components)

        company = Company(
            key=key,
            display_name=display,
            aliases=aliases,
            linkedin_url=company_jobs[0].company_linkedin_url,
            logo_url=next((j.company_logo_url for j in company_jobs if j.company_logo_url), None),
            li_industries=industries,
            classification=classification,
            jobs=sorted(company_jobs, key=lambda j: (j.posted_at or date.min), reverse=True),
            score=score,
            components=components,
            why=why,
            best_job_id=best_id,
        )
        blocks[classification.block].append(company)

    for block in blocks:
        # Desempate determinista en los dos ordenes: sin esto, dos ejecuciones
        # iguales podrian ordenar distinto y el informe pareceria cambiar sin
        # motivo.
        if orden == "prioridad":
            blocks[block].sort(key=lambda c: (-c.score, c.key))
        else:
            blocks[block].sort(
                key=lambda c: (-_fecha_orden(c), -c.score, c.key))
    return blocks


def _fecha_orden(company: Company) -> float:
    """Fecha de la oferta mas reciente de la empresa, como numero ordenable."""
    fechas = [j.posted_at for j in company.jobs if j.posted_at]
    return max(fechas).toordinal() if fechas else 0


def _most_common_spelling(jobs: list[JobPosting]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for job in jobs:
        if job.company_name_raw:
            counts[job.company_name_raw] += 1
    return max(counts, key=lambda k: (counts[k], k)) if counts else "(sin nombre)"


def _company_slug(jobs: list[JobPosting]) -> str | None:
    for job in jobs:
        url = job.company_linkedin_url or ""
        if "/company/" in url:
            return url.rstrip("/").split("/company/")[-1].split("?")[0]
    return None


def _best_job_id(jobs: list[JobPosting], components) -> str | None:
    if not jobs:
        return None
    if len(jobs) == 1:
        return jobs[0].job_id
    return max(jobs, key=lambda j: (j.posted_at or date.min)).job_id
