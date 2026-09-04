"""Orquestacion: de tarjetas crudas a ProcessedRun.

Esta funcion no toca la red. Recibe los dicts que ya produjo un fetcher (real o
de fixtures) y devuelve el resultado completo, con el invariante de
reconciliacion comprobado.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from ..config import Settings
from ..dates import parse_relative_date
from ..models import (
    Block, FilteredJob, JobPosting, ProcessedRun, RunDiagnostics,
)
from ..normalize import normalize_company_name, normalize_title
from .classifier import CompanyClassifier
from .dedupe import dedupe_jobs, find_alias_suspicions
from .location import classify_location
from .rol import classify_rol
from .seniority import classify_seniority


def build_job(raw: dict[str, Any], settings: Settings, today: date) -> JobPosting:
    name = raw.get("company") or ""
    normalized = normalize_company_name(name, settings.legal_suffixes)
    company_url = raw.get("company_url")
    slug = None
    if company_url and "/company/" in company_url:
        slug = company_url.rstrip("/").split("/company/")[-1].split("?")[0]

    posted_at, confidence = parse_relative_date(raw.get("posted_text"), today)
    if raw.get("posted_iso"):
        try:
            posted_at = date.fromisoformat(raw["posted_iso"])
            confidence = 1.0
        except ValueError:
            pass

    locations = settings.raw["locations"]
    return JobPosting(
        job_id=str(raw["job_id"]),
        source=raw.get("source", "guest"),
        url=raw.get("url", ""),
        fetched_at=datetime.now(),
        title_raw=raw.get("title") or "",
        title_norm=normalize_title(raw.get("title") or ""),
        company_name_raw=name,
        company_key=slug or normalized.norm or name.lower(),
        company_linkedin_url=company_url,
        company_logo_url=raw.get("company_logo_url"),
        location_raw=raw.get("location") or "",
        location_bucket=classify_location(
            raw.get("location") or "", raw.get("workplace_type"),
            locations["madrid_municipios"], locations["spain_markers"],
        ),
        workplace_type=raw.get("workplace_type"),
        posted_text=raw.get("posted_text"),
        posted_at=posted_at,
        posted_confidence=confidence,
        description_text=raw.get("description"),
        li_seniority_field=raw.get("li_seniority_field"),
        li_industries=raw.get("li_industries") or [],
        parse_warnings=raw.get("parse_warnings") or [],
    )


def process(
    raw_records: list[dict[str, Any]],
    settings: Settings,
    run_id: str,
    diagnostics: RunDiagnostics | None = None,
    today: date | None = None,
    orden: str = "reciente",
) -> ProcessedRun:
    from .aggregate import group_into_companies

    today = today or date.today()
    diagnostics = diagnostics or RunDiagnostics()
    diagnostics.jobs_seen = len(raw_records)

    jobs = [build_job(raw, settings, today) for raw in raw_records]

    surviving, merged = dedupe_jobs(jobs)
    diagnostics.duplicates_merged = merged
    diagnostics.alias_suspicions = find_alias_suspicions(surviving)

    # Nivel y rol. Ya solo NOT_DESIGN sale del pipeline: el resto se etiqueta
    # y se filtra en el informe, para tener la foto completa del mercado.
    kept: list[JobPosting] = []
    filtered: list[FilteredJob] = []
    for job in surviving:
        verdict = classify_seniority(
            job.title_raw, job.description_text, job.li_seniority_field, settings.patterns
        )
        job.seniority = verdict
        if verdict.survives:
            job.rol = classify_rol(job.title_raw, job.description_text, settings.patterns)
            kept.append(job)
        else:
            filtered.append(FilteredJob(
                job_id=job.job_id, title_raw=job.title_raw,
                company_name_raw=job.company_name_raw,
                reason=verdict.label.value, detail=verdict.explanation,
            ))

    classifier = CompanyClassifier(settings)
    blocks = group_into_companies(kept, classifier, settings, today, orden)

    run = ProcessedRun(
        run_id=run_id,
        generated_at=datetime.now(),
        config_hash=settings.config_hash,
        targets=blocks[Block.TARGET],
        competition=blocks[Block.COMPETITION],
        intermediaries=blocks[Block.INTERMEDIARY],
        review=blocks[Block.REVIEW],
        filtered_jobs=filtered,
        diagnostics=diagnostics,
    )

    ok, message = run.reconcile()
    if not ok:
        run.diagnostics.errors.append(f"RECONCILIACION FALLIDA: {message}")
    return run
