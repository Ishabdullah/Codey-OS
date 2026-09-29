import hashlib
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from codey_estimator.catalog.package import PackageSource, PackageSpec, validate_package
from codey_estimator.errors import (
    CatalogValidationError,
    RetailerAdapterError,
    RetailerDataError,
    UnknownUnitError,
)
from codey_estimator.ports import ObservationSource, RetailerProductData
from codey_estimator.refresh import EpochSeconds
from codey_estimator.retailers.base import AdapterCapability, ObservedPrice, RetailerOffer
from codey_estimator.retailers.parsing import clean_text
from codey_estimator.units import normalize_unit

MANUAL_RETAILER_CODE: Final[str] = "manual"


@dataclass(frozen=True, slots=True)
class ManualEntry:
    title: str
    price_cents: int
    package_qty: Decimal | int
    package_unit: str
    brand: str | None = None
    model_number: str | None = None
    upc: str | None = None
    description: str | None = None
    retailer_sku: str | None = None
    observed_by_user_id: int | None = None


def _check_positive_int(value: object, code: str, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field} must be an int, got {type(value)!r}")
    if value <= 0:
        raise RetailerDataError(code, f"{field} must be > 0, got {value!r}", field=field)


def _derive_sku(title: str, qty: Decimal, unit: str) -> str:
    key = (
        " ".join(title.casefold().split())
        + "\x1f"
        + format(qty.normalize(), "f")
        + "\x1f"
        + unit
    )
    return "m-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


class ManualAdapter:
    @property
    def retailer_code(self) -> str:
        return MANUAL_RETAILER_CODE

    @property
    def source(self) -> ObservationSource:
        return ObservationSource.MANUAL

    @property
    def capabilities(self) -> frozenset[AdapterCapability]:
        return frozenset()

    def search(self, query: str) -> tuple[RetailerOffer, ...]:
        raise RetailerAdapterError("UNSUPPORTED_OPERATION", "manual adapter cannot search")

    def fetch_current_price(
        self, retailer_sku: str, *, store_code: str | None = None
    ) -> RetailerOffer | None:
        raise RetailerAdapterError(
            "UNSUPPORTED_OPERATION", "manual adapter cannot fetch a current price"
        )

    def enter(self, entry: ManualEntry, *, observed_at: EpochSeconds) -> RetailerOffer:
        if isinstance(observed_at, bool) or not isinstance(observed_at, int):
            raise TypeError(f"observed_at must be an int, got {type(observed_at)!r}")
        if observed_at < 0:
            raise RetailerDataError(
                "INVALID_OBSERVED_AT", "observed_at must be >= 0", field="observed_at"
            )

        if not isinstance(entry.title, str):
            raise TypeError(f"title must be a str, got {type(entry.title)!r}")
        if clean_text(entry.title) is None:
            raise RetailerDataError(
                "MISSING_REQUIRED_VALUE", "title is required", field="title"
            )
        title = entry.title.strip()

        if isinstance(entry.price_cents, bool) or not isinstance(entry.price_cents, int):
            raise TypeError(f"price_cents must be an int, got {type(entry.price_cents)!r}")
        if entry.price_cents <= 0:
            raise RetailerDataError(
                "INVALID_PRICE", "price_cents must be > 0", field="price_cents"
            )

        if isinstance(entry.package_qty, bool) or not isinstance(
            entry.package_qty, (Decimal, int)
        ):
            raise TypeError(
                f"package_qty must be a Decimal or int, got {type(entry.package_qty)!r}"
            )
        qty = (
            Decimal(entry.package_qty)
            if isinstance(entry.package_qty, int)
            else entry.package_qty
        )

        try:
            unit = normalize_unit(entry.package_unit)
        except UnknownUnitError as exc:
            raise RetailerDataError(
                "INVALID_PACKAGE_UNIT",
                f"unknown package_unit: {entry.package_unit!r}",
                field="package_unit",
            ) from exc

        try:
            validate_package(
                PackageSpec(qty, unit, PackageSource.MANUAL_ENTRY), retailer_linked=False
            )
        except CatalogValidationError as exc:
            field = "package_qty" if exc.code == "INVALID_PACKAGE_QTY" else "package_unit"
            raise RetailerDataError(exc.code, str(exc), field=field) from exc

        brand = clean_text(entry.brand)
        model_number = clean_text(entry.model_number)
        upc = clean_text(entry.upc)
        description = clean_text(entry.description)

        if entry.retailer_sku is not None:
            retailer_sku = clean_text(entry.retailer_sku)
            if retailer_sku is None:
                raise RetailerDataError(
                    "MISSING_REQUIRED_VALUE",
                    "retailer_sku is required",
                    field="retailer_sku",
                )
        else:
            retailer_sku = _derive_sku(title, qty, unit)

        if entry.observed_by_user_id is not None:
            _check_positive_int(
                entry.observed_by_user_id, "INVALID_USER_ID", "observed_by_user_id"
            )

        product = RetailerProductData(
            retailer_code=MANUAL_RETAILER_CODE,
            retailer_sku=retailer_sku,
            title=title,
            upc=upc,
            model_number=model_number,
            brand=brand,
            description=description,
            package_qty=qty,
            package_unit=unit,
        )
        price = ObservedPrice(
            price_cents=entry.price_cents,
            observed_at=observed_at,
            source=ObservationSource.MANUAL,
            observed_by_user_id=entry.observed_by_user_id,
        )
        return RetailerOffer(product=product, price=price)
