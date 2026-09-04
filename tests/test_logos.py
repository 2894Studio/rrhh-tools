"""Logos de empresa.

La regla de fondo: nunca se adivina. Un logo equivocado en una ficha comercial
hace dudar del resto de la ficha, así que sin fuente fiable se cae al monograma.
"""

from rrhh_tools.logos import por_dominio
from rrhh_tools.models import (
    Block, Classification, CompanyLabel, Company, JobPosting, LocationBucket,
)
from rrhh_tools.parsing.guest import parse_search_cards
from rrhh_tools.parsing.session import parse_session_cards


def _empresa(nombre: str) -> Company:
    return Company(
        key=nombre.lower(), display_name=nombre,
        classification=Classification(label=CompanyLabel.END_CLIENT,
                                      confidence=0.9, block=Block.TARGET),
    )


def test_sin_dominio_no_hay_logo():
    assert por_dominio(None) is None
    assert por_dominio("") is None


def test_el_favicon_se_construye_desde_el_dominio():
    assert por_dominio("Seedtag.com") == "https://icons.duckduckgo.com/ip3/seedtag.com.ico"


def test_el_monograma_usa_las_iniciales():
    assert _empresa("Clarity AI").monograma == "CA"
    assert _empresa("Seedtag").monograma == "SE"
    assert _empresa("Banco Santander").monograma == "BS"


def test_el_monograma_nunca_revienta():
    assert _empresa("").monograma == "?"
    assert _empresa("···").monograma == "?"


def test_el_logo_sale_de_la_tarjeta_de_linkedin():
    """Es la fuente más fiable: viene con el resto del dato."""
    html = (
        '<ul><li><div class="base-card" data-entity-urn="urn:li:jobPosting:123456789">'
        '<a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/123456789"></a>'
        '<img class="artdeco-entity-image" data-delayed-url="https://media.licdn.com/logo.png">'
        '<h3 class="base-search-card__title">Junior UX Designer</h3>'
        '<h4 class="base-search-card__subtitle">Acme</h4>'
        '</div></li></ul>'
    )
    card = parse_search_cards(html)[0]
    assert card["company_logo_url"] == "https://media.licdn.com/logo.png"


def test_el_logo_tambien_se_extrae_del_dom_con_sesion():
    html = (
        '<div class="job-card-container" data-job-id="4002000001">'
        '<a class="job-card-container__link" href="/jobs/view/4002000001/">'
        '<span aria-hidden="true">Junior UI Designer</span></a>'
        '<img class="ivm-view-attr__img--centered" src="https://media.licdn.com/x.png">'
        '<div class="artdeco-entity-lockup__subtitle">Acme</div>'
        '</div>'
    )
    card = parse_session_cards(html)[0]
    assert card["company_logo_url"] == "https://media.licdn.com/x.png"


def test_una_url_de_logo_relativa_se_descarta():
    """Un src relativo no sirve fuera de LinkedIn: mejor monograma."""
    html = (
        '<div class="job-card-container" data-job-id="1234567">'
        '<a class="job-card-container__link" href="/jobs/view/1234567/">'
        '<span aria-hidden="true">Junior UI Designer</span></a>'
        '<img src="/static/ghost.png">'
        '</div>'
    )
    assert parse_session_cards(html)[0]["company_logo_url"] is None


def test_el_logo_llega_hasta_la_empresa_agregada(settings):
    from datetime import date
    from rrhh_tools.pipeline.run import process
    registros = [{
        "job_id": "1", "title": "Junior UX Designer", "company": "Bankinter",
        "company_url": "https://www.linkedin.com/company/bankinter",
        "company_logo_url": "https://media.licdn.com/logo.png",
        "location": "Madrid, España", "posted_text": "hace 2 días",
        "description": "Nuestro producto.", "source": "session",
    }]
    run = process(registros, settings, "t", today=date(2026, 9, 4))
    assert run.targets[0].logo_url == "https://media.licdn.com/logo.png"
