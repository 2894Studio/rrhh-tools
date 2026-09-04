"""Clasificador de rol.

El orden de comprobación es lo único delicado: AI gana sobre todo, y UX/UI va
antes que UX y que UI. Estos tests fijan ese orden, que es el que se rompe si
alguien reordena el módulo sin pensarlo.
"""

from pathlib import Path

import pytest
import yaml

from rrhh_tools.models import Rol
from rrhh_tools.pipeline.rol import classify_rol

CASOS = yaml.safe_load(
    (Path(__file__).parent / "fixtures" / "titles.yaml").read_text(encoding="utf-8")
)["casos"]


@pytest.mark.parametrize("caso", CASOS, ids=[c["titulo"] for c in CASOS])
def test_tabla_de_roles(caso, settings):
    veredicto = classify_rol(caso["titulo"], None, settings.patterns)
    assert veredicto.label.value == caso["rol"], (
        f"{caso['titulo']!r}: esperaba {caso['rol']}, salió {veredicto.label.value} "
        f"({veredicto.explanation})"
    )


def test_la_ia_gana_sobre_el_resto_de_roles(settings):
    """Es el diferencial de los perfiles: hay que poder aislarlo de un vistazo."""
    v = classify_rol("AI Product Designer", None, settings.patterns)
    assert v.label == Rol.AI
    assert v.secundario == Rol.PRODUCT, "el rol de fondo no debe perderse"
    assert len(v.etiquetas) == 2


def test_uxui_va_antes_que_ux_y_que_ui(settings):
    """Si se comprobara UX primero, la categoría combinada quedaría vacía y en
    España es el título más común."""
    assert classify_rol("UX/UI Designer", None, settings.patterns).label == Rol.UXUI
    assert classify_rol("Diseñador UX/UI", None, settings.patterns).label == Rol.UXUI
    assert classify_rol("UI/UX Designer", None, settings.patterns).label == Rol.UXUI
    assert classify_rol("UX Designer", None, settings.patterns).label == Rol.UX


def test_un_rol_de_diseno_sin_especialidad_cae_en_otro(settings):
    v = classify_rol("Head of Design", None, settings.patterns)
    assert v.label == Rol.OTRO
    assert v.explanation


def test_todo_veredicto_explica_por_que(settings):
    for titulo in ["AI Designer", "Product Designer", "UX/UI Designer", "Design Manager"]:
        v = classify_rol(titulo, None, settings.patterns)
        assert v.explanation, titulo


def test_el_rol_llega_hasta_la_oferta_procesada(settings):
    from datetime import date
    from rrhh_tools.pipeline.run import process
    registros = [{
        "job_id": "1", "title": "Senior AI Product Designer", "company": "Acme",
        "location": "Madrid, España", "posted_text": "hace 2 días",
        "description": "Nuestro producto.", "source": "guest",
    }]
    run = process(registros, settings, "t", today=date(2026, 9, 4))
    empresa = (run.targets + run.review + run.competition + run.intermediaries)[0]
    oferta = empresa.jobs[0]
    assert oferta.rol.label == Rol.AI
    assert oferta.seniority.label.value == "SENIOR"
    # Y la empresa expone ambas claves para que el filtro del informe las use.
    assert "ai" in empresa.roles
    assert "senior" in empresa.niveles
