"""Pipeline completo contra fixtures. Ni un socket."""

from datetime import date

import pytest

from rrhh_tools.config import Query
from rrhh_tools.http import FixtureFetcher
from rrhh_tools.models import RunDiagnostics
from rrhh_tools.pipeline.run import process
from rrhh_tools.sources import guest

HOY = date(2026, 9, 4)


@pytest.fixture(scope="module")
def run(settings, fixtures_dir):
    f = FixtureFetcher(fixtures_dir)
    queries, _ = settings.resolvable_queries()
    registros, etiquetas = guest.collect(f, queries, settings, 250)
    diag = RunDiagnostics(queries_run=etiquetas, pages_fetched=f.pages_fetched)
    return process(registros, settings, "test", diag, today=HOY)


def test_el_invariante_de_reconciliacion_se_cumple(run):
    """Toda oferta vista sale por exactamente una vía. Nada se pierde."""
    ok, mensaje = run.reconcile()
    assert ok, mensaje
    assert not run.diagnostics.errors


def test_reparto_en_los_cuatro_bloques(run):
    nombres = lambda cs: {c.display_name for c in cs}
    assert "Bankinter" in nombres(run.targets)
    assert "Cobee" in nombres(run.targets)
    assert "The Cocktail" in nombres(run.competition)
    assert "Talento Digital Selección" in nombres(run.intermediaries)


def test_las_agencias_no_se_tiran_sino_que_se_separan(run):
    """La competencia contratando junior es señal de mercado, no basura."""
    assert run.competition, "el bloque de competencia no debería estar vacío"
    for c in run.competition:
        assert c.jobs, "una agencia sin vacantes no aporta señal"
        assert c.score > 0


def test_los_senior_ya_no_se_descartan(run):
    """Cambio de criterio: antes salían del pipeline, ahora se etiquetan.

    El objetivo pasó a ser la foto completa del mercado, con el nivel como
    filtro en el informe.
    """
    todas = [j for c in (run.targets + run.competition + run.intermediaries + run.review)
             for j in c.jobs]
    senior = next(j for j in todas if j.title_raw == "Senior Product Designer")
    assert senior.seniority.label.value == "SENIOR"


def test_solo_el_no_diseno_queda_fuera_y_sigue_visible(run):
    motivos = {f.title_raw: f.reason for f in run.filtered_jobs}
    assert motivos == {"Diseñador Industrial Junior": "NOT_DESIGN"}
    for f in run.filtered_jobs:
        assert f.detail, "todo descarte debe explicar por qué"


def test_por_defecto_ordena_por_la_oferta_mas_reciente(run):
    """Cambio de criterio: para actuar sobre una vacante, lo primero es que
    siga abierta. La prioridad sigue disponible, pero ya no decide qué se ve
    primero."""
    fechas = [c.jobs[0].posted_at for c in run.targets]
    assert fechas == sorted(fechas, reverse=True), [
        (c.display_name, c.jobs[0].posted_at) for c in run.targets]


def test_el_orden_por_prioridad_sigue_disponible(settings, fixtures_dir):
    from rrhh_tools.http import FixtureFetcher
    f = FixtureFetcher(fixtures_dir)
    queries, _ = settings.resolvable_queries()
    registros, _ = guest.collect(f, queries, settings, 250)
    run = process(registros, settings, "t", today=HOY, orden="prioridad")
    puntuaciones = [c.score for c in run.targets]
    assert puntuaciones == sorted(puntuaciones, reverse=True)
    assert run.targets[0].display_name == "Bankinter"


def test_toda_empresa_lleva_desglose_y_explicacion(run):
    for bloque in (run.targets, run.competition, run.intermediaries, run.review):
        for c in bloque:
            assert c.components and c.why
            total = round(sum(x.points for x in c.components), 1)
            assert abs(total - c.score) < 0.05


def test_el_resultado_es_determinista(settings, fixtures_dir):
    def ejecutar():
        f = FixtureFetcher(fixtures_dir)
        queries, _ = settings.resolvable_queries()
        registros, _ = guest.collect(f, queries, settings, 250)
        r = process(registros, settings, "test", today=HOY)
        return [(c.key, c.score) for c in r.targets]
    assert ejecutar() == ejecutar()


def test_el_tope_de_ofertas_se_respeta(settings, fixtures_dir):
    """El volumen bajo es parte de la disciplina de peticiones."""
    f = FixtureFetcher(fixtures_dir)
    queries, _ = settings.resolvable_queries()
    registros, _ = guest.collect(f, queries, settings, max_jobs=3)
    assert len(registros) <= 3


def test_el_tope_se_reparte_entre_todas_las_busquedas(settings, fixtures_dir):
    """El tope es GLOBAL, y antes se gastaba en orden.

    Con 14 búsquedas y un tope de 40, la primera se comía el presupuesto entero
    y las otras 13 no llegaban a lanzarse nunca: el informe salía sesgado a
    "product designer / Madrid" sin que nada lo dijera. Ahora se rota por
    páginas, así que todas aportan antes de que ninguna pase a la segunda.
    """
    from rrhh_tools.http import FixtureFetcher
    from rrhh_tools.sources import guest

    lanzables, _ = settings.resolvable_queries()
    assert len(lanzables) > 1, "hacen falta varias búsquedas para que esto tenga sentido"

    # Tope pequeño a propósito: es donde se notaba el sesgo.
    _, labels = guest.collect(FixtureFetcher(fixtures_dir), lanzables, settings, 12)
    assert len(labels) > 1, "el tope se agotó en la primera búsqueda"


def test_la_rotacion_va_por_paginas_no_por_busqueda():
    from rrhh_tools.sources.base import rotacion

    pares = list(rotacion(["a", "b", "c"], 2))
    assert pares == [(0, "a"), (0, "b"), (0, "c"), (1, "a"), (1, "b"), (1, "c")]
    # La clave: ninguna búsqueda llega a su página 1 antes de que todas hayan
    # hecho su página 0.
    assert [p for p, _ in pares] == sorted(p for p, _ in pares)
