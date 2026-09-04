"""Render del informe HTML.

Un unico fichero autocontenido salvo la fuente DM Sans, que se pide a Google
Fonts. La pila de respaldo esta puesta para que el informe siga siendo legible
sin conexion o si la fuente no carga.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from ..linkedin_links import company_jobs, company_search, job_search
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


def _enlace_empresa(company: Company, geo_id: str | None) -> str:
    """Enlace para ver en LinkedIn todas las vacantes de esta empresa.

    Si conocemos su slug vamos directos a su pagina de empleo; si no,
    construimos una busqueda. Nunca inventamos una URL de oferta.
    """
    url = company.linkedin_url or ""
    if "/company/" in url:
        return company_jobs(url.rstrip("/").split("/company/")[-1].split("?")[0])
    return job_search(company.display_name, geo_id)


def render_report(run: ProcessedRun, title: str, source_label: str = "LinkedIn",
                  es_muestra: bool = False, geo_id: str | None = None) -> str:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        # autoescape=True explicito, NO select_autoescape(["html"]): esa funcion
        # mira la extension del fichero, que aqui es ".j2", asi que el escapado
        # no llegaba a activarse nunca y un nombre de empresa con HTML dentro se
        # inyectaba tal cual en el informe.
        autoescape=True,
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
            "rows": [{"c": company, "badges": _badges(company),
                      "linkedin": _enlace_empresa(company, geo_id)}
                     for company in companies],
        })

    _, reconcile_msg = run.reconcile()
    return template.render(
        title=title,
        generated=run.generated_at.strftime("%d/%m/%Y %H:%M"),
        run_id=run.run_id,
        config_hash=run.config_hash,
        source_label=source_label,
        # Un informe generado contra fixtures lleva empresas reales con ofertas
        # inventadas. Sin un aviso dentro de la propia pagina se lee como real.
        es_muestra=es_muestra,
        counts=run.count_jobs(),
        blocks=blocks,
        filtered=run.filtered_jobs,
        diagnostics=run.diagnostics,
        reconcile_msg=reconcile_msg,
    )


def _enlaces_curados(entrada: dict, geo_id: str | None, geo_es: str | None) -> list[dict]:
    """Un enlace de busqueda en LinkedIn por empresa de la ficha.

    Son busquedas, no ofertas: llevan al estado real de LinkedIn en el momento
    del clic. Una entrada puede agrupar varias empresas (la banca, por ejemplo),
    y entonces genera un enlace por cada una.
    """
    ubicacion = (entrada.get("ubicacion") or "").lower()
    geo = geo_id if "madrid" in ubicacion else (geo_es or geo_id)
    nombres = entrada.get("empresas") or [entrada.get("nombre", "")]
    busqueda = entrada.get("busqueda")
    if busqueda:
        return [{"texto": "Buscar esta oferta en LinkedIn",
                 "url": job_search(busqueda, geo, terms="")}]
    return [
        {"texto": f"Vacantes de {nombre} en LinkedIn" if len(nombres) > 1
                  else "Ver vacantes en LinkedIn",
         "url": job_search(nombre, geo)}
        for nombre in nombres if nombre
    ]


def render_curated(data: dict, title: str, geo_id: str | None = None,
                   geo_es: str | None = None) -> str:
    """Informe de la lista curada inicial.

    Usa la misma plantilla de estilos que el radar, para que ambos documentos se
    lean como el mismo sistema.
    """
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    empresas = data.get("empresas", [])
    for entrada in empresas:
        entrada["enlaces"] = _enlaces_curados(entrada, geo_id, geo_es)
    confirmadas = [e for e in empresas if e.get("evidencia") == "confirmada"]
    estrategicas = [e for e in empresas if e.get("evidencia") != "confirmada"]

    grupos = []
    if confirmadas:
        grupos.append({
            "tag": "Evidencia confirmada",
            "titulo": "Con vacante encontrada",
            "descripcion": "Hay evidencia pública de una vacante de diseño junior. "
                           "Cuando la fuente no publica el nombre de la empresa, se dice así.",
            "empresas": confirmadas,
        })
    if estrategicas:
        grupos.append({
            "tag": "Objetivo estratégico",
            "titulo": "Por perfil, a verificar",
            "descripcion": "Sin vacante confirmada. Son clientes finales con producto digital "
                           "propio y necesidad plausible: hipótesis razonadas, no hechos.",
            "empresas": estrategicas,
        })

    return env.get_template("curated.html.j2").render(
        title=title,
        contexto=data.get("contexto", {}),
        grupos=grupos,
        competencia=[
            {**c, "enlaces": [{"texto": "Ver en LinkedIn",
                               "url": company_search(c.get("nombre", ""))}]}
            for c in data.get("competencia_detectada", [])
        ],
        n_confirmadas=len(confirmadas),
        n_estrategicas=len(estrategicas),
    )


def render_index(generado: str, title: str) -> str:
    """Portada del sitio estático que agrupa los informes."""
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env.get_template("index.html.j2").render(title=title, generado=generado)
