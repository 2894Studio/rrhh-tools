"""Clasificador de empresas: cliente final vs agencia vs consultora vs seleccion.

Es la pieza central del proyecto. El objetivo de 2894 no es un listado de
ofertas sino saber A QUIEN LLAMAR, y eso depende por completo de acertar aqui.

Escalera de decision: gana el primer acierto decisivo, pero se registran TODAS
las reglas que dispararon para poder auditar y corregir la configuracion.

Tres protecciones contra falsos positivos, cada una nacida de un fallo concreto:
  1. La allowlist se consulta ANTES que el fuzzy -> "Singular Bank" no cae por
     parecerse a "Sngular" (que es una consultora).
  2. Los nombres cortos de un solo token son exact-match -> "Indra", "VASS",
     "GFT" o "Babel" colisionarian con demasiadas cosas via fuzzy.
  3. Una palabra clave en el NOMBRE nunca puede excluir por si sola -> si no,
     "Prosegur Solutions", "Digital Origin" o "Glovo Labs" caerian por contener
     "solutions" / "digital" / "labs".
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from ..config import Settings
from ..models import Block, Classification, CompanyLabel
from ..normalize import basic_norm, normalize_company_name, normalize_text

_CATEGORY_TO_LABEL = {
    "agency": CompanyLabel.AGENCY,
    "consultancy": CompanyLabel.CONSULTANCY,
    "staffing": CompanyLabel.STAFFING,
}

FUZZY_STRONG = 0.93
FUZZY_WEAK = 0.86
MIN_FUZZY_LEN = 6


@dataclass
class DenyEntry:
    name: str
    category: str
    norm: str
    tokens: set[str]
    aliases: list[str]
    alias_norms: list[str]
    slugs: list[str]
    exact_only: bool


def _build_deny_index(settings: Settings) -> list[DenyEntry]:
    suffixes = settings.legal_suffixes
    entries: list[DenyEntry] = []
    for raw in settings.denylist.get("companies", []):
        norm = normalize_company_name(raw["name"], suffixes)
        aliases = raw.get("aliases", []) or []
        exact_only = raw.get("match") == "exact" or norm.is_short_single_token
        entries.append(DenyEntry(
            name=raw["name"],
            category=raw["category"],
            norm=norm.norm,
            tokens=norm.tokens,
            aliases=aliases,
            alias_norms=[normalize_company_name(a, suffixes).norm for a in aliases],
            slugs=[s.lower() for s in (raw.get("linkedin_slugs") or [])],
            exact_only=exact_only,
        ))
    return entries


def _build_allow_index(settings: Settings) -> dict[str, str]:
    """norm -> sector. Incluye alias, porque 'Zara' debe resolver a Inditex."""
    suffixes = settings.legal_suffixes
    index: dict[str, str] = {}
    for raw in settings.allowlist.get("companies", []):
        sector = raw.get("sector", "")
        index[normalize_company_name(raw["name"], suffixes).norm] = sector
        for alias in raw.get("aliases", []) or []:
            index[normalize_company_name(alias, suffixes).norm] = sector
    return index


def _block_for(label: CompanyLabel, settings: Settings) -> Block:
    if label == CompanyLabel.END_CLIENT:
        return Block.TARGET
    if label == CompanyLabel.AGENCY:
        return Block.COMPETITION
    if label in (CompanyLabel.CONSULTANCY, CompanyLabel.STAFFING):
        return Block.INTERMEDIARY
    return Block.REVIEW


class CompanyClassifier:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.deny = _build_deny_index(settings)
        self.allow = _build_allow_index(settings)
        self.overrides = {
            basic_norm(o["company_key"]): o
            for o in (settings.decisions.get("overrides") or [])
        }
        self.name_keywords = settings.denylist.get("name_keywords", {})
        self.desc_patterns = settings.denylist.get("description_patterns", {})
        self.industries = settings.denylist.get("li_industries", {})
        self.thresholds = settings.thresholds

    # ------------------------------------------------------------------
    def classify(
        self,
        company_name: str,
        description: str | None = None,
        linkedin_slug: str | None = None,
        li_industries: list[str] | None = None,
    ) -> Classification:
        reasons: list[str] = []
        norm = normalize_company_name(company_name, self.settings.legal_suffixes)

        # --- Regla 0: override humano. Manda sobre todo lo demas. ---
        for key in filter(None, [basic_norm(linkedin_slug or ""), norm.norm]):
            if key in self.overrides:
                override = self.overrides[key]
                label = CompanyLabel(override["verdict"])
                note = override.get("note", "")
                return Classification(
                    label=label, confidence=1.0, block=_block_for(label, self.settings),
                    reasons=[f"Decisión manual del equipo: {label.value}." + (f" {note}" if note else "")],
                    rule_source="manual_override",
                )

        # --- Regla 1: slug de LinkedIn en denylist. La senal mas fiable. ---
        slug = (linkedin_slug or "").lower().strip("/")
        if slug:
            for entry in self.deny:
                if slug in entry.slugs:
                    return self._deny(entry, 0.99, "slug",
                                      reasons + [f"El slug de LinkedIn '{slug}' es {entry.name}."])

        # --- Regla 2: nombre normalizado exacto ---
        for entry in self.deny:
            if norm.norm and (norm.norm == entry.norm or norm.norm in entry.alias_norms):
                return self._deny(entry, 0.97, "exact",
                                  reasons + [f"Coincidencia exacta con {entry.name} en la denylist."])

        # --- Regla 3: allowlist. ANTES del fuzzy, y esto es deliberado. ---
        if norm.norm in self.allow:
            sector = self.allow[norm.norm]
            reasons.append(
                f"Está en la allowlist de clientes finales conocidos"
                + (f" (sector: {sector})." if sector else ".")
            )
            return Classification(
                label=CompanyLabel.END_CLIENT, confidence=0.95, block=Block.TARGET,
                reasons=reasons, rule_source="allowlist",
            )

        # --- Regla 4: todos los tokens de la denylist contenidos en el nombre ---
        for entry in self.deny:
            if len(entry.tokens) >= 2 and entry.tokens and entry.tokens <= norm.tokens:
                return self._deny(entry, 0.90, "token_subset",
                                  reasons + [f"El nombre contiene todos los términos de {entry.name}."])

        # --- Reglas 5 y 6: fuzzy, con las tres protecciones puestas ---
        best, best_ratio = None, 0.0
        if len(norm.norm) >= MIN_FUZZY_LEN and not norm.is_short_single_token:
            for entry in self.deny:
                if entry.exact_only:
                    continue  # nombres cortos o marcados: solo coincidencia exacta
                for candidate in [entry.norm, *entry.alias_norms]:
                    if len(candidate) < MIN_FUZZY_LEN:
                        continue
                    ratio = SequenceMatcher(None, norm.norm, candidate).ratio()
                    if ratio > best_ratio:
                        best, best_ratio = entry, ratio
        if best and best_ratio >= FUZZY_STRONG:
            return self._deny(best, 0.85, "fuzzy",
                              reasons + [f"Parecido muy alto con {best.name} ({best_ratio:.2f})."])
        if best and best_ratio >= FUZZY_WEAK:
            label = _CATEGORY_TO_LABEL[best.category]
            reasons.append(
                f"Parecido moderado con {best.name} ({best_ratio:.2f}). "
                "No es suficiente para excluir: lo mira una persona."
            )
            return Classification(
                label=label, confidence=0.60, block=Block.REVIEW,
                reasons=reasons, rule_source="fuzzy_weak",
            )

        # --- Regla 7: patrones en la descripcion ---
        desc_label, desc_conf, desc_reasons = self._score_description(description)
        reasons.extend(desc_reasons)

        # --- Regla 8: sector declarado en LinkedIn ---
        ind_label, ind_conf, ind_reasons = self._score_industries(li_industries or [])
        reasons.extend(ind_reasons)

        # --- Regla 9: palabras clave en el nombre. SOLO modificador. ---
        kw_category, kw_reason = self._name_keyword(norm.tokens)
        if kw_reason:
            reasons.append(kw_reason)

        label, confidence, source = self._combine(
            desc_label, desc_conf, ind_label, ind_conf, kw_category
        )

        if label == CompanyLabel.UNKNOWN:
            reasons.append("Ninguna regla identificó el tipo de empresa.")
            return Classification(
                label=CompanyLabel.UNKNOWN, confidence=0.0, block=Block.REVIEW,
                reasons=reasons, rule_source="default",
            )

        if label == CompanyLabel.END_CLIENT:
            block = (Block.TARGET if confidence >= self.thresholds["include_at"]
                     else Block.REVIEW)
        else:
            block = (_block_for(label, self.settings)
                     if confidence >= self.thresholds["exclude_at"] else Block.REVIEW)

        return Classification(label=label, confidence=round(confidence, 2),
                              block=block, reasons=reasons, rule_source=source)

    # ------------------------------------------------------------------
    def _deny(self, entry: DenyEntry, confidence: float, source: str,
              reasons: list[str]) -> Classification:
        label = _CATEGORY_TO_LABEL[entry.category]
        return Classification(
            label=label, confidence=confidence, block=_block_for(label, self.settings),
            reasons=reasons, rule_source=source,
        )

    def _score_description(self, description: str | None):
        if not description:
            return CompanyLabel.UNKNOWN, 0.0, []
        body = normalize_text(description)
        total = 0.0
        per_category: dict[str, float] = {}
        reasons: list[str] = []
        for category, spec in self.desc_patterns.items():
            weight = float(spec.get("weight", 0))
            for pattern in spec.get("patterns", []):
                if basic_norm(pattern) in body:
                    total += weight
                    per_category[category] = per_category.get(category, 0.0) + weight
                    reasons.append(f'La oferta dice "{pattern}".')
        # Escalones: una frase de intermediario es indicio; dos o mas frases
        # independientes ("para uno de nuestros clientes" + "importante empresa
        # del sector") son concluyentes. Sin este primer escalon el maximo era
        # 0.80, por debajo del umbral de exclusion, y ninguna oferta podia
        # clasificarse por su texto por explicita que fuera: todas acababan en
        # revision manual.
        if total <= -6:
            worst = min(per_category, key=lambda k: per_category[k])
            return _CATEGORY_TO_LABEL.get(worst, CompanyLabel.STAFFING), 0.88, reasons
        if total <= -4:
            worst = min(per_category, key=lambda k: per_category[k])
            return _CATEGORY_TO_LABEL.get(worst, CompanyLabel.STAFFING), 0.80, reasons
        if total <= -2:
            worst = min(per_category, key=lambda k: per_category[k])
            return _CATEGORY_TO_LABEL.get(worst, CompanyLabel.STAFFING), 0.65, reasons
        if total >= 4:
            return CompanyLabel.END_CLIENT, 0.75, reasons
        if total >= 2:
            return CompanyLabel.END_CLIENT, 0.60, reasons
        return CompanyLabel.UNKNOWN, 0.0, reasons

    def _score_industries(self, industries: list[str]):
        reasons: list[str] = []
        for industry in industries:
            if industry in self.industries.get("deny_strong", []):
                reasons.append(f"Sector declarado en LinkedIn: {industry}.")
                # Por encima de exclude_at a proposito: autodeclararse de este
                # sector es una senal muy fiable, y dejarlo por debajo mandaria
                # todos los intermediarios a revision manual.
                return CompanyLabel.STAFFING, 0.86, reasons
        for industry in industries:
            if industry in self.industries.get("deny_weak", []):
                # Nunca decisivo: las empresas de producto se auto-etiquetan asi
                # constantemente y perderiamos clientes finales buenos.
                reasons.append(
                    f"Sector declarado: {industry} (indicio débil, no concluyente)."
                )
                return CompanyLabel.CONSULTANCY, 0.60, reasons
        for industry in industries:
            if industry in self.industries.get("allow", []):
                reasons.append(f"Sector de cliente final: {industry}.")
                return CompanyLabel.END_CLIENT, 0.70, reasons
        return CompanyLabel.UNKNOWN, 0.0, reasons

    def _name_keyword(self, tokens: set[str]) -> tuple[str | None, str | None]:
        for category, words in self.name_keywords.items():
            hit = tokens & set(words)
            if hit:
                return category, (
                    f"El nombre contiene '{', '.join(sorted(hit))}' "
                    f"(indicio de {category}, solo modificador)."
                )
        return None, None

    def _combine(self, desc_label, desc_conf, ind_label, ind_conf, kw_category):
        """Combina descripcion, sector y palabras del nombre.

        La palabra clave del nombre solo puede EMPUJAR una senal que ya existe,
        nunca crear un veredicto. Esa es la proteccion 3.
        """
        candidates = [(desc_label, desc_conf, "description_keywords"),
                      (ind_label, ind_conf, "li_industry")]
        candidates = [c for c in candidates if c[0] != CompanyLabel.UNKNOWN]
        if not candidates:
            return CompanyLabel.UNKNOWN, 0.0, "default"

        label, confidence, source = max(candidates, key=lambda c: c[1])
        if kw_category and _CATEGORY_TO_LABEL.get(kw_category) == label:
            confidence = min(confidence + 0.15, 0.95)
            source += "+name_keywords"
        return label, confidence, source
