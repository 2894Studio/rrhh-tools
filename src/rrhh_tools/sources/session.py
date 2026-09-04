"""Fuente: LinkedIn con sesion iniciada, via Playwright.

Es la opcion elegida por el equipo. Da mas datos que el endpoint publico, pero
conviene tenerlo presente: automatizar LinkedIn con una cuenta puede provocar
que LinkedIn la restrinja. Por eso el volumen es bajo, el ritmo fijo, y ante
cualquier senal de muro de login se aborta en vez de insistir.

No hay evasion de deteccion de ningun tipo: un solo contexto de navegador,
cabeceras normales y esperas fijas.
"""

from __future__ import annotations

import os
import time
from typing import Any

from ..config import Query, Settings
from ..http import AuthWall
from ..parsing.guest import parse_job_detail, parse_search_cards
from .base import session_search_url

PAGE_SIZE = 25
COOKIE_ENV = "LINKEDIN_LI_AT"


def _cookie() -> str:
    value = os.environ.get(COOKIE_ENV, "").strip()
    if not value:
        raise AuthWall(
            f"Falta la variable de entorno {COOKIE_ENV}.\n"
            "Copia .env.example a .env y pega ahi tu cookie li_at de LinkedIn, o usa "
            "--source guest para no necesitar sesion."
        )
    return value


def collect(
    queries: list[Query],
    settings: Settings,
    max_jobs: int,
    seen: set[str] | None = None,
    record_dir=None,
) -> tuple[list[dict[str, Any]], list[str]]:
    from playwright.sync_api import sync_playwright

    seen = seen if seen is not None else set()
    records: list[dict[str, Any]] = []
    labels: list[str] = []
    delay = settings.run["min_delay_seconds"]

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(locale="es-ES")
        context.add_cookies([{
            "name": "li_at", "value": _cookie(),
            "domain": ".linkedin.com", "path": "/",
            "httpOnly": True, "secure": True,
        }])
        page = context.new_page()
        try:
            for query in queries:
                labels.append(f"{query.keywords} / {query.geo}"
                              + (f" / {query.workplace}" if query.workplace else ""))
                for page_index in range(settings.run["max_pages_per_query"]):
                    if len(records) >= max_jobs:
                        return records, labels
                    url = session_search_url(query, settings, page_index * PAGE_SIZE)
                    page.goto(url, wait_until="domcontentloaded",
                              timeout=settings.run["request_timeout_seconds"] * 1000)
                    time.sleep(delay)
                    if any(marker in page.url for marker in
                           ("/authwall", "/uas/login", "/checkpoint/")):
                        raise AuthWall(
                            "LinkedIn ha redirigido al muro de login. Tu cookie li_at ha "
                            "caducado o la sesión está restringida.\n"
                            "Copia una cookie nueva a .env, o cambia a --source guest."
                        )
                    # Carga diferida: el listado solo pinta al hacer scroll.
                    for _ in range(3):
                        page.mouse.wheel(0, 2200)
                        time.sleep(1.0)
                    html = page.content()
                    if record_dir:
                        from ..http import url_key
                        record_dir.mkdir(parents=True, exist_ok=True)
                        (record_dir / f"{url_key(url)}.html").write_text(html, encoding="utf-8")
                    cards = parse_search_cards(html)
                    if not cards:
                        break
                    for card in cards:
                        if card["job_id"] in seen or len(records) >= max_jobs:
                            continue
                        seen.add(card["job_id"])
                        card["source"] = "session"
                        records.append(card)
        finally:
            context.close()
            browser.close()
    return records, labels
