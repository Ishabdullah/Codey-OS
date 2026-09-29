import re
from dataclasses import dataclass, field
from enum import StrEnum
from fractions import Fraction
from typing import Final

from codey_estimator.catalog.schema import (
    Attr,
    AttrRole,
    NormalizedAttributes,
    get_schema,
    normalize_brand,
)
from codey_estimator.errors import CatalogValidationError
from codey_estimator.money import round_half_up

AUTO_CONFIRM_MIN_BP: Final[int] = 9000
PROPOSE_MIN_BP: Final[int] = 6000
SUBTYPE_MISMATCH_CAP_BP: Final[int] = 7000
IDENTITY_CONFIDENCE_BP: Final[int] = 10000

_UPC_RE: Final[re.Pattern[str]] = re.compile(r"[0-9]+")
_MODEL_STRIP_RE: Final[re.Pattern[str]] = re.compile(r"[^A-Z0-9]")


class MatchStatus(StrEnum):
    AUTO_CONFIRMED = "auto_confirmed"
    PROPOSED = "proposed"
    NO_MATCH = "no_match"


class MatchMethod(StrEnum):
    UPC = "upc"
    MODEL_NUMBER = "model_number"
    ATTRIBUTES = "attributes"


@dataclass(frozen=True, slots=True)
class MatchTarget:
    attributes: NormalizedAttributes
    known_upcs: frozenset[str] = field(default_factory=frozenset)
    known_models: frozenset[tuple[str, str]] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class MatchCandidate:
    attributes: NormalizedAttributes
    upc: str | None = None
    model_number: str | None = None


@dataclass(frozen=True, slots=True)
class MatchResult:
    confidence_bp: int
    status: MatchStatus
    method: MatchMethod
    matching: tuple[Attr, ...]
    conflicting: tuple[Attr, ...]
    differing: tuple[Attr, ...]
    missing: tuple[Attr, ...]
    subtype_capped: bool


def normalize_upc(raw: str | None) -> str | None:
    if raw is None:
        return None
    cleaned = raw.replace(" ", "").replace("-", "")
    if not cleaned or not _UPC_RE.fullmatch(cleaned):
        return None
    if len(cleaned) not in (12, 13, 14):
        return None
    return cleaned.zfill(14)


def normalize_model_number(raw: str | None) -> str | None:
    if raw is None:
        return None
    filtered = _MODEL_STRIP_RE.sub("", raw.upper())
    return filtered if filtered else None


def classify(confidence_bp: int, has_conflict: bool) -> MatchStatus:
    if isinstance(confidence_bp, bool) or not isinstance(confidence_bp, int):
        raise ValueError(f"confidence_bp must be an int, got {confidence_bp!r}")
    if not 0 <= confidence_bp <= 10000:
        raise ValueError(f"confidence_bp out of range: {confidence_bp!r}")
    if not isinstance(has_conflict, bool):
        raise ValueError(f"has_conflict must be a bool, got {has_conflict!r}")
    if has_conflict:
        return MatchStatus.NO_MATCH
    if confidence_bp >= AUTO_CONFIRM_MIN_BP:
        return MatchStatus.AUTO_CONFIRMED
    if confidence_bp >= PROPOSE_MIN_BP:
        return MatchStatus.PROPOSED
    return MatchStatus.NO_MATCH


def _find_identity_method(
    target: MatchTarget, candidate: MatchCandidate
) -> MatchMethod | None:
    norm_upc = normalize_upc(candidate.upc)
    if norm_upc is not None:
        known_upcs = {normalize_upc(u) for u in target.known_upcs}
        known_upcs.discard(None)
        if norm_upc in known_upcs:
            return MatchMethod.UPC

    c_brand = candidate.attributes.get(Attr.BRAND)
    norm_model = normalize_model_number(candidate.model_number)
    if isinstance(c_brand, str) and norm_model is not None:
        known_models = {
            (normalize_brand(b), normalize_model_number(m)) for b, m in target.known_models
        }
        if (c_brand, norm_model) in known_models:
            return MatchMethod.MODEL_NUMBER
    return None


def match(target: MatchTarget, candidate: MatchCandidate) -> MatchResult:
    t_attrs = target.attributes
    c_attrs = candidate.attributes
    if t_attrs.category != c_attrs.category:
        raise CatalogValidationError(
            "CATEGORY_MISMATCH",
            f"target category {t_attrs.category} != candidate category {c_attrs.category}",
        )
    schema = get_schema(t_attrs.category)
    for attr in schema.required:
        if t_attrs.get(attr) is None:
            raise CatalogValidationError(
                "MISSING_REQUIRED_ATTRIBUTE",
                f"target is missing required attribute: {attr}",
                attr=attr.value,
            )

    matching: list[Attr] = []
    conflicting: list[Attr] = []
    differing: list[Attr] = []
    missing: list[Attr] = []
    possible = 0
    earned = 0
    penalty = 0

    for spec in schema.specs:
        t_val = t_attrs.get(spec.attr)
        c_val = c_attrs.get(spec.attr)
        if spec.role is AttrRole.INFO:
            if t_val is not None and c_val is not None:
                if t_val == c_val:
                    matching.append(spec.attr)
                else:
                    differing.append(spec.attr)
            continue
        if spec.role is AttrRole.REQUIRED:
            possible += spec.weight
            if c_val is None:
                missing.append(spec.attr)
            elif c_val == t_val:
                matching.append(spec.attr)
                earned += spec.weight
            else:
                conflicting.append(spec.attr)
        else:
            if t_val is None:
                continue
            possible += spec.weight
            if c_val is None:
                missing.append(spec.attr)
            elif c_val == t_val:
                matching.append(spec.attr)
                earned += spec.weight
            else:
                differing.append(spec.attr)
                penalty += spec.weight

    identity_method = _find_identity_method(target, candidate)
    if identity_method is not None:
        status = (
            MatchStatus.PROPOSED
            if conflicting or Attr.SUBTYPE in differing
            else MatchStatus.AUTO_CONFIRMED
        )
        return MatchResult(
            confidence_bp=IDENTITY_CONFIDENCE_BP,
            status=status,
            method=identity_method,
            matching=tuple(matching),
            conflicting=tuple(conflicting),
            differing=tuple(differing),
            missing=tuple(missing),
            subtype_capped=False,
        )

    if conflicting:
        confidence_bp = 0
    else:
        confidence_bp = round_half_up(Fraction(max(0, earned - penalty) * 10000, possible))
    subtype_capped = not conflicting and Attr.SUBTYPE in differing
    if subtype_capped:
        confidence_bp = min(confidence_bp, SUBTYPE_MISMATCH_CAP_BP)
    status = classify(confidence_bp, bool(conflicting))
    return MatchResult(
        confidence_bp=confidence_bp,
        status=status,
        method=MatchMethod.ATTRIBUTES,
        matching=tuple(matching),
        conflicting=tuple(conflicting),
        differing=tuple(differing),
        missing=tuple(missing),
        subtype_capped=subtype_capped,
    )
