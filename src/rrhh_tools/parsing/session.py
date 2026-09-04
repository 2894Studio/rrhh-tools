"""Parsers del LinkedIn CON SESION INICIADA.

El DOM del listado con login no se parece al del endpoint publico: usa
`job-card-container` con `data-job-id` en vez de `base-card` con
`data-entity-urn`, y los textos cuelgan de clases `artdeco-entity-lockup__*`.
Reutilizar los selectores del modo publico aqui devuelve cero ofertas.

Igual que en el otro parser, los selectores estan escritos a partir de la
estructura conocida pero NO se han podido verificar contra LinkedIn real desde
el entorno de desarrollo. Por eso cada campo se busca con varias alternativas,
se cae hacia los selectores publicos como ultimo recurso, y lo que falla se
anota en `parse_warnings` en vez de romper la ejecucion.

Con `--record` se guarda el HTML recibido para ajustar los selectores en un
ciclo. Ese ajuste es trabajo previsto.
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from .guest import canonical_job_url, parse_search_cards, strip_query

_JOB_ID = re.compile(r"/jobs/view/(?:[^/]*-)?(\d{6,})")
_COMPANY_SLUG = re.compile(r"/company/([^/?#]+)")

# Contenedores de tarjeta en el listado con sesion, de mas a menos especifico.
_CARD_SELECTORS = [
    "div.job-card-container[data-job-id]",
    "li[data-occludable-job-id] div.job-card-container",
    "li.scaffold-layout__list-item",
    "li.jobs-search-results__list-item",
    "div[data-job-id]",
]

_TITLE_SELECTORS = [
    "a.job-card-container__link span[aria-hidden='true']",
    "a.job-card-list__title--link span[aria-hidden='true']",
    "a.job-card-list__title",
    ".artdeco-entity-lockup__title",
    "a.job-card-container__link",
]

_COMPANY_SELECTORS = [
    ".artdeco-entity-lockup__subtitle",
    ".job-card-container__primary-description",
    ".job-card-container__company-name",
]

_LOCATION_SELECTORS = [
    ".artdeco-entity-lockup__caption",
    "ul.job-card-container__metadata-wrapper li",
    ".job-card-container__metadata-item",
]

_DESCRIPTION_SELECTORS = [
    "div.jobs-description__content",
    "div.jobs-box__html-content",
    "div#job-details",
    "article.jobs-description__container",
    "div.jobs-description-content__text",
]


_WS = re.compile(r"\s+")


def _text(node: Any) -> str:
    """Texto plano con los espacios colapsados. Ver el mismo helper en guest.py."""
    return _WS.sub(" ", node.get_text(" ", strip=True)).strip() if node else ""


def _first(scope: Any, selectors: list[str]) -> Any:
    for selector in selectors:
        found = scope.select_one(selector)
        if found:
            return found
    return None


def parse_session_cards(html: str) -> list[dict[str, Any]]:
    """Listado con sesion -> dicts crudos.

    Si no reconoce ninguna tarjeta con los selectores de sesion, lo intenta con
    los del modo publico: LinkedIn a veces devuelve marcado publico incluso con
    la cookie puesta.
    """
    soup = BeautifulSoup(html, "lxml")

    cards: list[Any] = []
    for selector in _CARD_SELECTORS:
        cards = soup.select(selector)
        if cards:
            break
    if not cards:
        publico = parse_search_cards(html)
        for card in publico:
            card.setdefault("parse_warnings", []).append(
                "listado reconocido con los selectores del LinkedIn publico"
            )
        return publico

    resultados: list[dict[str, Any]] = []
    for card in cards:
        warnings: list[str] = []

        job_id = str(card.get("data-job-id")
                     or card.get("data-occludable-job-id") or "").strip()
        link = _first(card, ["a.job-card-container__link", "a.job-card-list__title--link",
                             "a[href*='/jobs/view/']"])
        href = link.get("href", "") if link else ""
        if not job_id and href:
            match = _JOB_ID.search(href)
            if match:
                job_id = match.group(1)
        if not job_id or not job_id.isdigit():
            continue  # sin id no hay nada que deduplicar

        titulo = _text(_first(card, _TITLE_SELECTORS))
        if not titulo and link:
            titulo = _text(link)
        if not titulo:
            warnings.append("titulo no encontrado en la tarjeta con sesion")

        empresa = _text(_first(card, _COMPANY_SELECTORS))
        if not empresa:
            warnings.append("empresa no encontrada en la tarjeta con sesion")

        company_url = None
        enlace_empresa = card.select_one("a[href*='/company/']")
        if enlace_empresa:
            company_url = strip_query(enlace_empresa.get("href", "")).rstrip("/")
            if company_url.startswith("/"):
                company_url = f"https://www.linkedin.com{company_url}"

        ubicacion = _text(_first(card, _LOCATION_SELECTORS))

        nodo_fecha = card.select_one("time")
        posted_text = _text(nodo_fecha)
        posted_iso = nodo_fecha.get("datetime", "") if nodo_fecha else ""

        resultados.append({
            "job_id": job_id,
            "url": canonical_job_url(job_id),
            "title": titulo,
            "company": empresa,
            "company_url": company_url,
            "location": ubicacion,
            "posted_text": posted_text or None,
            "posted_iso": posted_iso or None,
            "parse_warnings": warnings,
        })
    return resultados


def parse_session_detail(html: str) -> dict[str, Any]:
    """Pagina /jobs/view/<id> con sesion -> descripcion y datos de la oferta.

    La descripcion es lo que mas le importa al clasificador: de ahi salen las
    frases de intermediario, las menciones de IA y la senal de "primer
    disenador". Sin ella el modo sesion clasifica mucho peor que el publico.
    """
    soup = BeautifulSoup(html, "lxml")
    warnings: list[str] = []

    descripcion = _text(_first(soup, _DESCRIPTION_SELECTORS))
    if not descripcion:
        warnings.append("descripcion no encontrada en la pagina con sesion")

    # Las "insights" de la cabecera llevan jornada, nivel y a veces sector.
    insights = [
        _text(nodo) for nodo in soup.select(
            ".job-details-jobs-unified-top-card__job-insight, "
            ".jobs-unified-top-card__job-insight, "
            ".job-details-preferences-and-skills__pill"
        )
    ]
    texto_insights = " · ".join(i for i in insights if i)

    nivel = None
    for marcador in ("Prácticas", "Practicas", "Sin experiencia", "Nivel inicial",
                     "Internship", "Entry level", "Intermedio", "Mid-Senior"):
        if marcador.lower() in texto_insights.lower():
            nivel = marcador
            break

    sectores: list[str] = []
    match_sector = re.search(r"(?:Sectores?|Industries)\s*[:·]?\s*([^·]+)", texto_insights)
    if match_sector:
        sectores = [p.strip() for p in re.split(r"[,;]| y ", match_sector.group(1)) if p.strip()]

    company_slug = None
    enlace = _first(soup, ["a.job-details-jobs-unified-top-card__company-name",
                           ".job-details-jobs-unified-top-card__company-name a",
                           "a[href*='/company/']"])
    if enlace:
        match = _COMPANY_SLUG.search(enlace.get("href", ""))
        if match:
            company_slug = match.group(1)

    return {
        "description": descripcion or None,
        "li_seniority_field": nivel,
        "li_industries": sectores,
        "company_slug": company_slug,
        "insights": texto_insights or None,
        "parse_warnings": warnings,
    }
