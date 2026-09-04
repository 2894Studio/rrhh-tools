"""Construccion de URLs de busqueda de LinkedIn.

Se mantiene aparte de los fetchers para poder verificar los parametros en un
test sin abrir ninguna conexion.
"""

from __future__ import annotations

from urllib.parse import urlencode

from ..config import Query, Settings

GUEST_SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
GUEST_DETAIL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting"
SESSION_SEARCH = "https://www.linkedin.com/jobs/search/"

# f_WT: 1=presencial, 2=remoto, 3=hibrido
_WORKPLACE = {"remote": "2", "hybrid": "3", "onsite": "1"}


def _common_params(query: Query, settings: Settings, start: int) -> dict[str, str]:
    params = {
        "keywords": query.keywords,
        "geoId": settings.geo_id(query.geo),
        "start": str(start),
    }
    search = settings.raw["search"]
    if search.get("date_posted"):
        params["f_TPR"] = search["date_posted"]
    if search.get("experience_levels"):
        params["f_E"] = ",".join(search["experience_levels"])
    if query.workplace and query.workplace in _WORKPLACE:
        params["f_WT"] = _WORKPLACE[query.workplace]
    return params


def guest_search_url(query: Query, settings: Settings, start: int = 0) -> str:
    return f"{GUEST_SEARCH}?{urlencode(_common_params(query, settings, start))}"


def guest_detail_url(job_id: str) -> str:
    return f"{GUEST_DETAIL}/{job_id}"


def session_search_url(query: Query, settings: Settings, start: int = 0) -> str:
    return f"{SESSION_SEARCH}?{urlencode(_common_params(query, settings, start))}"


def rotacion(queries: list, max_pages: int):
    """Cede (pagina, busqueda) rotando POR PAGINAS, no por busqueda.

    IMPORTA MAS DE LO QUE PARECE. `max_jobs` es un tope global, asi que
    recorriendo las busquedas en orden la primera se comia el presupuesto
    entero y las demas no llegaban a lanzarse: con 14 busquedas y un tope de
    40, solo corria "product designer / Madrid" y el informe salia sesgado a
    eso sin que nada lo dijera.

    Rotando por paginas, todas las busquedas aportan su primera pagina antes de
    que ninguna pase a la segunda. Si el tope corta, corta parejo.

    Quien lo consume lleva su propio conjunto de busquedas agotadas y se las
    salta; mantenerlo fuera evita el protocolo de send() del generador.
    """
    for pagina in range(max_pages):
        for query in queries:
            yield pagina, query
