from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import StrEnum
from fractions import Fraction

from codey_estimator.catalog.schema import Attr, Category, Measure, NormalizedAttributes
from codey_estimator.errors import CatalogValidationError
from codey_estimator.units import UNITS


class PackageSource(StrEnum):
    RETAILER_LISTING = "retailer_listing"
    MANUAL_ENTRY = "manual_entry"


@dataclass(frozen=True, slots=True)
class PackageSpec:
    package_qty: Decimal
    package_unit: str
    source: PackageSource


def _fraction_to_decimal(value: Fraction) -> Decimal | None:
    remainder = value.denominator
    while remainder % 2 == 0:
        remainder //= 2
    while remainder % 5 == 0:
        remainder //= 5
    if remainder != 1:
        return None
    with localcontext() as ctx:
        ctx.prec = 60
        return Decimal(value.numerator) / Decimal(value.denominator)


def infer_package(attrs: NormalizedAttributes) -> tuple[Decimal, str] | None:
    package_count = attrs.get(Attr.PACKAGE_COUNT)
    n = package_count if isinstance(package_count, int) else 1
    category = attrs.category

    if category is Category.PLUMBING_PIPE:
        length = attrs.get(Attr.LENGTH)
        if not isinstance(length, Measure):
            return None
        dec = _fraction_to_decimal(Fraction(n) * length.value)
        return None if dec is None else (dec, "FT")

    if category is Category.DRYWALL_SHEET:
        width = attrs.get(Attr.WIDTH)
        length = attrs.get(Attr.LENGTH)
        if not isinstance(width, Measure) or not isinstance(length, Measure):
            return None
        dec = _fraction_to_decimal(Fraction(n) * width.value * length.value)
        return None if dec is None else (dec, "SF")

    if category is Category.LUMBER:
        dec = _fraction_to_decimal(Fraction(n))
        assert dec is not None
        return (dec, "EA")

    if category is Category.FASTENER:
        if not isinstance(package_count, int):
            return None
        dec = _fraction_to_decimal(Fraction(package_count))
        assert dec is not None
        return (dec, "EA")

    if category is Category.PAINT:
        volume = attrs.get(Attr.VOLUME)
        if not isinstance(volume, Measure):
            return None
        t = Fraction(n) * volume.value
        if t.denominator == 1:
            dec = _fraction_to_decimal(t)
            return None if dec is None else (dec, "GAL")
        four_t = t * 4
        if four_t.denominator == 1:
            dec = _fraction_to_decimal(four_t)
            return None if dec is None else (dec, "QT")
        dec = _fraction_to_decimal(t)
        return None if dec is None else (dec, "GAL")

    raise AssertionError(f"unhandled category: {category}")


def validate_package(spec: PackageSpec, *, retailer_linked: bool) -> None:
    qty = spec.package_qty
    if isinstance(qty, (bool, float)) or not isinstance(qty, (Decimal, int)):
        raise TypeError(f"package_qty must be a Decimal or int, got {type(qty)!r}")
    if isinstance(qty, int):
        qty = Decimal(qty)
    if not qty.is_finite() or qty < 1:
        raise CatalogValidationError(
            "INVALID_PACKAGE_QTY", f"package_qty must be finite and >= 1, got {qty!r}"
        )
    if spec.package_unit not in UNITS:
        raise CatalogValidationError(
            "INVALID_PACKAGE_UNIT", f"unknown package_unit: {spec.package_unit!r}"
        )
    if retailer_linked and spec.source is PackageSource.MANUAL_ENTRY:
        raise CatalogValidationError(
            "MANUAL_PACKAGE_ON_RETAILER_PRODUCT",
            "manual-entry package size is not allowed on a retailer-linked product",
        )
