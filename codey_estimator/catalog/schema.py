import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from typing import Final, TypeAlias

from codey_estimator.catalog.text import format_measure_value
from codey_estimator.errors import CatalogValidationError, UnknownCategoryError, UnknownUnitError
from codey_estimator.units import UNITS, convert_quantity

_BRAND_STRIP_RE: Final[re.Pattern[str]] = re.compile(r"[^A-Z0-9]")


class Category(StrEnum):
    PLUMBING_PIPE = "plumbing_pipe"
    DRYWALL_SHEET = "drywall_sheet"
    LUMBER = "lumber"
    FASTENER = "fastener"
    PAINT = "paint"


class Attr(StrEnum):
    MATERIAL = "material"
    SUBTYPE = "subtype"
    PRODUCT_TYPE = "product_type"
    NOMINAL_SIZE = "nominal_size"
    DIMENSION = "dimension"
    THICKNESS = "thickness"
    WIDTH = "width"
    LENGTH = "length"
    GAUGE = "gauge"
    TREATMENT = "treatment"
    FINISH = "finish"
    VOLUME = "volume"
    COLOR = "color"
    PACKAGE_COUNT = "package_count"
    BRAND = "brand"


class AttrKind(StrEnum):
    TEXT = "text"
    MEASURE = "measure"
    COUNT = "count"


class AttrRole(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    INFO = "info"


@dataclass(frozen=True, slots=True)
class Measure:
    value: Fraction
    unit: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, Fraction):
            raise TypeError(f"Measure.value must be a Fraction, got {type(self.value)!r}")
        if self.value <= 0:
            raise CatalogValidationError("INVALID_MEASURE", "Measure.value must be > 0")
        if self.unit not in UNITS:
            raise UnknownUnitError(f"unknown unit: {self.unit!r}")

    def key_text(self) -> str:
        return format_measure_value(self.value) + self.unit.lower()


AttrValue: TypeAlias = str | int | Measure


@dataclass(frozen=True, slots=True)
class AttributeSpec:
    attr: Attr
    kind: AttrKind
    role: AttrRole
    weight: int
    unit: str | None = None
    default: str | None = None


@dataclass(frozen=True, slots=True)
class CategorySchema:
    category: Category
    specs: tuple[AttributeSpec, ...]

    def spec(self, attr: Attr) -> AttributeSpec:
        for s in self.specs:
            if s.attr == attr:
                return s
        raise CatalogValidationError(
            "ATTR_NOT_IN_SCHEMA",
            f"{attr} is not in the {self.category} schema",
            attr=attr.value,
        )

    def index(self, attr: Attr) -> int:
        for i, s in enumerate(self.specs):
            if s.attr == attr:
                return i
        raise CatalogValidationError(
            "ATTR_NOT_IN_SCHEMA",
            f"{attr} is not in the {self.category} schema",
            attr=attr.value,
        )

    @property
    def key_attrs(self) -> tuple[Attr, ...]:
        return tuple(s.attr for s in self.specs if s.role != AttrRole.INFO)

    @property
    def required(self) -> tuple[Attr, ...]:
        return tuple(s.attr for s in self.specs if s.role == AttrRole.REQUIRED)


def _s(
    attr: Attr,
    kind: AttrKind,
    role: AttrRole,
    weight: int,
    unit: str | None = None,
    default: str | None = None,
) -> AttributeSpec:
    return AttributeSpec(attr=attr, kind=kind, role=role, weight=weight, unit=unit, default=default)


CATEGORY_SCHEMAS: Final[Mapping[Category, CategorySchema]] = {
    Category.PLUMBING_PIPE: CategorySchema(
        Category.PLUMBING_PIPE,
        (
            _s(Attr.MATERIAL, AttrKind.TEXT, AttrRole.REQUIRED, 10),
            _s(Attr.SUBTYPE, AttrKind.TEXT, AttrRole.OPTIONAL, 6),
            _s(Attr.NOMINAL_SIZE, AttrKind.MEASURE, AttrRole.REQUIRED, 10, unit="IN"),
            _s(Attr.COLOR, AttrKind.TEXT, AttrRole.OPTIONAL, 3),
            _s(Attr.LENGTH, AttrKind.MEASURE, AttrRole.REQUIRED, 10, unit="FT"),
            _s(Attr.PRODUCT_TYPE, AttrKind.TEXT, AttrRole.REQUIRED, 10),
            _s(Attr.PACKAGE_COUNT, AttrKind.COUNT, AttrRole.INFO, 0),
            _s(Attr.BRAND, AttrKind.TEXT, AttrRole.INFO, 0),
        ),
    ),
    Category.DRYWALL_SHEET: CategorySchema(
        Category.DRYWALL_SHEET,
        (
            _s(Attr.SUBTYPE, AttrKind.TEXT, AttrRole.OPTIONAL, 6, default="REGULAR"),
            _s(Attr.THICKNESS, AttrKind.MEASURE, AttrRole.REQUIRED, 10, unit="IN"),
            _s(Attr.WIDTH, AttrKind.MEASURE, AttrRole.REQUIRED, 10, unit="FT"),
            _s(Attr.LENGTH, AttrKind.MEASURE, AttrRole.REQUIRED, 10, unit="FT"),
            _s(Attr.PACKAGE_COUNT, AttrKind.COUNT, AttrRole.INFO, 0),
            _s(Attr.BRAND, AttrKind.TEXT, AttrRole.INFO, 0),
        ),
    ),
    Category.LUMBER: CategorySchema(
        Category.LUMBER,
        (
            _s(Attr.DIMENSION, AttrKind.TEXT, AttrRole.REQUIRED, 10),
            _s(Attr.LENGTH, AttrKind.MEASURE, AttrRole.REQUIRED, 10, unit="FT"),
            _s(Attr.TREATMENT, AttrKind.TEXT, AttrRole.REQUIRED, 10, default="UNTREATED"),
            _s(Attr.MATERIAL, AttrKind.TEXT, AttrRole.OPTIONAL, 3),
            _s(Attr.PACKAGE_COUNT, AttrKind.COUNT, AttrRole.INFO, 0),
            _s(Attr.BRAND, AttrKind.TEXT, AttrRole.INFO, 0),
        ),
    ),
    Category.FASTENER: CategorySchema(
        Category.FASTENER,
        (
            _s(Attr.PRODUCT_TYPE, AttrKind.TEXT, AttrRole.REQUIRED, 10),
            _s(Attr.SUBTYPE, AttrKind.TEXT, AttrRole.OPTIONAL, 6),
            _s(Attr.GAUGE, AttrKind.TEXT, AttrRole.REQUIRED, 10),
            _s(Attr.LENGTH, AttrKind.MEASURE, AttrRole.REQUIRED, 10, unit="IN"),
            _s(Attr.MATERIAL, AttrKind.TEXT, AttrRole.OPTIONAL, 3),
            _s(Attr.PACKAGE_COUNT, AttrKind.COUNT, AttrRole.INFO, 0),
            _s(Attr.BRAND, AttrKind.TEXT, AttrRole.INFO, 0),
        ),
    ),
    Category.PAINT: CategorySchema(
        Category.PAINT,
        (
            _s(Attr.PRODUCT_TYPE, AttrKind.TEXT, AttrRole.REQUIRED, 10),
            _s(Attr.SUBTYPE, AttrKind.TEXT, AttrRole.OPTIONAL, 6),
            _s(Attr.FINISH, AttrKind.TEXT, AttrRole.REQUIRED, 10),
            _s(Attr.VOLUME, AttrKind.MEASURE, AttrRole.REQUIRED, 10, unit="GAL"),
            _s(Attr.COLOR, AttrKind.TEXT, AttrRole.OPTIONAL, 3),
            _s(Attr.PACKAGE_COUNT, AttrKind.COUNT, AttrRole.INFO, 0),
            _s(Attr.BRAND, AttrKind.TEXT, AttrRole.INFO, 0),
        ),
    ),
}


def get_schema(category: "Category | str") -> CategorySchema:
    if isinstance(category, Category):
        return CATEGORY_SCHEMAS[category]
    if isinstance(category, str):
        try:
            cat = Category(category)
        except ValueError as exc:
            raise UnknownCategoryError(f"unknown category: {category!r}") from exc
        return CATEGORY_SCHEMAS[cat]
    raise TypeError(f"get_schema requires a Category or str, got {type(category)!r}")


def normalize_brand(raw: str | None) -> str | None:
    if raw is None:
        return None
    filtered = _BRAND_STRIP_RE.sub("", raw.upper())
    return filtered if filtered else None


_UPPER_ATTRS: Final[frozenset[Attr]] = frozenset({Attr.MATERIAL, Attr.SUBTYPE, Attr.TREATMENT})
_FORBIDDEN_CHARS: Final[frozenset[str]] = frozenset({"|", ":", "*"})


def _canonicalize_text(spec: AttributeSpec, raw: object) -> str:
    if not isinstance(raw, str):
        raise CatalogValidationError(
            "INVALID_ATTRIBUTE_VALUE",
            f"{spec.attr} expects a str, got {type(raw)!r}",
            attr=spec.attr.value,
        )
    s = raw.strip()
    if not s or any(ch in s for ch in _FORBIDDEN_CHARS):
        raise CatalogValidationError(
            "INVALID_ATTRIBUTE_VALUE",
            f"{spec.attr} has an invalid text value: {raw!r}",
            attr=spec.attr.value,
        )
    if spec.attr is Attr.BRAND:
        brand = normalize_brand(s)
        if brand is None:
            raise CatalogValidationError(
                "INVALID_ATTRIBUTE_VALUE",
                f"brand normalizes to empty: {raw!r}",
                attr=spec.attr.value,
            )
        return brand
    if spec.attr in _UPPER_ATTRS:
        return s.upper()
    return s.lower()


def _canonicalize_count(spec: AttributeSpec, raw: object) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise CatalogValidationError(
            "INVALID_ATTRIBUTE_VALUE",
            f"{spec.attr} expects an int >= 1, got {raw!r}",
            attr=spec.attr.value,
        )
    return raw


def _canonicalize_measure(spec: AttributeSpec, raw: object) -> Measure:
    if not isinstance(raw, Measure):
        raise CatalogValidationError(
            "INVALID_ATTRIBUTE_VALUE",
            f"{spec.attr} expects a Measure, got {type(raw)!r}",
            attr=spec.attr.value,
        )
    assert spec.unit is not None
    converted = convert_quantity(raw.value, raw.unit, spec.unit)
    return Measure(converted, spec.unit)


def _canonicalize(spec: AttributeSpec, raw: object) -> AttrValue:
    if spec.kind is AttrKind.TEXT:
        return _canonicalize_text(spec, raw)
    if spec.kind is AttrKind.COUNT:
        return _canonicalize_count(spec, raw)
    return _canonicalize_measure(spec, raw)


@dataclass(frozen=True, slots=True)
class NormalizedAttributes:
    category: Category
    values: tuple[tuple[Attr, AttrValue], ...]

    def __post_init__(self) -> None:
        schema = get_schema(self.category)
        seen: set[Attr] = set()
        last_index = -1
        for attr, value in self.values:
            spec = schema.spec(attr)
            if attr in seen:
                raise CatalogValidationError(
                    "DUPLICATE_ATTRIBUTE", f"duplicate attribute: {attr}", attr=attr.value
                )
            seen.add(attr)
            idx = schema.index(attr)
            if idx <= last_index:
                raise CatalogValidationError(
                    "ATTRIBUTE_ORDER", f"attribute out of schema order: {attr}", attr=attr.value
                )
            last_index = idx
            _check_kind(spec, value)

    def get(self, attr: Attr) -> AttrValue | None:
        for a, v in self.values:
            if a == attr:
                return v
        return None

    def as_dict(self) -> dict[Attr, AttrValue]:
        return dict(self.values)


def _check_kind(spec: AttributeSpec, value: AttrValue) -> None:
    if spec.kind is AttrKind.TEXT:
        if not isinstance(value, str) or not value:
            raise CatalogValidationError(
                "INVALID_ATTRIBUTE_VALUE",
                f"{spec.attr} expects a non-empty str, got {value!r}",
                attr=spec.attr.value,
            )
    elif spec.kind is AttrKind.COUNT:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise CatalogValidationError(
                "INVALID_ATTRIBUTE_VALUE",
                f"{spec.attr} expects an int >= 1, got {value!r}",
                attr=spec.attr.value,
            )
    else:
        if not isinstance(value, Measure) or value.unit != spec.unit:
            raise CatalogValidationError(
                "INVALID_ATTRIBUTE_VALUE",
                f"{spec.attr} expects a Measure in {spec.unit}, got {value!r}",
                attr=spec.attr.value,
            )


def make_attributes(
    category: "Category | str", values: Mapping[Attr, AttrValue]
) -> NormalizedAttributes:
    schema = get_schema(category)
    canon: dict[Attr, AttrValue] = {}
    for attr, raw in values.items():
        spec = schema.spec(attr)
        canon[attr] = _canonicalize(spec, raw)
    ordered = tuple((s.attr, canon[s.attr]) for s in schema.specs if s.attr in canon)
    return NormalizedAttributes(category=schema.category, values=ordered)
