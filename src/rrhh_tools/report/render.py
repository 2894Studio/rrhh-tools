"""Render del informe HTML.

Un unico fichero autocontenido salvo la fuente DM Sans, que se pide a Google
Fonts. La pila de respaldo esta puesta para que el informe siga siendo legible
sin conexion o si la fuente no carga.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..models import Company, ProcessedRun

TEMPLATE_DIR = Path(__file__).parent / "templates"


def _badges(company: Company) -> list[str]:
    """Etiquetas cortas de un vistazo. Fieles a lo que dicen los factores."""
    out: list[str] = []
    buckets = {job.location_bucket.value for job in company.jobs}
    if "MADRID" in buckets:
        out.append("Madrid")
    if "REMOTE_ES" in buckets:
        out.append("Remoto España")
    for component in company.components:
        if component.name == "first_designer_signal" and component.value >= 1.0:
            out.append("Su primer diseñador")
        if component.name == "ai_relevance" and component.value >= 0.6:
            out.append("Menciona IA")
    if company.n_jobs > 1:
        out.append(f"{company.n_jobs} vacantes")
    if company.classification.confidence < 0.7:
        out.append("Clasificación dudosa")
    return out


def render_report(run: ProcessedRun, title: str, source_label: str = "LinkedIn") -> str:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("report.html.j2")

    # Los badges son datos de presentacion, no del dominio: se calculan aqui y
    # viajan aparte, sin ensuciar el modelo Company.
    blocks = []
    for block_id, block_title, description, companies in run.blocks:
        blocks.append({
            "id": block_id.value,
            "title": block_title,
            "description": description,
            "rows": [{"c": company, "badges": _badges(company)} for company in companies],
        })

    _, reconcile_msg = run.reconcile()
    return template.render(
        title=title,
        generated=run.generated_at.strftime("%d/%m/%Y %H:%M"),
        run_id=run.run_id,
        config_hash=run.config_hash,
        source_label=source_label,
        counts=run.count_jobs(),
        blocks=blocks,
        filtered=run.filtered_jobs,
        diagnostics=run.diagnostics,
        reconcile_msg=reconcile_msg,
    )
