import pytest

from rrhh_tools.normalize import (
    basic_norm, normalize_company_name, normalize_title, strip_accents, title_core,
)


@pytest.mark.parametrize("raw,esperado", [
    ("Telefónica, S.A.", "telefonica"),
    ("Acme Solutions S.L.U.", "acme solutions"),
    ("Grupo Bimbo", "grupo bimbo"),          # 'Grupo' delante forma parte del nombre
    ("Inditex España", "inditex"),
    ("Prosegur Solutions", "prosegur solutions"),
    ("The Cocktail Experience", "the cocktail experience"),
])
def test_sufijos_legales_se_recortan_solo_al_final(raw, esperado, settings):
    assert normalize_company_name(raw, settings.legal_suffixes).norm == esperado


def test_nombres_cortos_de_un_token_se_marcan_para_exact_match(settings):
    # Es la protección que impide que 'Sngular' colisione por fuzzy.
    assert normalize_company_name("Sngular", settings.legal_suffixes).is_short_single_token
    assert not normalize_company_name("Singular Bank", settings.legal_suffixes).is_short_single_token


def test_strip_accents():
    assert strip_accents("Diseñador sénior") == "Disenador senior"


@pytest.mark.parametrize("a,b", [
    ("Junior UX/UI Designer (m/f/d)", "UX/UI Designer"),
    ("Diseñador/a UX Junior - Madrid (Remoto)", "Diseñador UX"),
    ("Senior Product Designer", "Product Designer"),
])
def test_title_core_ignora_nivel_genero_modalidad_y_ciudad(a, b):
    assert title_core(a) == title_core(b)


def test_title_core_distingue_puestos_distintos():
    assert title_core("Junior UX Designer") != title_core("Junior Product Manager")


def test_basic_norm_colapsa_espacios_y_puntuacion():
    assert basic_norm("  Foo &  Bar,  S.L.  ") == "foo and bar s l"


def test_normalize_title_limpia_el_ruido_antes_de_la_puntuacion():
    # Si se quitara la puntuación primero, "(m/f/d)" ya sería "m f d"
    # y su patrón de ruido no encontraría nada.
    assert "m f d" not in normalize_title("UX Designer (m/f/d)")
