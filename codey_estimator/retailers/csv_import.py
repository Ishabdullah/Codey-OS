import csv
import hashlib
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from codey_estimator.errors import CsvImportError, RetailerAdapterError, RetailerDataError
from codey_estimator.ports import ObservationSource, RetailerProductData
from codey_estimator.refresh import EpochSeconds
from codey_estimator.retailers.base import AdapterCapability, ObservedPrice, RetailerOffer
from codey_estimator.retailers.parsing import (
    CsvDateFormat,
    clean_text,
    parse_date,
    parse_package_cells,
    parse_package_text,
    parse_price_cents,
)

_RETAILER_CODE_RE = re.compile(r"[a-z0-9][a-z0-9_:.\-]*")
_LINE_SPLIT_RE = re.compile(r"[^\r\n]*(?:\r\n|\r|\n)|[^\r\n]+\Z")

_MAPPING_FIELD_ORDER: Final[tuple[str, ...]] = (
    "sku_column",
    "title_column",
    "price_column",
    "upc_column",
    "model_number_column",
    "brand_column",
    "description_column",
    "category_path_column",
    "store_column",
    "date_column",
    "package_qty_column",
    "package_unit_column",
    "package_column",
)


@dataclass(frozen=True, slots=True)
class CsvColumnMapping:
    sku_column: str
    title_column: str
    price_column: str
    upc_column: str | None = None
    model_number_column: str | None = None
    brand_column: str | None = None
    description_column: str | None = None
    category_path_column: str | None = None
    store_column: str | None = None
    date_column: str | None = None
    package_qty_column: str | None = None
    package_unit_column: str | None = None
    package_column: str | None = None
    date_format: CsvDateFormat = CsvDateFormat.ISO
    utc_offset_seconds: int = 0
    default_store_code: str | None = None
    delimiter: str = ","

    def __post_init__(self) -> None:
        for name in _MAPPING_FIELD_ORDER:
            value = getattr(self, name)
            if value is None:
                continue
            if not isinstance(value, str):
                raise TypeError(f"{name} must be a str, got {type(value)!r}")
            if not value.strip():
                raise CsvImportError("INVALID_MAPPING", f"{name} must not be blank")

        if self.package_column is not None and (
            self.package_qty_column is not None or self.package_unit_column is not None
        ):
            raise CsvImportError(
                "INVALID_MAPPING",
                "package_column cannot be combined with package_qty_column/package_unit_column",
            )
        if self.package_qty_column is not None and self.package_unit_column is None:
            raise CsvImportError(
                "INVALID_MAPPING", "package_qty_column requires package_unit_column"
            )

        if not isinstance(self.date_format, CsvDateFormat):
            raise TypeError(f"date_format must be a CsvDateFormat, got {type(self.date_format)!r}")

        if isinstance(self.utc_offset_seconds, bool) or not isinstance(
            self.utc_offset_seconds, int
        ):
            raise TypeError(
                f"utc_offset_seconds must be an int, got {type(self.utc_offset_seconds)!r}"
            )
        if abs(self.utc_offset_seconds) > 86_400:
            raise CsvImportError(
                "INVALID_MAPPING", "utc_offset_seconds must be within +/- 86400"
            )

        if not isinstance(self.delimiter, str):
            raise TypeError(f"delimiter must be a str, got {type(self.delimiter)!r}")
        if len(self.delimiter) != 1 or self.delimiter in ('"', "\r", "\n"):
            raise CsvImportError("INVALID_MAPPING", f"invalid delimiter: {self.delimiter!r}")

        if self.default_store_code is not None:
            if not isinstance(self.default_store_code, str):
                raise TypeError(
                    f"default_store_code must be a str, got {type(self.default_store_code)!r}"
                )
            if not self.default_store_code.strip():
                raise CsvImportError("INVALID_MAPPING", "default_store_code must not be blank")


@dataclass(frozen=True, slots=True)
class CsvRowError:
    row_number: int
    code: str
    message: str
    column: str | None


@dataclass(frozen=True, slots=True)
class CsvObservation:
    row_number: int
    retailer_sku: str
    price: ObservedPrice


@dataclass(frozen=True, slots=True)
class CsvImportResult:
    products: tuple[RetailerProductData, ...]
    observations: tuple[CsvObservation, ...]
    errors: tuple[CsvRowError, ...]
    duplicate_rows: tuple[int, ...]
    data_rows: int


def _is_blank_record(record: list[str]) -> bool:
    return not record or all(not cell.strip() for cell in record)


def _check_positive_int(value: object, code: str, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an int, got {type(value)!r}")
    if value <= 0:
        raise RetailerDataError(code, f"{field} must be > 0, got {value!r}", field=field)


class CsvImportAdapter:
    def __init__(self, retailer_code: str, mapping: CsvColumnMapping) -> None:
        if not isinstance(retailer_code, str):
            raise TypeError(f"retailer_code must be a str, got {type(retailer_code)!r}")
        if retailer_code == "manual" or not _RETAILER_CODE_RE.fullmatch(retailer_code):
            raise RetailerDataError(
                "INVALID_RETAILER_CODE",
                f"invalid retailer_code: {retailer_code!r}",
                field="retailer_code",
            )
        if not isinstance(mapping, CsvColumnMapping):
            raise TypeError(f"mapping must be a CsvColumnMapping, got {type(mapping)!r}")
        self._retailer_code = retailer_code
        self._mapping = mapping

    @property
    def retailer_code(self) -> str:
        return self._retailer_code

    @property
    def mapping(self) -> CsvColumnMapping:
        return self._mapping

    @property
    def source(self) -> ObservationSource:
        return ObservationSource.CSV

    @property
    def capabilities(self) -> frozenset[AdapterCapability]:
        return frozenset()

    def search(self, query: str) -> tuple[RetailerOffer, ...]:
        raise RetailerAdapterError("UNSUPPORTED_OPERATION", "csv adapter cannot search")

    def fetch_current_price(
        self, retailer_sku: str, *, store_code: str | None = None
    ) -> RetailerOffer | None:
        raise RetailerAdapterError(
            "UNSUPPORTED_OPERATION", "csv adapter cannot fetch a current price"
        )

    def import_text(
        self,
        text: str,
        *,
        imported_at: EpochSeconds,
        imported_by_user_id: int | None = None,
    ) -> CsvImportResult:
        if not isinstance(text, str):
            raise TypeError(f"text must be a str, got {type(text)!r}")
        if isinstance(imported_at, bool) or not isinstance(imported_at, int):
            raise TypeError(f"imported_at must be an int, got {type(imported_at)!r}")
        if imported_at < 0:
            raise RetailerDataError(
                "INVALID_OBSERVED_AT", "imported_at must be >= 0", field="imported_at"
            )
        if imported_by_user_id is not None:
            _check_positive_int(
                imported_by_user_id, "INVALID_USER_ID", "imported_by_user_id"
            )

        if text.startswith("﻿"):
            text = text[1:]

        lines = _LINE_SPLIT_RE.findall(text)
        reader = csv.reader(lines, delimiter=self._mapping.delimiter, strict=True)

        records: list[list[str]] = []
        try:
            for record in reader:
                records.append(record)
        except csv.Error as exc:
            raise CsvImportError(
                "MALFORMED_CSV", str(exc), row_number=len(records) + 1
            ) from exc

        header_idx = None
        for i, record in enumerate(records):
            if not _is_blank_record(record):
                header_idx = i
                break
        if header_idx is None:
            raise CsvImportError("EMPTY_FILE", "the file has no header row")

        header_record = [cell.strip() for cell in records[header_idx]]
        header_norm = [cell.casefold() for cell in header_record]

        mapping = self._mapping
        missing: list[str] = []
        ambiguous: str | None = None
        field_index: dict[str, int] = {}
        field_header_text: dict[str, str] = {}
        for name in _MAPPING_FIELD_ORDER:
            original = getattr(mapping, name)
            if original is None:
                continue
            norm_name = original.strip().casefold()
            indices = [i for i, h in enumerate(header_norm) if h == norm_name]
            if not indices:
                missing.append(original)
                continue
            if len(indices) > 1:
                if ambiguous is None:
                    ambiguous = original
                continue
            field_index[name] = indices[0]
            field_header_text[name] = header_record[indices[0]]

        if missing:
            raise CsvImportError(
                "MISSING_COLUMN", "mapped column(s) not found in header", columns=tuple(missing)
            )
        if ambiguous is not None:
            raise CsvImportError(
                "AMBIGUOUS_COLUMN",
                f"mapped column matches multiple header cells: {ambiguous!r}",
                columns=(ambiguous,),
            )

        expected_len = len(header_record)

        products_by_sku: dict[str, RetailerProductData] = {}
        products_order: list[RetailerProductData] = []
        observations: list[CsvObservation] = []
        errors: list[CsvRowError] = []
        duplicate_rows: list[int] = []
        seen_keys: set[tuple[str, str | None, int, int]] = set()
        data_rows = 0

        for idx in range(header_idx + 1, len(records)):
            record = records[idx]
            if _is_blank_record(record):
                continue
            row_number = idx + 1
            data_rows += 1

            try:
                if len(record) < expected_len or (
                    len(record) > expected_len
                    and any(cell.strip() for cell in record[expected_len:])
                ):
                    raise RetailerDataError(
                        "ROW_LENGTH_MISMATCH",
                        f"row has {len(record)} cells, expected {expected_len}",
                        field=None,
                    )

                sku = clean_text(record[field_index["sku_column"]])
                if sku is None:
                    raise RetailerDataError(
                        "MISSING_REQUIRED_VALUE",
                        "sku is required",
                        field=field_header_text["sku_column"],
                    )

                title = clean_text(record[field_index["title_column"]])
                if title is None:
                    raise RetailerDataError(
                        "MISSING_REQUIRED_VALUE",
                        "title is required",
                        field=field_header_text["title_column"],
                    )

                price_cents = parse_price_cents(
                    record[field_index["price_column"]], field=field_header_text["price_column"]
                )

                if "package_qty_column" in field_index or "package_unit_column" in field_index:
                    qty_idx = field_index.get("package_qty_column")
                    unit_idx = field_index.get("package_unit_column")
                    qty_text = record[qty_idx] if qty_idx is not None else ""
                    unit_text = record[unit_idx] if unit_idx is not None else ""
                    qty_field = field_header_text.get(
                        "package_qty_column", field_header_text.get("package_unit_column", "")
                    )
                    unit_field = field_header_text.get(
                        "package_unit_column", field_header_text.get("package_qty_column", "")
                    )
                    package_qty, package_unit = parse_package_cells(
                        qty_text, unit_text, qty_field=qty_field, unit_field=unit_field
                    )
                elif "package_column" in field_index:
                    package_qty, package_unit = parse_package_text(
                        record[field_index["package_column"]],
                        field=field_header_text["package_column"],
                    )
                else:
                    package_qty, package_unit = Decimal(1), None

                if "date_column" in field_index:
                    date_field = field_header_text["date_column"]
                    observed_at = parse_date(
                        record[field_index["date_column"]],
                        mapping.date_format,
                        mapping.utc_offset_seconds,
                        field=date_field,
                    )
                    if observed_at > imported_at:
                        raise RetailerDataError(
                            "DATE_AFTER_IMPORT",
                            "date is after the import time",
                            field=date_field,
                        )
                else:
                    observed_at = imported_at

                if "store_column" in field_index:
                    store_code = clean_text(record[field_index["store_column"]])
                    if store_code is None:
                        store_code = clean_text(mapping.default_store_code)
                else:
                    store_code = clean_text(mapping.default_store_code)

                existing = products_by_sku.get(sku)
                if existing is not None and (
                    existing.package_qty != package_qty or existing.package_unit != package_unit
                ):
                    if "package_qty_column" in field_index or "package_unit_column" in field_index:
                        if existing.package_qty != package_qty:
                            conflict_field = field_header_text.get("package_qty_column")
                        else:
                            conflict_field = field_header_text.get("package_unit_column")
                    elif "package_column" in field_index:
                        conflict_field = field_header_text["package_column"]
                    else:
                        conflict_field = None
                    raise RetailerDataError(
                        "CONFLICTING_PACKAGE",
                        f"sku {sku!r} already has a different package size",
                        field=conflict_field,
                    )

            except RetailerDataError as exc:
                errors.append(CsvRowError(row_number, exc.code, str(exc), exc.field))
                continue

            key = (sku, store_code, observed_at, price_cents)
            if key in seen_keys:
                duplicate_rows.append(row_number)
                continue
            seen_keys.add(key)

            if sku not in products_by_sku:
                product = RetailerProductData(
                    retailer_code=self._retailer_code,
                    retailer_sku=sku,
                    title=title,
                    upc=clean_text(record[field_index["upc_column"]])
                    if "upc_column" in field_index
                    else None,
                    model_number=clean_text(record[field_index["model_number_column"]])
                    if "model_number_column" in field_index
                    else None,
                    brand=clean_text(record[field_index["brand_column"]])
                    if "brand_column" in field_index
                    else None,
                    description=clean_text(record[field_index["description_column"]])
                    if "description_column" in field_index
                    else None,
                    category_path=clean_text(record[field_index["category_path_column"]])
                    if "category_path_column" in field_index
                    else None,
                    package_qty=package_qty,
                    package_unit=package_unit,
                )
                products_by_sku[sku] = product
                products_order.append(product)

            raw_hash = hashlib.sha256("\x1f".join(record).encode("utf-8")).hexdigest()
            observations.append(
                CsvObservation(
                    row_number=row_number,
                    retailer_sku=sku,
                    price=ObservedPrice(
                        price_cents=price_cents,
                        observed_at=observed_at,
                        source=ObservationSource.CSV,
                        store_code=store_code,
                        observed_by_user_id=imported_by_user_id,
                        raw_hash=raw_hash,
                    ),
                )
            )

        return CsvImportResult(
            products=tuple(products_order),
            observations=tuple(observations),
            errors=tuple(errors),
            duplicate_rows=tuple(duplicate_rows),
            data_rows=data_rows,
        )
