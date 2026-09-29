from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol, runtime_checkable

from codey_estimator.refresh import EpochSeconds, RefreshStatus


class ObservationSource(StrEnum):
    ADAPTER = "adapter"
    MANUAL = "manual"
    CSV = "csv"


@dataclass(frozen=True, slots=True)
class RefreshState:
    last_checked_at: EpochSeconds | None = None
    next_refresh_at: EpochSeconds | None = None
    refresh_interval_days: int | None = None
    refresh_status: RefreshStatus = RefreshStatus.OK
    refresh_error: str | None = None
    refresh_priority: int = 0
    consecutive_failures: int = 0


@dataclass(frozen=True, slots=True)
class RetailerProductData:
    retailer_code: str
    retailer_sku: str
    title: str
    upc: str | None = None
    model_number: str | None = None
    brand: str | None = None
    description: str | None = None
    category_path: str | None = None
    attributes: tuple[tuple[str, str], ...] = ()
    package_qty: Decimal = Decimal(1)
    package_unit: str | None = None
    url: str | None = None
    availability: str | None = None


@dataclass(frozen=True, slots=True)
class RetailerProductRecord:
    id: int
    data: RetailerProductData
    current_price_cents: int | None
    current_observation_id: int | None
    refresh: RefreshState
    first_seen_at: EpochSeconds
    active: bool = True


@dataclass(frozen=True, slots=True)
class PriceObservationData:
    retailer_product_id: int
    price_cents: int
    observed_at: EpochSeconds
    source: ObservationSource
    store_code: str | None = None
    was_price_cents: int | None = None
    unit_price_cents: int | None = None
    availability: str | None = None
    observed_by_user_id: int | None = None
    raw_hash: str | None = None


@dataclass(frozen=True, slots=True)
class PriceObservationRecord:
    id: int
    data: PriceObservationData


@dataclass(frozen=True, slots=True)
class SearchCacheEntry:
    retailer_code: str
    normalized_query: str
    result_skus: tuple[str, ...]
    fetched_at: EpochSeconds


@runtime_checkable
class RetailerProductRepo(Protocol):
    def get_by_sku(
        self, retailer_code: str, retailer_sku: str
    ) -> RetailerProductRecord | None: ...

    def get_by_upc(
        self, upc: str, retailer_code: str | None = None
    ) -> tuple[RetailerProductRecord, ...]: ...

    def upsert(
        self, data: RetailerProductData, seen_at: EpochSeconds
    ) -> RetailerProductRecord: ...

    def list_needing_refresh(
        self, now: EpochSeconds, limit: int
    ) -> tuple[RetailerProductRecord, ...]: ...

    def update_refresh_state(self, product_id: int, state: RefreshState) -> None: ...


@runtime_checkable
class PriceObservationRepo(Protocol):
    def append(self, observation: PriceObservationData) -> PriceObservationRecord: ...

    def get_latest(
        self, retailer_product_id: int, store_code: str | None = None
    ) -> PriceObservationRecord | None: ...

    def get_history(
        self,
        retailer_product_id: int,
        *,
        since: EpochSeconds | None = None,
        limit: int | None = None,
    ) -> tuple[PriceObservationRecord, ...]: ...


@runtime_checkable
class SearchCacheRepo(Protocol):
    def get(self, retailer_code: str, normalized_query: str) -> SearchCacheEntry | None: ...

    def put(self, entry: SearchCacheEntry) -> None: ...
