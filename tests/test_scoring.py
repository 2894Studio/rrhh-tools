from datetime import date

import pytest

from rrhh_tools.models import (
    Block, Classification, CompanyLabel, JobPosting, LocationBucket,
    SeniorityLabel, SeniorityVerdict,
)
from rrhh_tools.pipeline.scoring import score_company

HOY = date(2026, 9, 4)


def cliente_final(conf=0.95):
    return Classification(label=CompanyLabel.END_CLIENT, confidence=conf, block=Block.TARGET)


def oferta(**kw):
    base = dict(
        job_id="1", title_raw="Junior UX Designer", company_key="acme",
        company_name_raw="Acme", location_bucket=LocationBucket.MADRID,
        posted_at=HOY, posted_confidence=1.0, description_text="Descripción normal.",
        seniority=SeniorityVerdict(label=SeniorityLabel.JUNIOR, confidence=0.95),
    )
    base.update(kw)
    return JobPosting(**base)


def test_los_pesos_suman_cien(settings):
    assert sum(settings.weights.values()) == 100


def test_el_maximo_teorico_es_cien(settings):
    score, _, _ = score_company(
        cliente_final(),
        [oferta(description_text="IA, machine learning e inteligencia artificial. "
                                 "Serás el primer diseñador de la empresa."),
         oferta(job_id="2"), oferta(job_id="3")],
        settings, HOY)
    assert score == 100.0


def test_cada_componente_explica_su_valor(settings):
    _, componentes, _ = score_company(cliente_final(), [oferta()], settings, HOY)
    assert len(componentes) == len(settings.weights)
    for c in componentes:
        assert c.explanation, f"{c.name} sin explicación"
        assert 0.0 <= c.value <= 1.0


def test_no_ser_cliente_final_hunde_la_puntuacion(settings):
    agencia = Classification(label=CompanyLabel.AGENCY, confidence=0.97, block=Block.COMPETITION)
    alto, _, _ = score_company(cliente_final(), [oferta()], settings, HOY)
    bajo, _, _ = score_company(agencia, [oferta()], settings, HOY)
    assert alto - bajo == settings.weights["end_client_confidence"]


def test_la_ausencia_de_ia_no_descalifica(settings):
    _, componentes, _ = score_company(cliente_final(), [oferta()], settings, HOY)
    ia = next(c for c in componentes if c.name == "ai_relevance")
    assert ia.value == 0.2   # línea base, no cero


def test_primer_disenador_solo_con_evidencia_textual(settings):
    """No debe inferirse del número de vacantes: si se acoplara con el factor
    de volumen, ambos serían proxy del tamaño y se contaría dos veces."""
    _, sin_texto, _ = score_company(cliente_final(), [oferta(), oferta(job_id="2"),
                                                     oferta(job_id="3")], settings, HOY)
    fd = next(c for c in sin_texto if c.name == "first_designer_signal")
    assert fd.value == 0.5, "tres vacantes no deben activar la señal de primer diseñador"

    _, con_texto, _ = score_company(
        cliente_final(),
        [oferta(description_text="Serás el primer diseñador de la empresa.")], settings, HOY)
    fd = next(c for c in con_texto if c.name == "first_designer_signal")
    assert fd.value == 1.0


def test_la_frescura_se_pondera_por_la_confianza_de_la_fecha(settings):
    """'hace 2 semanas' es un rango, no un instante."""
    exacta = oferta(posted_at=date(2026, 9, 3), posted_confidence=1.0)
    difusa = oferta(posted_at=date(2026, 9, 3), posted_confidence=0.3)
    _, c_exacta, _ = score_company(cliente_final(), [exacta], settings, HOY)
    _, c_difusa, _ = score_company(cliente_final(), [difusa], settings, HOY)
    v_exacta = next(c for c in c_exacta if c.name == "recency").value
    v_difusa = next(c for c in c_difusa if c.name == "recency").value
    assert v_exacta > v_difusa          # la difusa se acerca al valor neutro
    assert abs(v_difusa - 0.5) < abs(v_exacta - 0.5)


def test_los_factores_de_oferta_toman_el_maximo(settings):
    """Se vende contra el mejor encaje disponible."""
    mala = oferta(job_id="1", location_bucket=LocationBucket.REST_ES)
    buena = oferta(job_id="2", location_bucket=LocationBucket.MADRID)
    _, componentes, _ = score_company(cliente_final(), [mala, buena], settings, HOY)
    assert next(c for c in componentes if c.name == "location_fit").value == 1.0


def test_la_puntuacion_es_determinista(settings):
    ofertas = [oferta(), oferta(job_id="2")]
    a, _, _ = score_company(cliente_final(), ofertas, settings, HOY)
    b, _, _ = score_company(cliente_final(), ofertas, settings, HOY)
    assert a == b


def test_un_factor_que_puntua_cero_conserva_su_explicacion(settings):
    """Bug real: max() con empate a 0.0 devolvía el inicializador vacío.

    Le pasaba a los puestos de nivel lead, que puntúan 0 en encaje de nivel:
    la tabla del informe mostraba la fila con la casilla "Lectura" en blanco.
    """
    from rrhh_tools.models import SeniorityVerdict
    oferta = JobPosting(
        job_id="1", title_raw="Head of Design", company_key="acme",
        company_name_raw="Acme", location_bucket=LocationBucket.OUTSIDE_ES,
        posted_at=HOY, posted_confidence=1.0, description_text="Descripción.",
        seniority=SeniorityVerdict(label=SeniorityLabel.LEAD, confidence=0.95),
    )
    _, componentes, _ = score_company(cliente_final(), [oferta], settings, HOY)
    for componente in componentes:
        assert componente.explanation, f"{componente.name} sin explicación"
