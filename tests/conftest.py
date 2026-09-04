"""Configuración común de los tests.

El guardia de red es lo más importante de este fichero: cualquier intento de
abrir una conexión durante los tests falla de forma dura. Eso hace dos cosas a
la vez: permite que la suite pase en un entorno sin conectividad, y garantiza
que ningún test empiece a depender en silencio de que LinkedIn esté disponible.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rrhh_tools.config import load_settings  # noqa: E402


@pytest.fixture(autouse=True)
def no_network(monkeypatch, request):
    """Prohíbe la red en todos los tests salvo los marcados como 'live'."""
    if request.node.get_closest_marker("live"):
        return

    def blocked(*args, **kwargs):
        raise AssertionError(
            "Un test ha intentado salir a la red. La suite debe funcionar sin "
            "conectividad: usa FixtureFetcher y los ficheros de tests/fixtures/http."
        )

    import requests.adapters
    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", blocked)
    try:
        import playwright.sync_api
        monkeypatch.setattr(playwright.sync_api, "sync_playwright", blocked)
    except ImportError:
        pass


@pytest.fixture(scope="session")
def settings():
    return load_settings(ROOT / "config")


@pytest.fixture(scope="session")
def fixtures_dir():
    return ROOT / "tests" / "fixtures" / "http"
