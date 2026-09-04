from rrhh_tools.config import Query
from rrhh_tools.http import FixtureFetcher
from rrhh_tools.parsing.guest import parse_job_detail, parse_search_cards
from rrhh_tools.sources.base import guest_detail_url, guest_search_url

QUERY = Query(id="fixture", keywords="junior UX designer", geo="spain", workplace="remote")


def test_las_tarjetas_se_parsean_sin_avisos(settings, fixtures_dir):
    f = FixtureFetcher(fixtures_dir)
    tarjetas = parse_search_cards(f.get(guest_search_url(QUERY, settings, 0)))
    assert len(tarjetas) == 8
    assert sum(len(t["parse_warnings"]) for t in tarjetas) == 0
    primera = tarjetas[0]
    assert primera["job_id"] == "4001000001"
    assert primera["title"] == "Junior Product Designer"
    assert primera["company"] == "Bankinter"
    assert "/company/bankinter" in primera["company_url"]
    assert primera["url"] == "https://www.linkedin.com/jobs/view/4001000001/"


def test_una_pagina_vacia_termina_la_paginacion(settings, fixtures_dir):
    f = FixtureFetcher(fixtures_dir)
    assert parse_search_cards(f.get(guest_search_url(QUERY, settings, 10))) == []


def test_el_detalle_extrae_descripcion_nivel_y_sector(settings, fixtures_dir):
    f = FixtureFetcher(fixtures_dir)
    d = parse_job_detail(f.get(guest_detail_url("4001000001")))
    assert d["company_slug"] == "bankinter"
    assert d["li_seniority_field"] == "Prácticas"
    assert d["li_industries"] == ["Banking"]
    assert "roadmap de producto" in d["description"]


def test_el_parser_avisa_en_vez_de_romperse():
    """Si LinkedIn cambia el marcado, el parser debe degradarse, no explotar."""
    d = parse_job_detail("<html><body><p>marcado inesperado</p></body></html>")
    assert d["description"] is None
    assert "descripcion no encontrada" in d["parse_warnings"]

    assert parse_search_cards("<html><body>nada</body></html>") == []


def test_las_urls_llevan_los_filtros_correctos(settings):
    url = guest_search_url(QUERY, settings, 0)
    assert "geoId=105646813" in url      # España, verificado
    assert "f_E=1%2C2" in url            # prácticas + nivel inicial
    assert "f_WT=2" in url               # remoto
    assert "f_TPR=r604800" in url        # última semana
