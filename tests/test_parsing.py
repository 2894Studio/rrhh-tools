from rrhh_tools.config import Query
from rrhh_tools.http import FixtureFetcher
from rrhh_tools.parsing.guest import parse_job_detail, parse_search_cards
from rrhh_tools.sources.base import guest_detail_url, guest_search_url

def _query(settings) -> Query:
    """La misma a la que están ancladas las fixtures."""
    lanzables, _ = settings.resolvable_queries()
    return lanzables[0]


def test_las_tarjetas_se_parsean_sin_avisos(settings, fixtures_dir):
    f = FixtureFetcher(fixtures_dir)
    tarjetas = parse_search_cards(f.get(guest_search_url(_query(settings), settings, 0)))
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
    assert parse_search_cards(f.get(guest_search_url(_query(settings), settings, 10))) == []


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
    """Ya NO se filtra por nivel en LinkedIn.

    El campo f_E lo autodeclara quien publica la oferta y se equivoca a menudo.
    Ahora se traen todos los niveles y el nivel lo decide nuestro clasificador,
    que es lo que permite tener la foto completa del mercado.
    """
    madrid = next(q for q in settings.queries if q.geo == "comunidad_madrid")
    url = guest_search_url(madrid, settings, 0)
    assert "geoId=100994331" in url          # Comunidad de Madrid
    assert "f_E=" not in url                 # sin filtro de nivel, a propósito
    assert "f_TPR=r86400" in url             # ventana de 24h, para tirada diaria
    assert "f_WT=" not in url                # sin modalidad: Madrid presencial incluido

    remoto = next(q for q in settings.queries if q.workplace == "remote")
    url_remoto = guest_search_url(remoto, settings, 0)
    assert "geoId=105646813" in url_remoto   # España, verificado
    assert "f_WT=2" in url_remoto            # remoto
