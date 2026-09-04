"""Fuente: LinkedIn publico, sin login. Es el plan B si la sesion se restringe."""

from __future__ import annotations

from typing import Any

from ..config import Query, Settings
from ..http import Fetcher
from ..parsing.guest import parse_job_detail, parse_search_cards
from .base import guest_detail_url, guest_search_url

PAGE_SIZE = 10


def collect(
    fetcher: Fetcher,
    queries: list[Query],
    settings: Settings,
    max_jobs: int,
    seen: set[str] | None = None,
    fetch_details: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Descarga tarjetas y, opcionalmente, el detalle de cada oferta.

    Devuelve (registros, descripciones_de_busquedas). Respeta `max_jobs` como
    tope duro: el volumen bajo es parte de la disciplina de peticiones.
    """
    seen = seen if seen is not None else set()
    records: list[dict[str, Any]] = []
    labels: list[str] = []

    for query in queries:
        labels.append(f"{query.keywords} / {query.geo}"
                      + (f" / {query.workplace}" if query.workplace else ""))
        for page in range(settings.run["max_pages_per_query"]):
            if len(records) >= max_jobs:
                return records, labels
            html = fetcher.get(guest_search_url(query, settings, page * PAGE_SIZE))
            cards = parse_search_cards(html)
            if not cards:
                break  # pagina vacia: fin de la paginacion para esta query
            for card in cards:
                if card["job_id"] in seen or len(records) >= max_jobs:
                    continue
                seen.add(card["job_id"])
                card["source"] = "guest"
                if fetch_details:
                    try:
                        detail = parse_job_detail(fetcher.get(guest_detail_url(card["job_id"])))
                        card.update({k: v for k, v in detail.items()
                                     if k not in ("parse_warnings", "criteria")})
                        card["parse_warnings"] = (card.get("parse_warnings") or []) + \
                            detail.get("parse_warnings", [])
                    except FileNotFoundError:
                        card.setdefault("parse_warnings", []).append("sin detalle disponible")
                records.append(card)
    return records, labels
