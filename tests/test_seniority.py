import yaml
import pytest
from pathlib import Path

from rrhh_tools.pipeline.seniority import classify_seniority

CASOS = yaml.safe_load((Path(__file__).parent / "fixtures" / "titles.yaml").read_text(encoding="utf-8"))["casos"]


@pytest.mark.parametrize("caso", CASOS, ids=[c["titulo"] for c in CASOS])
def test_tabla_de_titulos(caso, settings):
    veredicto = classify_seniority(caso["titulo"], None, None, settings.patterns)
    assert veredicto.label.value == caso["esperado"], (
        f"{caso['titulo']!r}: esperaba {caso['esperado']}, salió {veredicto.label.value} "
        f"({veredicto.explanation})"
    )


def test_la_negativa_gana_a_la_positiva(settings):
    """La regla que gobierna todo el filtro."""
    v = classify_seniority("Senior Junior Designer", None, None, settings.patterns)
    assert v.label.value == "AMBIGUOUS"   # mezcla explícita: decide una persona
    v = classify_seniority("Senior Product Designer", None, None, settings.patterns)
    assert v.label.value == "NOT_JUNIOR"


def test_rescate_por_descripcion_cuando_el_titulo_calla(settings):
    v = classify_seniority("Product Designer", "Buscamos perfil con 0-2 anos de experiencia",
                           None, settings.patterns)
    assert v.label.value == "JUNIOR_BY_DESC"
    assert v.confidence < 0.95   # menos fiable que el título: va a revisión


def test_la_descripcion_tambien_puede_descartar(settings):
    v = classify_seniority("Product Designer", "Se requieren minimo 5 anos de experiencia",
                           None, settings.patterns)
    assert v.label.value == "NOT_JUNIOR"


def test_el_campo_de_linkedin_sirve_de_rescate(settings):
    v = classify_seniority("UX Designer", "Descripcion neutra", "Prácticas", settings.patterns)
    assert v.label.value == "JUNIOR_BY_DESC"


def test_solo_dos_veredictos_abandonan_el_pipeline(settings):
    for titulo, sobrevive in [("Senior Product Designer", False), ("Interior Designer", False),
                              ("Junior UX Designer", True), ("Product Designer", True)]:
        v = classify_seniority(titulo, None, None, settings.patterns)
        assert v.survives is sobrevive, titulo
