from pathlib import Path

import pytest
import yaml

from rrhh_tools.models import CompanyLabel
from rrhh_tools.pipeline.classifier import CompanyClassifier

CASOS = yaml.safe_load(
    (Path(__file__).parent / "fixtures" / "companies.yaml").read_text(encoding="utf-8")
)["casos"]


@pytest.fixture(scope="module")
def clasificador(settings):
    return CompanyClassifier(settings)


@pytest.mark.parametrize("caso", CASOS, ids=[c["nombre"] for c in CASOS])
def test_tabla_de_empresas(caso, clasificador):
    r = clasificador.classify(caso["nombre"])
    assert r.label.value == caso["esperado"], f"{caso['nombre']}: {r.reasons}"
    assert r.block.value == caso["bloque"], f"{caso['nombre']}: {r.reasons}"


# --- Las tres protecciones contra falsos positivos ---

def test_la_allowlist_se_consulta_antes_que_el_fuzzy(clasificador):
    """Singular Bank no puede caer por parecerse a Sngular (consultora)."""
    assert clasificador.classify("Singular Bank").label == CompanyLabel.END_CLIENT
    assert clasificador.classify("Sngular").label == CompanyLabel.CONSULTANCY


@pytest.mark.parametrize("nombre", [
    "Prosegur Solutions", "Digital Origin", "Glovo Labs",
    "Acme Talent Media", "Estudio Bantierra",
])
def test_una_palabra_del_nombre_nunca_excluye_por_si_sola(nombre, clasificador):
    """Sin esta regla, cualquier empresa con 'solutions', 'labs', 'talent' o
    'estudio' en el nombre caeria injustamente."""
    r = clasificador.classify(nombre)
    assert r.block.value != "B", f"{nombre} excluida solo por su nombre: {r.reasons}"
    assert r.block.value != "C", f"{nombre} excluida solo por su nombre: {r.reasons}"


@pytest.mark.parametrize("nombre", ["Indra", "VASS", "GFT", "Babel", "Seidor"])
def test_los_nombres_cortos_son_exact_match(nombre, settings, clasificador):
    """Deben casar exactamente, pero no arrastrar a nombres parecidos."""
    assert clasificador.classify(nombre).label == CompanyLabel.CONSULTANCY
    parecido = clasificador.classify(nombre + "tech Soluciones Digitales")
    assert parecido.block.value == "D", parecido.reasons


# --- Heuristicas de texto y sector ---

def test_la_frase_de_intermediario_es_la_senal_mas_potente(clasificador):
    r = clasificador.classify(
        "Consultora Anónima",
        "Para uno de nuestros clientes, importante empresa del sector, seleccionamos...",
    )
    assert r.label == CompanyLabel.STAFFING
    assert r.block.value == "C"


def test_las_senales_de_producto_propio_indican_cliente_final(clasificador):
    r = clasificador.classify(
        "Producto Nuevo SL",
        "Trabajarás en nuestro producto, con nuestros usuarios, definiendo el roadmap de producto.",
    )
    assert r.label == CompanyLabel.END_CLIENT


def test_el_sector_de_consultoria_nunca_es_concluyente(clasificador):
    """Las empresas de producto se auto-etiquetan asi constantemente."""
    r = clasificador.classify("Empresa X", None, None, ["IT Services and IT Consulting"])
    assert r.block.value == "D"      # a revisión, no a exclusión
    assert r.confidence < 0.85


def test_el_override_manual_manda_sobre_todo(settings):
    settings.decisions["overrides"] = [
        {"company_key": "nateevo", "verdict": "END_CLIENT", "note": "caso de prueba"}
    ]
    try:
        r = CompanyClassifier(settings).classify("Nateevo")
        assert r.label == CompanyLabel.END_CLIENT
        assert r.rule_source == "manual_override"
    finally:
        settings.decisions["overrides"] = []


def test_toda_clasificacion_explica_por_que(clasificador):
    for nombre in ["Nateevo", "BBVA", "Empresa Rara SL"]:
        r = clasificador.classify(nombre)
        assert r.reasons, f"{nombre} sin explicación"
        assert all(isinstance(x, str) and x for x in r.reasons)
