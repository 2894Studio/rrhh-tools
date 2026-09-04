"""Clasificador de nivel.

Lo que cambió: esto era una puerta que descartaba todo lo que no fuera junior.
Ahora es una etiqueta, y lo único que abandona el pipeline es lo que no es
diseño digital. Los tests reflejan ese criterio nuevo, no una versión relajada
del antiguo.
"""

from pathlib import Path

import pytest
import yaml

from rrhh_tools.models import SeniorityLabel
from rrhh_tools.pipeline.seniority import classify_seniority

CASOS = yaml.safe_load(
    (Path(__file__).parent / "fixtures" / "titles.yaml").read_text(encoding="utf-8")
)["casos"]


@pytest.mark.parametrize("caso", CASOS, ids=[c["titulo"] for c in CASOS])
def test_tabla_de_niveles(caso, settings):
    veredicto = classify_seniority(caso["titulo"], None, None, settings.patterns)
    assert veredicto.label.value == caso["nivel"], (
        f"{caso['titulo']!r}: esperaba {caso['nivel']}, salió {veredicto.label.value} "
        f"({veredicto.explanation})"
    )


def test_solo_el_no_diseno_abandona_el_pipeline(settings):
    """El cambio de criterio, en una línea.

    Antes salían NOT_DESIGN y NOT_JUNIOR. Ahora un senior se queda: es la foto
    completa del mercado, con el nivel como filtro.
    """
    for titulo, sobrevive in [
        ("Senior Product Designer", True),      # antes se descartaba
        ("Head of Design", True),               # antes se descartaba
        ("Product Designer", True),
        ("Junior UX Designer", True),
        ("Diseñador Industrial", False),        # lo único que sigue fuera
        ("Backend Engineer", False),
    ]:
        v = classify_seniority(titulo, None, None, settings.patterns)
        assert v.survives is sobrevive, f"{titulo}: {v.label.value} ({v.explanation})"


def test_lead_gana_a_senior_y_a_junior(settings):
    """Son dos listas distintas ahora, y el orden de comprobación importa."""
    assert classify_seniority("Senior Design Lead", None, None,
                              settings.patterns).label == SeniorityLabel.LEAD
    assert classify_seniority("Junior Design Manager", None, None,
                              settings.patterns).label == SeniorityLabel.LEAD
    assert classify_seniority("Senior UX Designer", None, None,
                              settings.patterns).label == SeniorityLabel.SENIOR


def test_un_titulo_que_mezcla_niveles_se_cuenta_como_el_mas_alto(settings):
    v = classify_seniority("Junior/Senior UX Designer", None, None, settings.patterns)
    assert v.label == SeniorityLabel.SENIOR
    assert v.confidence < 0.95           # se sabe que es dudoso
    assert v.positive_hits and v.negative_hits   # y se ve por qué


def test_un_titulo_mudo_es_mid_no_ambiguo(settings):
    """Llamarlo 'ambiguo' llenaba de dudas una lista entera sin aportar nada."""
    v = classify_seniority("Product Designer", None, None, settings.patterns)
    assert v.label == SeniorityLabel.MID


def test_el_cuerpo_corrige_el_nivel_cuando_el_titulo_calla(settings):
    junior = classify_seniority("Product Designer", "Buscamos perfil con 0-2 anos de experiencia",
                                None, settings.patterns)
    assert junior.label == SeniorityLabel.JUNIOR_BY_DESC
    assert junior.confidence < 0.95

    senior = classify_seniority("Product Designer", "Se requieren minimo 5 anos de experiencia",
                                None, settings.patterns)
    assert senior.label == SeniorityLabel.SENIOR

    mid = classify_seniority("Product Designer", "Buscamos alguien con 3 anos de experiencia",
                             None, settings.patterns)
    assert mid.label == SeniorityLabel.MID


def test_el_campo_de_linkedin_sirve_de_rescate(settings):
    v = classify_seniority("UX Designer", "Descripcion neutra", "Prácticas", settings.patterns)
    assert v.label == SeniorityLabel.JUNIOR_BY_DESC


def test_los_dos_junior_se_unifican_para_filtrar(settings):
    """En el informe, 'junior' es un solo filtro aunque haya dos etiquetas."""
    assert SeniorityLabel.JUNIOR.clave_filtro == "junior"
    assert SeniorityLabel.JUNIOR_BY_DESC.clave_filtro == "junior"
    assert SeniorityLabel.SENIOR.clave_filtro == "senior"
