from datetime import date

from rrhh_tools.models import JobPosting, LocationBucket
from rrhh_tools.pipeline.dedupe import dedupe_jobs, find_alias_suspicions


def oferta(job_id, titulo, empresa, fecha, source="guest", desc=None,
           bucket=LocationBucket.MADRID):
    return JobPosting(job_id=job_id, title_raw=titulo, company_key=empresa,
                      company_name_raw=empresa, location_bucket=bucket,
                      posted_at=fecha, source=source, description_text=desc)


def test_mismo_id_se_fusiona_y_gana_la_sesion():
    a = oferta("1", "Junior UX Designer", "acme", date(2026, 9, 1))
    b = oferta("1", "Junior UX Designer", "acme", date(2026, 9, 1), "session", "descripción")
    out, fusionadas = dedupe_jobs([a, b])
    assert len(out) == 1 and fusionadas == 1
    assert out[0].description_text == "descripción"
    assert out[0].n_sightings == 2


def test_repost_con_titulo_retocado_se_fusiona_y_gana_el_mas_reciente():
    a = oferta("1", "Junior UX Designer", "acme", date(2026, 9, 1))
    b = oferta("2", "UX Designer Junior", "acme", date(2026, 9, 3))
    out, fusionadas = dedupe_jobs([a, b])
    assert len(out) == 1 and fusionadas == 1
    assert out[0].job_id == "2"
    assert "1" in out[0].merged_ids


def test_puestos_distintos_de_la_misma_empresa_no_se_fusionan():
    a = oferta("1", "Junior UX Designer", "acme", date(2026, 9, 1))
    b = oferta("2", "Junior Product Manager", "acme", date(2026, 9, 1))
    out, fusionadas = dedupe_jobs([a, b])
    assert len(out) == 2 and fusionadas == 0


def test_el_fuzzy_de_titulo_nunca_cruza_empresas():
    """Dos empresas distintas con el mismo puesto son dos oportunidades."""
    a = oferta("1", "Junior UX Designer", "acme", date(2026, 9, 1))
    b = oferta("2", "Junior UX Designer", "otra", date(2026, 9, 1))
    out, fusionadas = dedupe_jobs([a, b])
    assert len(out) == 2 and fusionadas == 0


def test_la_misma_oferta_en_ubicaciones_distintas_no_se_fusiona():
    a = oferta("1", "Junior UX Designer", "acme", date(2026, 9, 1), bucket=LocationBucket.MADRID)
    b = oferta("2", "Junior UX Designer", "acme", date(2026, 9, 1), bucket=LocationBucket.REMOTE_ES)
    out, _ = dedupe_jobs([a, b])
    assert len(out) == 2


def test_el_recuento_siempre_cuadra():
    ofertas = [
        oferta("1", "Junior UX Designer", "acme", date(2026, 9, 1)),
        oferta("1", "Junior UX Designer", "acme", date(2026, 9, 1)),
        oferta("2", "UX Designer Junior", "acme", date(2026, 9, 3)),
        oferta("3", "Product Designer", "acme", date(2026, 9, 2)),
        oferta("4", "Junior UX Designer", "otra", date(2026, 9, 1)),
    ]
    out, fusionadas = dedupe_jobs(ofertas)
    assert len(out) + fusionadas == len(ofertas)


def test_los_alias_se_reportan_pero_no_se_fusionan_solos():
    """Unir 'Acme' con 'Acme España' puede ser correcto o un error;
    equivocarse contamina el informe, así que decide una persona."""
    a = oferta("1", "Junior UX Designer", "acme", date(2026, 9, 1))
    b = oferta("2", "Junior UI Designer", "acme-spain", date(2026, 9, 1))
    b.company_name_raw = a.company_name_raw = "Acme"
    sospechas = find_alias_suspicions([a, b])
    assert len(sospechas) == 1 and "Acme" in sospechas[0]
