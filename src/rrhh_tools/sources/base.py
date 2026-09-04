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
