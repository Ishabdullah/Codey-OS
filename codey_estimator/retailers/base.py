from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from codey_estimator.ports import ObservationSource, PriceObservationData, RetailerProductData
from codey_estimator.refresh import EpochSeconds


class AdapterCapability(StrEnum):
    SEARCH = "search"
    FETCH_PRICE = "fetch_price"


@dataclass(frozen=True, slots=True)
class ObservedPrice:
    price_cents: int
    observed_at: EpochSeconds
    source: ObservationSource
    store_code: str | None = None
    was_price_cents: int | None = None
    unit_price_cents: int | None = None
    availability: str | None = None
    observed_by_user_id: int | None = None
    raw_hash: str | None = None

    def bind(self, retailer_product_id: int) -> PriceObservationData:
        if isinstance(retailer_product_id, bool) or not isinstance(retailer_product_id, int):
            raise TypeError(
                f"retailer_product_id must be an int, got {type(retailer_product_id)!r}"
            )
        if retailer_product_id <= 0:
            raise ValueError("retailer_product_id must be > 0")
        return PriceObservationData(
            retailer_product_id=retailer_product_id,
            price_cents=self.price_cents,
            observed_at=self.observed_at,
            source=self.source,
            store_code=self.store_code,
            was_price_cents=self.was_price_cents,
            unit_price_cents=self.unit_price_cents,
            availability=self.availability,
            observed_by_user_id=self.observed_by_user_id,
            raw_hash=self.raw_hash,
        )


@dataclass(frozen=True, slots=True)
class RetailerOffer:
    product: RetailerProductData
    price: ObservedPrice


@runtime_checkable
class RetailerAdapter(Protocol):
    @property
    def retailer_code(self) -> str: ...

    @property
    def source(self) -> ObservationSource: ...

    @property
    def capabilities(self) -> frozenset[AdapterCapability]: ...

    def search(self, query: str) -> tuple[RetailerOffer, ...]: ...

    def fetch_current_price(
        self, retailer_sku: str, *, store_code: str | None = None
    ) -> RetailerOffer | None: ...
