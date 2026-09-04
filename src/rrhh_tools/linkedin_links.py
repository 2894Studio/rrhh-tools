"""Enlaces a LinkedIn para verificar cada empresa en la fuente original.

Son URLS DE BUSQUEDA, no de ofertas concretas. La diferencia importa: una URL
de oferta que no hemos visto seria inventada, y podria llevar a una vacante que
no existe. Una busqueda siempre lleva al estado real de LinkedIn en el momento
en que se hace clic, aunque no devuelva nada.
"""

from __future__ import annotations

from urllib.parse import urlencode

JOBS = "https://www.linkedin.com/jobs/search/"
COMPANIES = "https://www.linkedin.com/search/results/companies/"

# Terminos de diseno que acotan la busqueda dentro de una empresa.
DESIGN_TERMS = "designer OR diseñador OR UX OR UI"


def job_search(company: str, geo_id: str | None = None, terms: str = DESIGN_TERMS) -> str:
    """Vacantes de diseno en una empresa concreta."""
    params = {"keywords": f"{company} {terms}"}
    if geo_id:
        params["geoId"] = geo_id
    return f"{JOBS}?{urlencode(params)}"


def company_search(company: str) -> str:
    """Pagina de la empresa en LinkedIn, via buscador."""
    return f"{COMPANIES}?{urlencode({'keywords': company})}"


def company_jobs(slug: str) -> str:
    """Vacantes publicadas por una empresa cuyo slug ya conocemos."""
    return f"https://www.linkedin.com/company/{slug}/jobs/"
