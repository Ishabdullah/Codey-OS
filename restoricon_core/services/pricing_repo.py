"""Codey-Estimator Phase B9.x pricing round (2026-09-30): concrete repo
classes backing the 3 Protocol-bound tables `retailer_products`,
`price_observations`, `search_cache` (see `restoricon_core/database.py`'s
`_SCHEMA_SQL` for the DDL). Each class here satisfies exactly one of
`codey_estimator/ports.py`'s `@runtime_checkable` Protocols
(`RetailerProductRepo`, `PriceObservationRepo`, `SearchCacheRepo`) via
structural typing -- none of them subclass the Protocol, they just
implement its methods with matching signatures.

Convention notes (matching `EstimateService`, see
`restoricon_core/services/estimate_service.py`):
  - Constructor takes `db: DatabaseManager`.
  - Every write uses `BEGIN IMMEDIATE` so the write lock is held for the
    whole operation. `upsert()` is read-then-write (check-if-sku-exists,
    then insert-or-update) -- the lock must be held across both the read
    and the write, not just the write, or two concurrent upserts of a
    brand-new (retailer_code, retailer_sku) pair could both see "not
    found" and both INSERT, racing on the unique index. This is the same
    race class `NEW-534`'s claim-workflow fix already closed elsewhere in
    this codebase (see `codey_estimator_service.md` §2) -- not
    reintroduced here.
  - Every returned record is one of `ports.py`'s own frozen dataclasses
    (`RetailerProductRecord`, `PriceObservationRecord`, `SearchCacheEntry`),
    never a bare `sqlite3.Row`.
"""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from typing import Optional

from codey_estimator.ports import (
    ObservationSource,
    PriceObservationData,
    PriceObservationRecord,
    RefreshState,
    RetailerProductData,
    RetailerProductRecord,
    SearchCacheEntry,
)
from codey_estimator.refresh import EpochSeconds, RefreshStatus

from ..database import DatabaseManager
from ..models import utc_now_iso


def _attributes_to_json(attributes: tuple[tuple[str, str], ...]) -> str:
    return json.dumps(dict(attributes))


def _attributes_from_json(raw: str) -> tuple[tuple[str, str], ...]:
    obj = json.loads(raw) if raw else {}
    return tuple((k, v) for k, v in obj.items())


def _row_to_retailer_product_record(row: sqlite3.Row) -> RetailerProductRecord:
    data = RetailerProductData(
        retailer_code=row["retailer_code"],
        retailer_sku=row["retailer_sku"],
        title=row["title"],
        upc=row["upc"],
        model_number=row["model_number"],
        brand=row["brand"],
        description=row["description"],
        category_path=row["category_path"],
        attributes=_attributes_from_json(row["attributes_json"]),
        package_qty=Decimal(row["package_qty"]),
        package_unit=row["package_unit"],
        url=row["url"],
        availability=row["availability"],
    )
    refresh = RefreshState(
        last_checked_at=row["refresh_last_checked_at"],
        next_refresh_at=row["refresh_next_refresh_at"],
        refresh_interval_days=row["refresh_interval_days"],
        refresh_status=RefreshStatus(row["refresh_status"]),
        refresh_error=row["refresh_error"],
        refresh_priority=row["refresh_priority"],
        consecutive_failures=row["consecutive_failures"],
    )
    return RetailerProductRecord(
        id=row["id"],
        data=data,
        current_price_cents=row["current_price_cents"],
        current_observation_id=row["current_observation_id"],
        refresh=refresh,
        first_seen_at=row["first_seen_at"],
        active=bool(row["active"]),
    )


def _row_to_price_observation_record(row: sqlite3.Row) -> PriceObservationRecord:
    data = PriceObservationData(
        retailer_product_id=row["retailer_product_id"],
        price_cents=row["price_cents"],
        observed_at=row["observed_at"],
        source=ObservationSource(row["source"]),
        store_code=row["store_code"],
        was_price_cents=row["was_price_cents"],
        unit_price_cents=row["unit_price_cents"],
        availability=row["availability"],
        observed_by_user_id=row["observed_by_user_id"],
        raw_hash=row["raw_hash"],
    )
    return PriceObservationRecord(id=row["id"], data=data)


def _row_to_search_cache_entry(row: sqlite3.Row) -> SearchCacheEntry:
    return SearchCacheEntry(
        retailer_code=row["retailer_code"],
        normalized_query=row["normalized_query"],
        result_skus=tuple(json.loads(row["result_skus_json"])),
        fetched_at=row["fetched_at"],
    )


class RetailerProductRepoImpl:
    """Satisfies `codey_estimator.ports.RetailerProductRepo`."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def get_by_sku(
        self, retailer_code: str, retailer_sku: str
    ) -> Optional[RetailerProductRecord]:
        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT * FROM retailer_products WHERE retailer_code = ? AND retailer_sku = ?;",
            (retailer_code, retailer_sku),
        ).fetchone()
        return _row_to_retailer_product_record(row) if row is not None else None

    def get_by_upc(
        self, upc: str, retailer_code: Optional[str] = None
    ) -> tuple[RetailerProductRecord, ...]:
        conn = self.db.get_connection()
        if retailer_code is None:
            rows = conn.execute(
                "SELECT * FROM retailer_products WHERE upc = ?;", (upc,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM retailer_products WHERE upc = ? AND retailer_code = ?;",
                (upc, retailer_code),
            ).fetchall()
        return tuple(_row_to_retailer_product_record(r) for r in rows)

    def upsert(
        self, data: RetailerProductData, seen_at: EpochSeconds
    ) -> RetailerProductRecord:
        """Read-then-write, lock held for the whole operation -- see this
        module's docstring for why the `BEGIN IMMEDIATE` must wrap both
        the existence check and the insert/update (NEW-534 race class)."""
        conn = self.db.get_connection()
        attributes_json = _attributes_to_json(data.attributes)
        package_qty = str(data.package_qty)
        with conn:
            conn.execute("BEGIN IMMEDIATE;")
            existing = conn.execute(
                "SELECT id, first_seen_at FROM retailer_products "
                "WHERE retailer_code = ? AND retailer_sku = ?;",
                (data.retailer_code, data.retailer_sku),
            ).fetchone()
            now_iso = utc_now_iso()
            if existing is None:
                cursor = conn.execute(
                    """
                    INSERT INTO retailer_products (
                        retailer_code, retailer_sku, title, upc, model_number, brand,
                        description, category_path, attributes_json, package_qty,
                        package_unit, url, availability, first_seen_at, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        data.retailer_code, data.retailer_sku, data.title, data.upc,
                        data.model_number, data.brand, data.description, data.category_path,
                        attributes_json, package_qty, data.package_unit, data.url,
                        data.availability, seen_at, now_iso, now_iso,
                    ),
                )
                product_id = cursor.lastrowid
            else:
                product_id = existing["id"]
                conn.execute(
                    """
                    UPDATE retailer_products SET
                        title = ?, upc = ?, model_number = ?, brand = ?, description = ?,
                        category_path = ?, attributes_json = ?, package_qty = ?,
                        package_unit = ?, url = ?, availability = ?, updated_at = ?
                    WHERE id = ?;
                    """,
                    (
                        data.title, data.upc, data.model_number, data.brand, data.description,
                        data.category_path, attributes_json, package_qty, data.package_unit,
                        data.url, data.availability, now_iso, product_id,
                    ),
                )
            row = conn.execute(
                "SELECT * FROM retailer_products WHERE id = ?;", (product_id,)
            ).fetchone()
        return _row_to_retailer_product_record(row)

    def list_needing_refresh(
        self, now: EpochSeconds, limit: int
    ) -> tuple[RetailerProductRecord, ...]:
        conn = self.db.get_connection()
        rows = conn.execute(
            """
            SELECT * FROM retailer_products
            WHERE active = 1
              AND refresh_status NOT IN ('disabled', 'failed', 'pending')
              AND (refresh_next_refresh_at IS NULL OR refresh_next_refresh_at <= ?)
            ORDER BY refresh_priority DESC, refresh_next_refresh_at ASC
            LIMIT ?;
            """,
            (now, limit),
        ).fetchall()
        return tuple(_row_to_retailer_product_record(r) for r in rows)

    def update_refresh_state(self, product_id: int, state: RefreshState) -> None:
        conn = self.db.get_connection()
        with conn:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute(
                """
                UPDATE retailer_products SET
                    refresh_last_checked_at = ?, refresh_next_refresh_at = ?,
                    refresh_interval_days = ?, refresh_status = ?, refresh_error = ?,
                    refresh_priority = ?, consecutive_failures = ?, updated_at = ?
                WHERE id = ?;
                """,
                (
                    state.last_checked_at, state.next_refresh_at, state.refresh_interval_days,
                    state.refresh_status.value, state.refresh_error, state.refresh_priority,
                    state.consecutive_failures, utc_now_iso(), product_id,
                ),
            )


class PriceObservationRepoImpl:
    """Satisfies `codey_estimator.ports.PriceObservationRepo`. Every write
    inserts into the append-only `price_observations` table (see the DB
    triggers `trg_price_observations_no_update`/`_no_delete`) -- this
    class never issues an UPDATE or DELETE against that table."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def append(self, observation: PriceObservationData) -> PriceObservationRecord:
        conn = self.db.get_connection()
        with conn:
            conn.execute("BEGIN IMMEDIATE;")
            cursor = conn.execute(
                """
                INSERT INTO price_observations (
                    retailer_product_id, price_cents, observed_at, source, store_code,
                    was_price_cents, unit_price_cents, availability, observed_by_user_id, raw_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    observation.retailer_product_id, observation.price_cents,
                    observation.observed_at, observation.source.value,
                    observation.store_code, observation.was_price_cents,
                    observation.unit_price_cents, observation.availability,
                    observation.observed_by_user_id, observation.raw_hash,
                ),
            )
            obs_id = cursor.lastrowid
            conn.execute(
                "UPDATE retailer_products SET current_observation_id = ?, "
                "current_price_cents = ?, updated_at = ? WHERE id = ?;",
                (obs_id, observation.price_cents, utc_now_iso(), observation.retailer_product_id),
            )
            row = conn.execute(
                "SELECT * FROM price_observations WHERE id = ?;", (obs_id,)
            ).fetchone()
        return _row_to_price_observation_record(row)

    def get_latest(
        self, retailer_product_id: int, store_code: Optional[str] = None
    ) -> Optional[PriceObservationRecord]:
        conn = self.db.get_connection()
        if store_code is None:
            row = conn.execute(
                "SELECT * FROM price_observations WHERE retailer_product_id = ? "
                "ORDER BY observed_at DESC, id DESC LIMIT 1;",
                (retailer_product_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM price_observations WHERE retailer_product_id = ? "
                "AND store_code = ? ORDER BY observed_at DESC, id DESC LIMIT 1;",
                (retailer_product_id, store_code),
            ).fetchone()
        return _row_to_price_observation_record(row) if row is not None else None

    def get_history(
        self,
        retailer_product_id: int,
        *,
        since: Optional[EpochSeconds] = None,
        limit: Optional[int] = None,
    ) -> tuple[PriceObservationRecord, ...]:
        conn = self.db.get_connection()
        sql = "SELECT * FROM price_observations WHERE retailer_product_id = ?"
        params: list = [retailer_product_id]
        if since is not None:
            sql += " AND observed_at >= ?"
            params.append(since)
        sql += " ORDER BY observed_at DESC, id DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = conn.execute(sql, tuple(params)).fetchall()
        return tuple(_row_to_price_observation_record(r) for r in rows)


class SearchCacheRepoImpl:
    """Satisfies `codey_estimator.ports.SearchCacheRepo`."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def get(self, retailer_code: str, normalized_query: str) -> Optional[SearchCacheEntry]:
        conn = self.db.get_connection()
        row = conn.execute(
            "SELECT * FROM search_cache WHERE retailer_code = ? AND normalized_query = ?;",
            (retailer_code, normalized_query),
        ).fetchone()
        return _row_to_search_cache_entry(row) if row is not None else None

    def put(self, entry: SearchCacheEntry) -> None:
        """Read-then-write, lock held for the whole operation -- same
        upsert race reasoning as `RetailerProductRepoImpl.upsert()` above."""
        conn = self.db.get_connection()
        result_skus_json = json.dumps(list(entry.result_skus))
        with conn:
            conn.execute("BEGIN IMMEDIATE;")
            existing = conn.execute(
                "SELECT id FROM search_cache WHERE retailer_code = ? AND normalized_query = ?;",
                (entry.retailer_code, entry.normalized_query),
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO search_cache (retailer_code, normalized_query, "
                    "result_skus_json, fetched_at) VALUES (?, ?, ?, ?);",
                    (entry.retailer_code, entry.normalized_query, result_skus_json, entry.fetched_at),
                )
            else:
                conn.execute(
                    "UPDATE search_cache SET result_skus_json = ?, fetched_at = ? WHERE id = ?;",
                    (result_skus_json, entry.fetched_at, existing["id"]),
                )

