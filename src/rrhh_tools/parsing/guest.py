"""Parsers del LinkedIn publico (sin login).

Los selectores estan escritos a partir de la estructura conocida del endpoint
`jobs-guest`, pero NO se han podido verificar contra LinkedIn real desde el
entorno de desarrollo (sin salida a red). Por eso:

  - cada campo se busca con varios selectores alternativos,
  - un selector que falla anota un aviso en `parse_warnings`, no rompe,
  - `rrhh-tools search --record` guarda el HTML recibido para poder ajustar
    los selectores en un ciclo si LinkedIn ha cambiado el marcado.

Ese ciclo de ajuste es trabajo previsto, no un fallo del sistema.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup

_JOB_ID_URL = re.compile(r"/jobs/view/(?:[^/]*-)?(\d{6,})")
_JOB_ID_URN = re.compile(r"jobPosting:(\d+)")
_COMPANY_SLUG = re.compile(r"/company/([^/?#]+)")


_WS = re.compile(r"\s+")


def _text(node: Any) -> str:
    """Texto plano con los espacios colapsados.

    get_text(strip=True) solo recorta los extremos de cada nodo: el sangrado y
    los saltos de linea DENTRO de un mismo bloque de texto sobreviven, y luego
    frases como "primera persona de diseno" no casan con ningun patron.
    """
    return _WS.sub(" ", node.get_text(" ", strip=True)).strip() if node else ""


def _first(soup: Any, selectors: list[str]) -> Any:
    for selector in selectors:
        found = soup.select_one(selector)
        if found:
            return found
    return None


def canonical_job_url(job_id: str) -> str:
    return f"https://www.linkedin.com/jobs/view/{job_id}/"


def strip_query(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def parse_search_cards(html: str) -> list[dict[str, Any]]:
    """Fragmento de resultados -> lista de dicts crudos (sin modelos todavia)."""
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("li div.base-card, div.base-card, li div.job-search-card")
    if not cards:
        # El fragmento a veces llega como <li> sueltos. El filtro es
        # deliberadamente estricto: sin el, este parser "reconoce" tambien el
        # DOM del LinkedIn con sesion y devuelve basura (titulos duplicados,
        # empresa vacia) en vez de no devolver nada, que es peor porque
        # aparenta funcionar.
        cards = [
            li for li in soup.select("li")
            if li.select_one("a[href*='/jobs/view/']")
            and not li.select_one("[data-job-id], [data-occludable-job-id]")
            and (li.select_one("[class*='base-card'], [class*='base-search-card'], "
                               "[class*='job-search-card']")
                 or li.get("data-entity-urn"))
        ]

    results: list[dict[str, Any]] = []
    for card in cards:
        warnings: list[str] = []

        link = _first(card, ["a.base-card__full-link", "a.base-search-card__title-link",
                             "a[href*='/jobs/view/']"])
        href = link.get("href", "") if link else ""

        job_id = ""
        urn = card.get("data-entity-urn") or card.get("data-job-id") or ""
        if urn:
            match = _JOB_ID_URN.search(str(urn))
            job_id = match.group(1) if match else str(urn)
        if not job_id and href:
            match = _JOB_ID_URL.search(href)
            if match:
                job_id = match.group(1)
        if not job_id:
            continue  # sin id no hay nada que deduplicar; se ignora la tarjeta

        title_node = _first(card, ["h3.base-search-card__title", "h3", ".base-search-card__title"])
        title = _text(title_node)
        if not title and link:
            title = _text(link)
        if not title:
            warnings.append("titulo no encontrado")

        company_node = _first(card, ["h4.base-search-card__subtitle a",
                                     "h4.base-search-card__subtitle", "h4 a", "h4"])
        company = _text(company_node)
        if not company:
            warnings.append("empresa no encontrada")

        company_url = ""
        company_link = _first(card, ["h4.base-search-card__subtitle a", "a[href*='/company/']"])
        if company_link:
            company_url = strip_query(company_link.get("href", ""))

        location = _text(_first(card, ["span.job-search-card__location",
                                       ".base-search-card__metadata span", ".job-search-card__location"]))

        # LinkedIn sirve el logo en la propia tarjeta: es la fuente mas fiable.
        logo = None
        img = _first(card, ["img.artdeco-entity-image", "img.search-entity-media__image",
                            ".search-entity-media img", "img"])
        if img:
            logo = (img.get("data-delayed-url") or img.get("data-ghost-url")
                    or img.get("src") or None)
            if logo and not logo.startswith("http"):
                logo = None

        time_node = _first(card, ["time.job-search-card__listdate",
                                  "time.job-search-card__listdate--new", "time"])
        posted_text = _text(time_node)
        posted_iso = time_node.get("datetime", "") if time_node else ""

        results.append({
            "job_id": job_id,
            "url": canonical_job_url(job_id),
            "title": title,
            "company": company,
            "company_url": company_url or None,
            "location": location,
            "posted_text": posted_text or None,
            "posted_iso": posted_iso or None,
            "company_logo_url": logo,
            "parse_warnings": warnings,
        })
    return results


def parse_job_detail(html: str) -> dict[str, Any]:
    """Pagina de detalle -> descripcion y criterios de la oferta."""
    soup = BeautifulSoup(html, "lxml")
    warnings: list[str] = []

    description_node = _first(soup, ["div.description__text", "div.show-more-less-html__markup",
                                     "section.description", "div.description"])
    description = _text(description_node)
    if not description:
        warnings.append("descripcion no encontrada")

    criteria: dict[str, str] = {}
    for item in soup.select("li.description__job-criteria-item, .description__job-criteria-item"):
        key = _text(_first(item, ["h3.description__job-criteria-subheader", "h3"]))
        value = _text(_first(item, ["span.description__job-criteria-text", "span"]))
        if key:
            criteria[key.strip().lower()] = value

    seniority = None
    industries: list[str] = []
    for key, value in criteria.items():
        if "antigüedad" in key or "antiguedad" in key or "seniority" in key or "experiencia" in key:
            seniority = value
        if "sector" in key or "industr" in key:
            industries = [part.strip() for part in re.split(r"[,;]| y ", value) if part.strip()]

    company_slug = None
    company_link = _first(soup, ["a.topcard__org-name-link", "a[href*='/company/']"])
    if company_link:
        match = _COMPANY_SLUG.search(company_link.get("href", ""))
        if match:
            company_slug = match.group(1)

    return {
        "description": description or None,
        "li_seniority_field": seniority,
        "li_industries": industries,
        "company_slug": company_slug,
        "criteria": criteria,
        "parse_warnings": warnings,
    }
