"""Orden por frescura y filtros del informe.

Dos cosas se fijan aquí. La primera es un cambio de criterio: el informe se
ordenaba por prioridad y ahora lo hace por la oferta publicada más reciente,
porque para actuar sobre una vacante lo primero es que siga abierta.

La segunda es la mejora progresiva: los controles los inyecta el script, así
que sin JavaScript no debe haber botones muertos en el HTML servido.
"""

from datetime import date

import pytest

from rrhh_tools.http import FixtureFetcher
from rrhh_tools.pipeline.run import process
from rrhh_tools.report.render import FACETAS_RADAR, render_report
from rrhh_tools.sources import guest

HOY = date(2026, 9, 5)


def _run(settings, fixtures_dir, orden="reciente"):
    fetcher = FixtureFetcher(fixtures_dir)
    queries, _ = settings.resolvable_queries()
    registros, _ = guest.collect(fetcher, queries, settings, 250)
    return process(registros, settings, "t", today=HOY, orden=orden)


@pytest.fixture(scope="module")
def demo_dir():
    from pathlib import Path
    return Path(__file__).parent / "fixtures" / "demo"


def test_por_defecto_manda_la_mas_reciente(settings, demo_dir):
    run = _run(settings, demo_dir)
    for bloque in (run.targets, run.competition, run.intermediaries, run.review):
        fechas = [max(j.posted_at for j in c.jobs if j.posted_at) for c in bloque if c.jobs]
        assert fechas == sorted(fechas, reverse=True)


def test_el_orden_por_prioridad_sigue_disponible(settings, demo_dir):
    run = _run(settings, demo_dir, orden="prioridad")
    puntuaciones = [c.score for c in run.targets]
    assert puntuaciones == sorted(puntuaciones, reverse=True)


def test_los_dos_ordenes_son_deterministas(settings, demo_dir):
    for orden in ("reciente", "prioridad"):
        a = [c.key for c in _run(settings, demo_dir, orden).targets]
        b = [c.key for c in _run(settings, demo_dir, orden).targets]
        assert a == b


def test_cada_ficha_lleva_sus_datos_de_filtro(settings, demo_dir):
    html = render_report(_run(settings, demo_dir), "t")
    for atributo in ("data-ficha", "data-nivel", "data-rol", "data-ubicacion",
                     "data-dias", "data-ia", "data-score", "data-bloque"):
        assert atributo in html, atributo
    # Una empresa con vacantes de dos niveles los lleva los dos: aparece si
    # cualquiera casa con el filtro.
    assert 'data-nivel="mid senior"' in html


def test_sin_javascript_no_hay_botones_muertos(settings, demo_dir):
    """Los controles los construye el script; el HTML servido no los trae."""
    html = render_report(_run(settings, demo_dir), "t")
    assert 'class="chip"' not in html
    assert 'id="filtros"' in html          # el contenedor sí, vacío
    assert 'aria-live="polite"' in html    # y el recuento, para lectores de pantalla


def test_las_facetas_declaran_nivel_y_rol_como_multiseleccion():
    """Se querrá ver 'junior + mid' o 'IA + producto' a la vez."""
    por_clave = {f["clave"]: f for f in FACETAS_RADAR}
    assert por_clave["nivel"]["multi"] is True
    assert por_clave["rol"]["multi"] is True
    assert por_clave["ubicacion"]["multi"] is False
    assert por_clave["dias"]["tipo"] == "max"
    assert por_clave["nivel"]["atajo"]["valores"] == ["junior"]


def test_las_facetas_cubren_todos_los_valores_posibles():
    """Si se añade un nivel o un rol y no se añade su chip, queda invisible."""
    from rrhh_tools.models import Rol, SeniorityLabel
    por_clave = {f["clave"]: f for f in FACETAS_RADAR}

    niveles = {o["valor"] for o in por_clave["nivel"]["opciones"]}
    esperados = {n.clave_filtro for n in SeniorityLabel if n != SeniorityLabel.NOT_DESIGN}
    assert esperados <= niveles, esperados - niveles

    roles = {o["valor"] for o in por_clave["rol"]["opciones"]}
    assert {r.clave_filtro for r in Rol} <= roles


def test_el_json_de_facetas_no_puede_cerrar_el_script():
    from rrhh_tools.report.render import _facetas_json
    salida = _facetas_json([{"clave": "x", "etiqueta": "</script><script>alert(1)",
                             "multi": False, "opciones": []}])
    assert "</script>" not in salida
    assert "\\u003c" in salida
