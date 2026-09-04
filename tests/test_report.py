from datetime import date

import pytest

from rrhh_tools.config import Query
from rrhh_tools.http import FixtureFetcher
from rrhh_tools.pipeline.run import process
from rrhh_tools.report.render import render_report
from rrhh_tools.sources import guest


@pytest.fixture(scope="module")
def html(settings, fixtures_dir):
    f = FixtureFetcher(fixtures_dir)
    queries, _ = settings.resolvable_queries()
    registros, _ = guest.collect(f, queries, settings, 250)
    run = process(registros, settings, "test", today=date(2026, 9, 4))
    return render_report(run, "2894 — Radar de diseño junior")


def test_estan_los_cuatro_bloques(html):
    for titulo in ["Cuentas objetivo", "Señal de competencia", "Intermediarios", "Por revisar"]:
        assert titulo in html, f"falta el bloque {titulo!r}"


def test_esta_el_panel_de_temperatura_de_mercado(html):
    assert "Temperatura del mercado" in html


def test_se_ve_lo_que_quedo_fuera(html):
    """Nada se descarta en silencio, y el informe debe demostrarlo."""
    assert "Qué quedó fuera" in html
    assert "Senior Product Designer" in html


def test_usa_la_paleta_de_marca(html):
    for token in ["#0A46FF", "#F7F8FA", "#0B0B0D", "#E6E8EC", "#7DB7FF"]:
        assert token in html


def test_no_hay_acentos_calidos(html):
    """La marca es deliberadamente fría: ni un naranja, rojo, ámbar o verde."""
    import re
    prohibidos = ["orange", "crimson", "gold", "tomato", "#f59", "#ff9", "#e74",
                  "#28a745", "#dc3545", "#ffc107", "green", "red;", "yellow"]
    minusculas = html.lower()
    for color in prohibidos:
        assert color not in minusculas, f"color cálido o de semáforo encontrado: {color}"


def test_usa_dm_sans_con_respaldo(html):
    assert "DM Sans" in html
    assert "Helvetica" in html, "debe haber pila de respaldo si la fuente no carga"


def test_no_hay_recursos_externos_salvo_la_fuente(html):
    import re
    urls = re.findall(r'(?:src|href)="(https?://[^"]+)"', html)
    externos = [u for u in urls if "fonts.googleapis.com" not in u and "fonts.gstatic.com" not in u]
    for url in externos:
        assert "linkedin.com" in url, f"recurso externo inesperado: {url}"


def test_cada_empresa_muestra_su_desglose(html):
    assert "Por qué puntúa así" in html
    assert "PUNTOS" in html.upper()


def test_el_informe_se_escapa_correctamente(settings, fixtures_dir):
    """Un nombre de empresa con HTML no debe romper ni inyectar la página."""
    f = FixtureFetcher(fixtures_dir)
    queries, _ = settings.resolvable_queries()
    registros, _ = guest.collect(f, queries, settings, 250)
    registros[0]["company"] = '<script>alert("x")</script>'
    run = process(registros, settings, "test", today=date(2026, 9, 4))
    salida = render_report(run, "t")
    assert "<script>alert" not in salida
    assert "&lt;script&gt;" in salida
