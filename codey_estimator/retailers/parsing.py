import re
from decimal import Decimal
from enum import StrEnum

from codey_estimator import money
from codey_estimator.catalog.package import PackageSource, PackageSpec, validate_package
from codey_estimator.errors import CatalogValidationError, RetailerDataError, UnknownUnitError
from codey_estimator.refresh import EpochSeconds
from codey_estimator.units import normalize_unit


class CsvDateFormat(StrEnum):
    ISO = "iso"
    US = "us"


_COMMA_PRICE_RE = re.compile(r"\d{1,3}(,\d{3})+(\.\d{1,2})?")
_QTY_RE = re.compile(r"\d{1,3}(,\d{3})+(\.\d+)?|\d+(\.\d+)?")
_LEADING_QTY_RE = re.compile(r"^(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)")
_UNIT_TEXT_RE = re.compile(r"[A-Za-z][A-Za-z ]*\.?")

_ISO_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_US_DATE_RE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")

_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"clean_text requires a str or None, got {type(value)!r}")
    stripped = value.strip()
    return stripped if stripped else None


def parse_price_cents(text: str, *, field: str) -> int:
    s = text.strip()
    if not s:
        raise RetailerDataError(
            "MISSING_REQUIRED_VALUE", f"{field} is required", field=field
        )
    if s.startswith("-"):
        raise RetailerDataError("INVALID_PRICE", f"invalid price: {text!r}", field=field)
    if s.startswith("$"):
        s = s[1:].strip()
    if _COMMA_PRICE_RE.fullmatch(s):
        s = s.replace(",", "")
    try:
        cents = money.parse_dollars(s)
    except ValueError as exc:
        raise RetailerDataError(
            "INVALID_PRICE", f"invalid price: {text!r}", field=field
        ) from exc
    if cents <= 0:
        raise RetailerDataError("INVALID_PRICE", f"invalid price: {text!r}", field=field)
    return cents


def _clean_unit_text(unit_text: str) -> str:
    u = unit_text.strip()
    if u.endswith("."):
        u = u[:-1]
    u = re.sub(r"\s+", " ", u).strip()
    return u


def _finalize_package(
    qty_text: str, unit_text: str, *, qty_field: str, unit_field: str
) -> tuple[Decimal, str | None]:
    unit_clean = _clean_unit_text(unit_text)
    qty_clean = qty_text.strip()

    if not qty_clean and not unit_clean:
        return (Decimal(1), None)
    if qty_clean and not unit_clean:
        raise RetailerDataError(
            "PACKAGE_UNIT_MISSING",
            "package unit is required when a package quantity is given",
            field=unit_field,
        )
    if qty_clean:
        if not _QTY_RE.fullmatch(qty_clean):
            raise RetailerDataError(
                "INVALID_PACKAGE_QTY",
                f"invalid package quantity: {qty_clean!r}",
                field=qty_field,
            )
        qty = Decimal(qty_clean.replace(",", ""))
    else:
        qty = Decimal(1)

    try:
        unit = normalize_unit(unit_clean)
    except UnknownUnitError as exc:
        raise RetailerDataError(
            "INVALID_PACKAGE_UNIT",
            f"unknown package unit: {unit_clean!r}",
            field=unit_field,
        ) from exc

    try:
        validate_package(
            PackageSpec(qty, unit, PackageSource.RETAILER_LISTING), retailer_linked=True
        )
    except CatalogValidationError as exc:
        error_field = qty_field if exc.code == "INVALID_PACKAGE_QTY" else unit_field
        raise RetailerDataError(exc.code, str(exc), field=error_field) from exc

    return (qty, unit)


def parse_package_cells(
    qty_text: str, unit_text: str, *, qty_field: str, unit_field: str
) -> tuple[Decimal, str | None]:
    return _finalize_package(qty_text, unit_text, qty_field=qty_field, unit_field=unit_field)


def parse_package_text(text: str, *, field: str) -> tuple[Decimal, str | None]:
    s = text.strip()
    if not s:
        return (Decimal(1), None)

    m = _LEADING_QTY_RE.match(s)
    if m:
        qty_str = m.group(1)
        rest = s[m.end() :].strip()
    else:
        qty_str = ""
        rest = s

    if rest and not _UNIT_TEXT_RE.fullmatch(rest):
        first = rest[0]
        if not ("A" <= first <= "Z" or "a" <= first <= "z"):
            raise RetailerDataError(
                "INVALID_PACKAGE_QTY",
                f"invalid package text: {text!r}",
                field=field,
            )
        raise RetailerDataError(
            "INVALID_PACKAGE_UNIT",
            f"invalid package unit: {rest!r}",
            field=field,
        )

    return _finalize_package(qty_str, rest, qty_field=field, unit_field=field)


def days_from_civil(year: int, month: int, day: int) -> int:
    y = year - (1 if month <= 2 else 0)
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    doy = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _is_leap_year(year: int) -> bool:
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def parse_date(
    text: str, date_format: CsvDateFormat, utc_offset_seconds: int, *, field: str
) -> EpochSeconds:
    s = text.strip()
    if not s:
        raise RetailerDataError("MISSING_REQUIRED_VALUE", f"{field} is required", field=field)

    if date_format is CsvDateFormat.ISO:
        m = _ISO_DATE_RE.fullmatch(s)
        if not m:
            raise RetailerDataError("INVALID_DATE", f"invalid date: {text!r}", field=field)
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = _US_DATE_RE.fullmatch(s)
        if not m:
            raise RetailerDataError("INVALID_DATE", f"invalid date: {text!r}", field=field)
        month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))

    if not (1 <= month <= 12):
        raise RetailerDataError("INVALID_DATE", f"invalid date: {text!r}", field=field)

    max_day = _DAYS_IN_MONTH[month - 1]
    if month == 2 and _is_leap_year(year):
        max_day = 29
    if not (1 <= day <= max_day):
        raise RetailerDataError("INVALID_DATE", f"invalid date: {text!r}", field=field)

    result = days_from_civil(year, month, day) * 86400 - utc_offset_seconds
    if result < 0:
        raise RetailerDataError("INVALID_DATE", f"invalid date: {text!r}", field=field)
    return result
