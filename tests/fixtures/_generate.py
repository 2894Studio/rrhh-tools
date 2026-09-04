"""Genera los fixtures HTML del pipeline.

IMPORTANTE: estos fixtures son una reproduccion A MANO de la estructura
conocida del HTML de LinkedIn. No son capturas reales: el entorno donde se
construyo el proyecto no tiene salida a red y no pudo descargarlas.

Sirven para dos cosas legitimas:
  - fijar el contrato del parser y detectar regresiones,
  - ejercitar el pipeline entero de punta a punta sin conectividad.

NO sirven para garantizar que los selectores casan con el LinkedIn de hoy.
Para eso, en la maquina del usuario:  rrhh-tools search --record
y se sustituyen estos ficheros por las capturas reales.

Uso:  python tests/fixtures/_generate.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from rrhh_tools.config import Query, load_settings  # noqa: E402
from rrhh_tools.http import url_key  # noqa: E402
from rrhh_tools.sources.base import guest_detail_url, guest_search_url  # noqa: E402

HTTP_DIR = Path(__file__).parent / "http"

CARD = """
<li>
  <div class="base-card relative job-search-card" data-entity-urn="urn:li:jobPosting:{job_id}">
    <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/{slug}-{job_id}?refId=abc">
      <span class="sr-only">{title}</span>
    </a>
    <div class="base-search-card__info">
      <h3 class="base-search-card__title">{title}</h3>
      <h4 class="base-search-card__subtitle">
        <a class="hidden-nested-link" href="https://www.linkedin.com/company/{company_slug}?trk=x">{company}</a>
      </h4>
      <div class="base-search-card__metadata">
        <span class="job-search-card__location">{location}</span>
        <time class="job-search-card__listdate" datetime="{iso}">{posted}</time>
      </div>
    </div>
  </div>
</li>
"""

DETAIL = """<html><body>
<section class="top-card-layout">
  <a class="topcard__org-name-link" href="https://www.linkedin.com/company/{company_slug}?trk=y">{company}</a>
</section>
<div class="description__text description__text--rich">
  <section class="show-more-less-html">
    <div class="show-more-less-html__markup">{description}</div>
  </section>
</div>
<ul class="description__job-criteria-list">
  <li class="description__job-criteria-item">
    <h3 class="description__job-criteria-subheader">Nivel de antigüedad</h3>
    <span class="description__job-criteria-text">{seniority}</span>
  </li>
  <li class="description__job-criteria-item">
    <h3 class="description__job-criteria-subheader">Sectores</h3>
    <span class="description__job-criteria-text">{industries}</span>
  </li>
</ul>
</body></html>
"""

# (job_id, titulo, empresa, slug, ubicacion, fecha_iso, texto_fecha, nivel_li, sectores, descripcion)
JOBS = [
    ("4001000001", "Junior Product Designer", "Bankinter", "bankinter",
     "Madrid, Comunidad de Madrid, España", "2026-09-02", "hace 2 días",
     "Prácticas", "Banking",
     "Buscamos un Junior Product Designer para nuestro producto digital. "
     "Trabajaras con nuestros usuarios reales definiendo el roadmap de producto. "
     "Valoramos conocimientos de inteligencia artificial y de diseno con IA, "
     "prompt engineering y herramientas como Figma AI. 0-2 anos de experiencia."),

    ("4001000002", "Diseñador/a UX/UI Junior", "Cobee", "cobee",
     "Madrid, Comunidad de Madrid, España", "2026-08-30", "hace 5 días",
     "Sin experiencia", "Financial Services",
     "Seras el primer disenador de la empresa y ayudaras a crear el equipo de diseno "
     "desde cero. Nuestra plataforma de beneficios para empleados crece rapido. "
     "Buscamos a alguien con ganas de aprender. Menos de 2 anos de experiencia."),

    ("4001000003", "Becario Diseño UX", "The Cocktail", "the-cocktail",
     "Madrid, Comunidad de Madrid, España", "2026-09-01", "hace 3 días",
     "Prácticas", "Design Services",
     "Buscamos becario de diseno UX para trabajar en proyectos de cliente. "
     "Trabajaras con nuestros clientes de diferentes sectores en una agencia "
     "lider del mercado espanol."),

    ("4001000004", "Senior Product Designer", "Cabify", "cabify",
     "Madrid, Comunidad de Madrid, España", "2026-08-28", "hace 1 semana",
     "Intermedio", "Software Development",
     "Buscamos un Senior Product Designer con minimo 5 anos de experiencia "
     "para liderar nuestro design system team."),

    ("4001000005", "Junior UX Designer", "Talento Digital Selección", "talento-digital",
     "España (En remoto)", "2026-08-27", "hace 1 semana",
     "Sin experiencia", "Staffing and Recruiting",
     "Para uno de nuestros clientes, importante empresa del sector retail, "
     "seleccionamos un Junior UX Designer. Proceso de seleccion confidencial."),

    ("4001000006", "Diseñador Industrial Junior", "Acciona", "acciona",
     "Madrid, Comunidad de Madrid, España", "2026-08-31", "hace 4 días",
     "Sin experiencia", "Utilities",
     "Diseno industrial de componentes mecanicos. Se requiere manejo de CAD."),

    ("4001000007", "Junior UI Designer", "Genially", "genially",
     "España (En remoto)", "2026-09-03", "hace 1 día",
     "Prácticas", "Software Development",
     "Buscamos Junior UI Designer para nuestro producto. Trabajamos con IA "
     "generativa y machine learning aplicado al diseno. Nuestros usuarios "
     "crean contenido interactivo. Sin experiencia previa necesaria."),

    ("4001000008", "UX/UI Designer", "Nova Retail Group", "nova-retail",
     "Madrid, Comunidad de Madrid, España", "2026-08-29", "hace 6 días",
     "Sin experiencia", "Retail",
     "Incorporamos un perfil de diseno a nuestro equipo. Seras la primera "
     "persona de diseno de la compania. 1-2 anos de experiencia."),
]


def build() -> None:
    settings = load_settings(ROOT / "config")
    HTTP_DIR.mkdir(parents=True, exist_ok=True)
    query = Query(id="fixture", keywords="junior UX designer", geo="spain", workplace="remote")

    cards = "".join(
        CARD.format(job_id=j[0], title=j[1], company=j[2], company_slug=j[3],
                    location=j[4], iso=j[5], posted=j[6],
                    slug=j[1].lower().replace(" ", "-").replace("/", "-"))
        for j in JOBS
    )
    page0 = guest_search_url(query, settings, 0)
    (HTTP_DIR / f"{url_key(page0)}.html").write_text(f"<ul>{cards}</ul>", encoding="utf-8")

    # Pagina siguiente vacia: es lo que termina la paginacion.
    page1 = guest_search_url(query, settings, 10)
    (HTTP_DIR / f"{url_key(page1)}.html").write_text("<ul></ul>", encoding="utf-8")

    for job in JOBS:
        url = guest_detail_url(job[0])
        html = DETAIL.format(company=job[2], company_slug=job[3], description=job[9],
                             seniority=job[7], industries=job[8])
        (HTTP_DIR / f"{url_key(url)}.html").write_text(html, encoding="utf-8")

    print(f"Generados {len(JOBS) + 2} fixtures en {HTTP_DIR}")
    print(f"  busqueda pagina 0: {page0}")


if __name__ == "__main__":
    build()
