"""Parser del LinkedIn con sesión iniciada.

Es el camino que el equipo eligió como principal, y su DOM no se parece al del
LinkedIn público: reutilizar aquellos selectores devuelve cero ofertas.
"""

from pathlib import Path

import pytest

from rrhh_tools.parsing.session import parse_session_cards, parse_session_detail

FIXTURES = Path(__file__).parent / "fixtures" / "session"


@pytest.fixture(scope="module")
def listado():
    return (FIXTURES / "search.html").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def detalle():
    return (FIXTURES / "detail.html").read_text(encoding="utf-8")


def test_reconoce_las_tarjetas_del_dom_con_sesion(listado):
    cards = parse_session_cards(listado)
    assert len(cards) == 2
    assert sum(len(c["parse_warnings"]) for c in cards) == 0


def test_extrae_los_campos_de_la_tarjeta(listado):
    primera = parse_session_cards(listado)[0]
    assert primera["job_id"] == "4002000001"
    assert primera["title"] == "Junior Product Designer"
    assert primera["company"] == "Payflow"
    assert "Madrid" in primera["location"]
    assert primera["posted_text"] == "hace 1 día"
    assert primera["posted_iso"] == "2026-09-03"
    assert primera["url"] == "https://www.linkedin.com/jobs/view/4002000001/"
    assert primera["company_url"] == "https://www.linkedin.com/company/payflow"


def test_los_selectores_publicos_no_valen_para_el_dom_con_sesion(listado):
    """Justifica que exista este parser aparte.

    Si algún día los selectores públicos empezaran a funcionar aquí, este test
    fallaría y habría que replantearse mantener dos parsers.
    """
    from rrhh_tools.parsing.guest import parse_search_cards
    assert parse_search_cards(listado) == []


def test_cae_a_los_selectores_publicos_si_no_reconoce_nada():
    """LinkedIn a veces sirve marcado público aun con la cookie puesta."""
    publico = (
        '<ul><li><div class="base-card" data-entity-urn="urn:li:jobPosting:999888777">'
        '<a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/999888777"></a>'
        '<h3 class="base-search-card__title">Junior UX Designer</h3>'
        '<h4 class="base-search-card__subtitle">Acme</h4>'
        '</div></li></ul>'
    )
    cards = parse_session_cards(publico)
    assert len(cards) == 1
    assert cards[0]["job_id"] == "999888777"
    assert any("publico" in w for w in cards[0]["parse_warnings"])


def test_el_detalle_trae_la_descripcion(detalle):
    """Sin descripción el clasificador pierde sus señales más fuertes."""
    d = parse_session_detail(detalle)
    assert d["description"]
    assert "primera persona de diseño" in d["description"]
    assert d["company_slug"] == "payflow"
    assert d["li_seniority_field"] == "Prácticas"
    assert "Financial Services" in d["li_industries"]


def test_el_detalle_avisa_en_vez_de_romperse():
    d = parse_session_detail("<html><body><p>marcado inesperado</p></body></html>")
    assert d["description"] is None
    assert d["parse_warnings"]


def test_una_tarjeta_sin_id_se_ignora():
    html = '<div class="job-card-container"><span>sin id</span></div>'
    assert parse_session_cards(html) == []


def test_el_pipeline_completo_funciona_con_datos_de_sesion(settings):
    """De tarjeta con sesión a empresa clasificada y puntuada."""
    from datetime import date
    from rrhh_tools.pipeline.run import process

    listado = (FIXTURES / "search.html").read_text(encoding="utf-8")
    detalle = (FIXTURES / "detail.html").read_text(encoding="utf-8")
    cards = parse_session_cards(listado)
    for card in cards:
        card["source"] = "session"
    cards[0].update({k: v for k, v in parse_session_detail(detalle).items()
                     if k != "parse_warnings" and v})

    run = process(cards, settings, "sesion", today=date(2026, 9, 4))
    ok, mensaje = run.reconcile()
    assert ok, mensaje
    # Payflow es cliente final; el "Diseñador/a UX Senior" debe quedar fuera.
    assert any(c.display_name == "Payflow" for c in run.targets)
    assert any(f.reason == "NOT_JUNIOR" for f in run.filtered_jobs)
    payflow = next(c for c in run.targets if c.display_name == "Payflow")
    señal = next(c for c in payflow.components if c.name == "first_designer_signal")
    assert señal.value == 1.0, "la descripción decía que sería su primera persona de diseño"
