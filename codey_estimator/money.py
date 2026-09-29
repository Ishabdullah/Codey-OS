import math
import re
from collections.abc import Sequence
from decimal import Decimal
from fractions import Fraction
from typing import Final, TypeAlias

Cents: TypeAlias = int
BP_DENOMINATOR: Final[int] = 10_000

_DOLLARS_RE = re.compile(r"^-?\d+(\.\d{1,2})?$")


def _check_cents(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int cents value, got {type(value)!r}")


def round_half_up(value: Fraction | Decimal | int) -> int:
    if isinstance(value, bool):
        raise TypeError("round_half_up does not accept bool")
    if isinstance(value, float):
        raise TypeError("round_half_up does not accept float")
    if isinstance(value, (int, Decimal)):
        frac = Fraction(value)
    elif isinstance(value, Fraction):
        frac = value
    else:
        raise TypeError(f"round_half_up does not accept {type(value)!r}")
    if frac >= 0:
        return math.floor(frac + Fraction(1, 2))
    return -math.floor(-frac + Fraction(1, 2))


def apply_markup(cost_cents: int, markup_bp: int) -> int:
    _check_cents(cost_cents, "cost_cents")
    _check_cents(markup_bp, "markup_bp")
    if cost_cents < 0 or markup_bp < 0:
        raise ValueError("apply_markup requires non-negative cost_cents and markup_bp")
    return round_half_up(Fraction(cost_cents * (10_000 + markup_bp), 10_000))


def percent_of(amount_cents: int, bp: int) -> int:
    _check_cents(amount_cents, "amount_cents")
    _check_cents(bp, "bp")
    if amount_cents < 0 or bp < 0:
        raise ValueError("percent_of requires non-negative amount_cents and bp")
    return round_half_up(Fraction(amount_cents * bp, 10_000))


def ratio_bp(numerator: int, denominator: int) -> int:
    _check_cents(numerator, "numerator")
    _check_cents(denominator, "denominator")
    if denominator == 0:
        raise ZeroDivisionError("ratio_bp denominator is zero")
    return round_half_up(Fraction(numerator * 10_000, denominator))


def allocate_pro_rata(total_cents: int, weights: Sequence[int]) -> list[int]:
    _check_cents(total_cents, "total_cents")
    for w in weights:
        _check_cents(w, "weight")
    if total_cents < 0:
        raise ValueError("allocate_pro_rata requires non-negative total_cents")
    for w in weights:
        if w < 0:
            raise ValueError("allocate_pro_rata requires non-negative weights")

    n = len(weights)
    if n == 0:
        if total_cents == 0:
            return []
        raise ValueError("allocate_pro_rata: no weights to allocate a non-zero total to")

    total_weight = sum(weights)
    if total_weight == 0:
        if total_cents == 0:
            return [0] * n
        raise ValueError("allocate_pro_rata: all weights are zero but total_cents is non-zero")

    base = [total_cents * w // total_weight for w in weights]
    rem = [total_cents * w % total_weight for w in weights]
    leftover = total_cents - sum(base)

    order = sorted(range(n), key=lambda i: (-rem[i], i))
    result = list(base)
    for i in order[:leftover]:
        result[i] += 1
    return result


def parse_dollars(text: str) -> int:
    if not isinstance(text, str):
        raise TypeError("parse_dollars requires a str")
    s = text.strip()
    if not _DOLLARS_RE.match(s):
        raise ValueError(f"invalid dollar string: {text!r}")
    negative = s.startswith("-")
    if negative:
        s = s[1:]
    if "." in s:
        whole, frac = s.split(".")
        frac = (frac + "00")[:2]
    else:
        whole, frac = s, "00"
    cents = int(whole) * 100 + int(frac)
    return -cents if negative else cents


def format_cents(cents: int) -> str:
    _check_cents(cents, "cents")
    negative = cents < 0
    magnitude = abs(cents)
    dollars, remainder = divmod(magnitude, 100)
    formatted = f"${dollars:,}.{remainder:02d}"
    return f"-{formatted}" if negative else formatted
