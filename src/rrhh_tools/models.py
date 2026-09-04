"""Modelos de datos del pipeline.

El invariante que sostiene todo el sistema esta al final de este modulo, en
`ProcessedRun.reconcile()`: toda oferta que entra sale por exactamente una via.
Nada se descarta en silencio, nunca.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Block(StrEnum):
    """Bloques del informe. Las agencias no se tiran: se leen distinto."""

    TARGET = "A"      # clientes finales: a quien llamamos
    COMPETITION = "B"  # agencias y estudios: termometro de demanda
    INTERMEDIARY = "C"  # consultoras y seleccion: ocultan al cliente real
    REVIEW = "D"      # decision humana pendiente


class CompanyLabel(StrEnum):
    END_CLIENT = "END_CLIENT"
    AGENCY = "AGENCY"
    CONSULTANCY = "CONSULTANCY"
    STAFFING = "STAFFING"
    UNKNOWN = "UNKNOWN"


class SeniorityLabel(StrEnum):
    JUNIOR = "JUNIOR"
    JUNIOR_BY_DESC = "JUNIOR_BY_DESC"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_JUNIOR = "NOT_JUNIOR"
    NOT_DESIGN = "NOT_DESIGN"


class LocationBucket(StrEnum):
    MADRID = "MADRID"
    REMOTE_ES = "REMOTE_ES"
    REST_ES = "REST_ES"
    OUTSIDE_ES = "OUTSIDE_ES"
    UNKNOWN = "UNKNOWN"


class SeniorityVerdict(BaseModel):
    label: SeniorityLabel
    confidence: float
    positive_hits: list[str] = Field(default_factory=list)
    negative_hits: list[str] = Field(default_factory=list)
    role_hits: list[str] = Field(default_factory=list)
    explanation: str = ""

    @property
    def survives(self) -> bool:
        """Solo NOT_DESIGN y NOT_JUNIOR abandonan el pipeline."""
        return self.label not in (SeniorityLabel.NOT_DESIGN, SeniorityLabel.NOT_JUNIOR)


class Classification(BaseModel):
    label: CompanyLabel
    confidence: float
    block: Block
    reasons: list[str] = Field(default_factory=list)
    rule_source: str = "default"

    @property
    def category_label(self) -> str:
        return {
            CompanyLabel.END_CLIENT: "Cliente final",
            CompanyLabel.AGENCY: "Agencia / estudio digital",
            CompanyLabel.CONSULTANCY: "Consultora IT / ESN",
            CompanyLabel.STAFFING: "Selección / ETT",
            CompanyLabel.UNKNOWN: "Sin clasificar",
        }[self.label]


class JobPosting(BaseModel):
    job_id: str
    source: str = "guest"
    url: str = ""
    fetched_at: datetime | None = None

    title_raw: str = ""
    title_norm: str = ""
    company_name_raw: str = ""
    company_key: str = ""
    company_linkedin_url: str | None = None
    company_logo_url: str | None = None

    location_raw: str = ""
    location_bucket: LocationBucket = LocationBucket.UNKNOWN
    workplace_type: str | None = None

    posted_text: str | None = None
    posted_at: date | None = None
    posted_confidence: float = 0.5

    description_text: str | None = None
    li_seniority_field: str | None = None
    li_industries: list[str] = Field(default_factory=list)

    seniority: SeniorityVerdict | None = None
    dedupe_key: str = ""
    merged_ids: list[str] = Field(default_factory=list)
    n_sightings: int = 1
    parse_warnings: list[str] = Field(default_factory=list)

    @property
    def haystack(self) -> str:
        """Titulo + descripcion, para los heuristicos que miran ambos."""
        return f"{self.title_raw}\n{self.description_text or ''}"


class ScoreComponent(BaseModel):
    name: str
    label: str
    weight: float
    value: float
    explanation: str

    @property
    def points(self) -> float:
        return round(self.weight * self.value, 2)


class Company(BaseModel):
    key: str
    display_name: str
    aliases: list[str] = Field(default_factory=list)
    linkedin_url: str | None = None
    logo_url: str | None = None
    li_industries: list[str] = Field(default_factory=list)
    classification: Classification
    jobs: list[JobPosting] = Field(default_factory=list)
    score: float = 0.0
    components: list[ScoreComponent] = Field(default_factory=list)
    why: str = ""
    best_job_id: str | None = None

    @property
    def n_jobs(self) -> int:
        return len(self.jobs)

    @property
    def monograma(self) -> str:
        """Iniciales para cuando no hay logo. Nunca inventamos una imagen."""
        palabras = [p for p in self.display_name.split() if p[:1].isalnum()]
        if not palabras:
            return "?"
        if len(palabras) == 1:
            return palabras[0][:2].upper()
        return (palabras[0][:1] + palabras[1][:1]).upper()

    @property
    def best_job(self) -> JobPosting | None:
        for job in self.jobs:
            if job.job_id == self.best_job_id:
                return job
        return self.jobs[0] if self.jobs else None


class FilteredJob(BaseModel):
    """Oferta que sale del pipeline. Se conserva para poder auditar por que."""

    job_id: str
    title_raw: str
    company_name_raw: str
    reason: str
    detail: str = ""


class RunDiagnostics(BaseModel):
    queries_run: list[str] = Field(default_factory=list)
    pages_fetched: int = 0
    jobs_seen: int = 0
    duplicates_merged: int = 0
    errors: list[str] = Field(default_factory=list)
    alias_suspicions: list[str] = Field(default_factory=list)
    stopped_early: bool = False
    stop_reason: str = ""


class ProcessedRun(BaseModel):
    run_id: str
    generated_at: datetime
    config_hash: str = ""
    targets: list[Company] = Field(default_factory=list)       # bloque A
    competition: list[Company] = Field(default_factory=list)   # bloque B
    intermediaries: list[Company] = Field(default_factory=list)  # bloque C
    review: list[Company] = Field(default_factory=list)        # bloque D
    filtered_jobs: list[FilteredJob] = Field(default_factory=list)
    diagnostics: RunDiagnostics = Field(default_factory=RunDiagnostics)

    @property
    def blocks(self) -> list[tuple[Block, str, str, list[Company]]]:
        """Los cuatro bloques con su titulo y su lectura, en orden de informe."""
        return [
            (Block.TARGET, "Cuentas objetivo",
             "Clientes finales. A quién podéis llamar para colocar los perfiles.",
             self.targets),
            (Block.COMPETITION, "Señal de competencia",
             "Agencias y estudios. Que contraten junior significa que hay demanda "
             "y que están ganando proyectos.",
             self.competition),
            (Block.INTERMEDIARY, "Intermediarios",
             "Consultoras y empresas de selección. Ocultan al cliente final, "
             "aunque a veces la oferta lo deja entrever.",
             self.intermediaries),
            (Block.REVIEW, "Por revisar",
             "Clasificación ambigua o nivel dudoso. Aquí están las oportunidades "
             "que ni la heurística ni nosotros conocemos todavía.",
             self.review),
        ]

    def count_jobs(self) -> dict[str, int]:
        return {
            "A": sum(c.n_jobs for c in self.targets),
            "B": sum(c.n_jobs for c in self.competition),
            "C": sum(c.n_jobs for c in self.intermediaries),
            "D": sum(c.n_jobs for c in self.review),
            "filtered": len(self.filtered_jobs),
            "merged": self.diagnostics.duplicates_merged,
        }

    def reconcile(self) -> tuple[bool, str]:
        """Toda oferta vista sale por exactamente una via.

        Es el chequeo que garantiza que el sistema nunca descarta nada en
        silencio. Se ejecuta en cada run y hay un test dedicado.
        """
        counts = self.count_jobs()
        accounted = (counts["A"] + counts["B"] + counts["C"] + counts["D"]
                     + counts["filtered"] + counts["merged"])
        seen = self.diagnostics.jobs_seen
        ok = accounted == seen
        msg = (f"vistas={seen} contabilizadas={accounted} "
               f"(A={counts['A']} B={counts['B']} C={counts['C']} D={counts['D']} "
               f"filtradas={counts['filtered']} fusionadas={counts['merged']})")
        return ok, msg
