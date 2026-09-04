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


def test_los_senior_y_los_no_disenadores_quedan_fuera_pero_visibles(run):
    motivos = {f.title_raw: f.reason for f in run.filtered_jobs}
    assert motivos["Senior Product Designer"] == "NOT_JUNIOR"
    assert motivos["Diseñador Industrial Junior"] == "NOT_DESIGN"
    for f in run.filtered_jobs:
        assert f.detail, "todo descarte debe explicar por qué"


def test_el_orden_prioriza_clientes_finales_con_encaje(run):
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
