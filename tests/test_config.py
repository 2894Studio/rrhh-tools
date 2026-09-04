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
    """Un geoId adivinado buscaría en otra región sin dar ningún error."""
    with pytest.raises(ConfigError, match="sin resolver"):
        settings.geo_id("comunidad_madrid")


def test_las_queries_bloqueadas_se_separan_con_su_motivo(settings):
    lanzables, bloqueadas = settings.resolvable_queries()
    assert lanzables, "las búsquedas de ámbito España sí deben poder lanzarse"
    assert bloqueadas, "las de Madrid deben quedar bloqueadas hasta resolver el geoId"
    assert all("geoId" in b for b in bloqueadas)


def test_el_geoid_de_espana_esta_verificado(settings):
    assert settings.geo_id("spain") == "105646813"


def test_todas_las_regex_compilan(settings):
    p = settings.patterns
    total = sum(len(getattr(p, campo)) for campo in vars(p))
    assert total > 50


def test_el_hash_de_configuracion_es_estable(settings):
    assert settings.config_hash == settings.config_hash
    assert len(settings.config_hash) == 12
