"""Carga y validacion de la configuracion.

Dos validaciones existen para impedir ejecuciones que fallarian en silencio:

1. Los pesos del scoring deben sumar 100. Si no, las puntuaciones no son
   comparables entre ejecuciones y nadie se daria cuenta.
2. Una query no puede lanzarse con un geoId sin resolver. Un geoId adivinado
   devuelve resultados de la region equivocada sin error alguno.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PLACEHOLDER_PREFIX = "PLACEHOLDER"
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


class ConfigError(RuntimeError):
    pass


@dataclass
class Query:
    id: str
    keywords: str
    geo: str
    workplace: str | None = None


@dataclass
class CompiledPatterns:
    """Regex ya compiladas. Se compilan una vez, no en cada oferta."""

    role_positive: list[re.Pattern]
    role_exclude: list[re.Pattern]
    sen_senior: list[re.Pattern]
    sen_lead: list[re.Pattern]
    sen_senior_cased: list[re.Pattern]
    sen_positive: list[re.Pattern]
    sen_weak_positive: list[re.Pattern]
    desc_sen_positive: list[re.Pattern]
    desc_sen_negative: list[re.Pattern]
    desc_sen_mid: list[re.Pattern]
    rol_ai: list[re.Pattern]
    rol_uxui: list[re.Pattern]
    rol_product: list[re.Pattern]
    rol_ux: list[re.Pattern]
    rol_ui: list[re.Pattern]
    ai: list[re.Pattern]
    first_designer_strong: list[re.Pattern]
    first_designer_mature: list[re.Pattern]


@dataclass
class Settings:
    raw: dict[str, Any]
    denylist: dict[str, Any]
    allowlist: dict[str, Any]
    keywords: dict[str, Any]
    decisions: dict[str, Any]
    patterns: CompiledPatterns
    legal_suffixes: set[str] = field(default_factory=set)
    config_dir: Path = DEFAULT_CONFIG_DIR

    # --- accesos comodos ---
    @property
    def weights(self) -> dict[str, float]:
        return self.raw["scoring"]["weights"]

    @property
    def thresholds(self) -> dict[str, float]:
        return self.raw["thresholds"]

    @property
    def run(self) -> dict[str, Any]:
        return self.raw["run"]

    @property
    def report(self) -> dict[str, Any]:
        return self.raw["report"]

    @property
    def queries(self) -> list[Query]:
        return [Query(**q) for q in self.raw["queries"]]

    def geo_id(self, name: str) -> str:
        geos = self.raw["search"]["geo"]
        if name not in geos:
            raise ConfigError(f"geo desconocido: {name!r}. Definelo en config.yaml -> search.geo")
        value = str(geos[name])
        if value.startswith(PLACEHOLDER_PREFIX):
            raise ConfigError(
                f"El geoId de {name!r} sigue sin resolver ({value}).\n"
                "Un geoId adivinado buscaria en la region equivocada sin dar ningun error.\n"
                "Filtra por esa ubicacion en LinkedIn y copia el parametro geoId= de la URL "
                "a config/config.yaml."
            )
        return value

    def resolvable_queries(self) -> tuple[list[Query], list[str]]:
        """Separa las queries lanzables de las bloqueadas por un geo sin resolver."""
        ok, blocked = [], []
        for query in self.queries:
            try:
                self.geo_id(query.geo)
                ok.append(query)
            except ConfigError as exc:
                blocked.append(f"{query.id}: {exc}")
        return ok, blocked

    @property
    def config_hash(self) -> str:
        blob = yaml.safe_dump(
            [self.raw, self.denylist, self.allowlist, self.keywords, self.decisions],
            sort_keys=True,
        )
        return hashlib.sha1(blob.encode()).hexdigest()[:12]


def _compile(patterns: list[str], flags: int = re.IGNORECASE) -> list[re.Pattern]:
    return [re.compile(p, flags) for p in patterns]


def _validate_weights(raw: dict[str, Any]) -> None:
    weights = raw.get("scoring", {}).get("weights", {})
    total = sum(weights.values())
    if abs(total - 100) > 0.001:
        raise ConfigError(
            f"Los pesos del scoring suman {total}, deben sumar 100.\n"
            "Sin esto las puntuaciones dejan de ser comparables entre ejecuciones.\n"
            f"Pesos actuales: {weights}"
        )


def load_settings(config_dir: Path | str | None = None) -> Settings:
    directory = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
    if not directory.is_dir():
        raise ConfigError(f"No existe el directorio de configuracion: {directory}")

    def read(name: str) -> dict[str, Any]:
        path = directory / name
        if not path.is_file():
            raise ConfigError(f"Falta el fichero de configuracion: {path}")
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    raw = read("config.yaml")
    denylist = read("denylist.yaml")
    allowlist = read("allowlist.yaml")
    keywords = read("keywords.yaml")
    decisions = read("decisions.yaml")

    _validate_weights(raw)

    kw = keywords
    patterns = CompiledPatterns(
        role_positive=_compile(kw["role"]["positive"]),
        role_exclude=_compile(kw["role"]["exclude"]),
        sen_senior=_compile(kw["seniority"]["senior"]),
        sen_lead=_compile(kw["seniority"]["lead"]),
        # Sin IGNORECASE a proposito: los numeros romanos solo cuentan en mayusculas,
        # para que un "ii" minusculo dentro de otra palabra no dispare un falso positivo.
        sen_senior_cased=_compile(kw["seniority"]["senior_cased"], flags=0),
        sen_positive=_compile(kw["seniority"]["positive"]),
        sen_weak_positive=_compile(kw["seniority"]["weak_positive"]),
        desc_sen_positive=_compile(kw["description_seniority"]["positive"]),
        desc_sen_negative=_compile(kw["description_seniority"]["negative"]),
        desc_sen_mid=_compile(kw["description_seniority"]["mid"]),
        rol_ai=_compile(kw["rol"]["ai"]),
        rol_uxui=_compile(kw["rol"]["uxui"]),
        rol_product=_compile(kw["rol"]["product"]),
        rol_ux=_compile(kw["rol"]["ux"]),
        rol_ui=_compile(kw["rol"]["ui"]),
        ai=_compile(kw["ai_relevance"]["patterns"]),
        first_designer_strong=_compile(kw["first_designer"]["strong"]),
        first_designer_mature=_compile(kw["first_designer"]["mature"]),
    )

    return Settings(
        raw=raw,
        denylist=denylist,
        allowlist=allowlist,
        keywords=keywords,
        decisions=decisions,
        patterns=patterns,
        legal_suffixes=set(kw.get("legal_suffixes", [])),
        config_dir=directory,
    )
