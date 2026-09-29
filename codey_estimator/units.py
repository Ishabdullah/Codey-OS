import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from typing import Final

from codey_estimator.errors import IncompatibleUnitsError, UnknownUnitError


class Dimension(StrEnum):
    LENGTH = "length"
    AREA = "area"
    LIQUID = "liquid"
    CUBIC = "cubic"
    COUNT = "count"
    TIME = "time"
    BOX = "box"
    ROLL = "roll"
    BAG = "bag"
    SHEET = "sheet"
    FIXTURE = "fixture"
    ROOM = "room"
    LUMP = "lump"


@dataclass(frozen=True, slots=True)
class Unit:
    code: str
    label: str
    dimension: Dimension
    factor: Fraction


UNITS: Final[Mapping[str, Unit]] = {
    "FT": Unit("FT", "ft", Dimension.LENGTH, Fraction(1)),
    "LF": Unit("LF", "LF", Dimension.LENGTH, Fraction(1)),
    "IN": Unit("IN", "in", Dimension.LENGTH, Fraction(1, 12)),
    "YD": Unit("YD", "yd", Dimension.LENGTH, Fraction(3)),
    "SF": Unit("SF", "SF", Dimension.AREA, Fraction(1)),
    "SQ": Unit("SQ", "SQ", Dimension.AREA, Fraction(100)),
    "SY": Unit("SY", "SY", Dimension.AREA, Fraction(9)),
    "GAL": Unit("GAL", "gal", Dimension.LIQUID, Fraction(1)),
    "QT": Unit("QT", "qt", Dimension.LIQUID, Fraction(1, 4)),
    "CF": Unit("CF", "CF", Dimension.CUBIC, Fraction(1)),
    "CY": Unit("CY", "CY", Dimension.CUBIC, Fraction(27)),
    "EA": Unit("EA", "ea", Dimension.COUNT, Fraction(1)),
    "HR": Unit("HR", "hr", Dimension.TIME, Fraction(1)),
    "BX": Unit("BX", "box", Dimension.BOX, Fraction(1)),
    "RL": Unit("RL", "roll", Dimension.ROLL, Fraction(1)),
    "BG": Unit("BG", "bag", Dimension.BAG, Fraction(1)),
    "SH": Unit("SH", "sheet", Dimension.SHEET, Fraction(1)),
    "FIXTURE": Unit("FIXTURE", "fixture", Dimension.FIXTURE, Fraction(1)),
    "ROOM": Unit("ROOM", "room", Dimension.ROOM, Fraction(1)),
    "LS": Unit("LS", "lump sum", Dimension.LUMP, Fraction(1)),
}

ALIASES: Final[Mapping[str, str]] = {
    "feet": "FT",
    "foot": "FT",
    "lin ft": "LF",
    "linear ft": "LF",
    "inch": "IN",
    "inches": "IN",
    "sqft": "SF",
    "sq ft": "SF",
    "square": "SQ",
    "squares": "SQ",
    "gallon": "GAL",
    "gallons": "GAL",
    "each": "EA",
    "pc": "EA",
    "pcs": "EA",
    "hour": "HR",
    "hours": "HR",
    "hrs": "HR",
    "box": "BX",
    "roll": "RL",
    "bag": "BG",
    "sheet": "SH",
    "fixtures": "FIXTURE",
    "rooms": "ROOM",
}


def normalize_unit(code: str) -> str:
    key = code.strip().lower()
    for canonical in UNITS:
        if canonical.lower() == key:
            return canonical
    if key in ALIASES:
        return ALIASES[key]
    raise UnknownUnitError(f"unknown unit: {code!r}")


def get_unit(code: str) -> Unit:
    return UNITS[normalize_unit(code)]


def convert_quantity(
    qty: Decimal | int | Fraction, from_unit: str, to_unit: str
) -> Fraction:
    if isinstance(qty, (bool, float)):
        raise TypeError("convert_quantity does not accept bool or float")
    from_u = get_unit(from_unit)
    to_u = get_unit(to_unit)
    if from_u.dimension != to_u.dimension:
        raise IncompatibleUnitsError(
            f"cannot convert {from_unit!r} to {to_unit!r}: incompatible dimensions"
        )
    q = Fraction(qty)
    if q < 0:
        raise ValueError("convert_quantity requires a non-negative qty")
    return q * from_u.factor / to_u.factor


def packages_needed(
    qty: Decimal | int | Fraction,
    qty_unit: str,
    package_qty: Decimal | int,
    package_unit: str,
) -> int:
    if isinstance(package_qty, (bool, float)):
        raise TypeError("packages_needed does not accept bool or float for package_qty")
    if package_qty <= 0:
        raise ValueError("packages_needed requires a positive package_qty")
    if qty == 0:
        return 0
    converted = convert_quantity(qty, qty_unit, package_unit)
    return math.ceil(converted / Fraction(package_qty))
