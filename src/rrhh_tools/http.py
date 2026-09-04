"""Capa de red. Es el UNICO modulo del proyecto que abre sockets.

Todo lo demas recibe strings, y por eso el 90% del sistema se puede probar sin
conectividad. `FixtureFetcher` es intercambiable con `ThrottledFetcher`, asi
que hasta el camino de red se ejercita offline contra respuestas guardadas.

Disciplina de peticiones, sin evasion de deteccion: un solo cliente, cabeceras
normales, ritmo fijo, volumen bajo, y parada limpia ante cualquier senal de
limite. No hay rotacion de proxies, ni resolucion de captchas, ni falsificacion
de huella de navegador; esas tecnicas quedan deliberadamente fuera.
"""

from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import requests

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


class ThrottleStop(RuntimeError):
    """LinkedIn nos esta limitando. Se para la ejecucion, no se insiste."""


class AuthWall(RuntimeError):
    """La cookie de sesion ya no vale. Reintentar no la va a resucitar."""


def url_key(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()


class Fetcher(Protocol):
    def get(self, url: str) -> str: ...


@dataclass
class ThrottledFetcher:
    """Cliente HTTP con ritmo fijo y parada limpia."""

    min_delay: float = 4.0
    jitter: float = 0.5
    timeout: int = 30
    max_retries: int = 3
    record_dir: Path | None = None

    def __post_init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        })
        self._last_request = 0.0
        self.pages_fetched = 0

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_request
        # El jitter solo evita ir en lockstep exacto; no es una tecnica de evasion.
        delay = self.min_delay + random.uniform(0, self.jitter)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request = time.monotonic()

    def get(self, url: str) -> str:
        backoff = self.min_delay
        for attempt in range(1, self.max_retries + 1):
            self._wait()
            response = self.session.get(url, timeout=self.timeout,
                                        allow_redirects=True)
            self.pages_fetched += 1

            if response.status_code in (429, 999):
                if attempt == self.max_retries:
                    raise ThrottleStop(
                        f"LinkedIn devuelve {response.status_code} tras {attempt} intentos. "
                        "Se para la ejecucion y se guarda el checkpoint; "
                        "reanuda mas tarde con --resume."
                    )
                time.sleep(backoff)
                backoff *= 2
                continue

            if response.status_code == 403 or _is_authwall(response.url, response.text):
                raise AuthWall(
                    "LinkedIn ha devuelto el muro de login. Tu cookie li_at ha caducado "
                    "o la sesion esta restringida.\n"
                    "Copia una cookie nueva a .env, o cambia a --source guest."
                )

            response.raise_for_status()
            if self.record_dir:
                self.record_dir.mkdir(parents=True, exist_ok=True)
                (self.record_dir / f"{url_key(url)}.html").write_text(
                    response.text, encoding="utf-8")
            return response.text
        raise ThrottleStop("Reintentos agotados.")


def _is_authwall(url: str, body: str) -> bool:
    markers = ("/authwall", "/uas/login", "/checkpoint/")
    if any(m in url for m in markers):
        return True
    head = body[:4000].lower()
    return "authwall" in head or "sign in to continue" in head


@dataclass
class FixtureFetcher:
    """Reproduce respuestas guardadas. Intercambiable con ThrottledFetcher.

    Es lo que permite ejercitar el pipeline entero de punta a punta sin red.
    """

    fixture_dir: Path
    pages_fetched: int = 0

    def get(self, url: str) -> str:
        path = self.fixture_dir / f"{url_key(url)}.html"
        if not path.is_file():
            raise FileNotFoundError(
                f"No hay fixture para {url}\nEsperaba: {path}\n"
                "Genera fixtures con: rrhh-tools search --record"
            )
        self.pages_fetched += 1
        return path.read_text(encoding="utf-8")
