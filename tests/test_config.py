import pytest
import yaml

from rrhh_tools.config import ConfigError, load_settings


def test_los_pesos_deben_sumar_cien(tmp_path, settings):
    """Sin esto las puntuaciones dejan de ser comparables entre ejecuciones."""
    for nombre in ["config.yaml", "denylist.yaml", "allowlist.yaml",
                   "keywords.yaml", "decisions.yaml"]:
        (tmp_path / nombre).write_text(
            (settings.config_dir / nombre).read_text(encoding="utf-8"), encoding="utf-8")
    roto = yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))
    roto["scoring"]["weights"]["recency"] = 99
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(roto), encoding="utf-8")

    with pytest.raises(ConfigError, match="deben sumar 100"):
        load_settings(tmp_path)


def test_un_geoid_sin_resolver_bloquea_la_busqueda(settings):
    """Un geoId adivinado buscaría en otra región sin dar ningún error.

    Se prueba el mecanismo con un geo sintético, no con una entrada concreta
    de la configuración: los geoId reales se van resolviendo con el tiempo y
    el test debe seguir cubriendo la protección.
    """
    settings.raw["search"]["geo"]["pruebas"] = "PLACEHOLDER_LO_QUE_SEA"
    try:
        with pytest.raises(ConfigError, match="sin resolver"):
            settings.geo_id("pruebas")
    finally:
        del settings.raw["search"]["geo"]["pruebas"]


def test_las_queries_bloqueadas_se_separan_con_su_motivo(settings):
    original = settings.raw["search"]["geo"]["spain"]
    settings.raw["search"]["geo"]["spain"] = "PLACEHOLDER_ESPANA"
    try:
        lanzables, bloqueadas = settings.resolvable_queries()
        assert bloqueadas, "las búsquedas con geo sin resolver deben quedar fuera"
        assert all("geoId" in b for b in bloqueadas)
        assert all("spain" not in q.geo for q in lanzables)
    finally:
        settings.raw["search"]["geo"]["spain"] = original


def test_todas_las_queries_configuradas_son_lanzables(settings):
    """Si esto falla, hay un geoId sin resolver y esas búsquedas no se harán."""
    lanzables, bloqueadas = settings.resolvable_queries()
    assert not bloqueadas, f"búsquedas bloqueadas: {bloqueadas}"
    assert len(lanzables) == len(settings.queries)


def test_los_geoid_estan_resueltos(settings):
    assert settings.geo_id("spain") == "105646813"
    assert settings.geo_id("comunidad_madrid") == "100994331"


def test_todas_las_regex_compilan(settings):
    p = settings.patterns
    total = sum(len(getattr(p, campo)) for campo in vars(p))
    assert total > 50


def test_un_geo_inexistente_da_un_error_claro(settings):
    with pytest.raises(ConfigError, match="geo desconocido"):
        settings.geo_id("narnia")


def test_el_hash_de_configuracion_es_estable(settings):
    assert settings.config_hash == settings.config_hash
    assert len(settings.config_hash) == 12
