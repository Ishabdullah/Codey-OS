"""Codey-Estimator Phase B9.x pricing round (2026-09-30) tests: CRUD
round-trips + Protocol conformance for the 3 repo classes in
`restoricon_core/services/pricing_repo.py`, the append-only trigger
guarantees on `price_observations`/`labor_rate_history`, the unique-index
collision guarantees on `retailer_products`/`search_cache`/
`material_matches`, a `canonical_materials`/`material_matches` JSON
round-trip (including a Measure-typed attribute, to exercise the
Fraction-as-string serialization), and `PricingJobService`'s lifecycle
methods.
"""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from fractions import Fraction

import pytest

from codey_estimator.ports import (
    ObservationSource,
    PriceObservationData,
    PriceObservationRepo,
    RefreshState,
    RetailerProductData,
    RetailerProductRepo,
    SearchCacheEntry,
    SearchCacheRepo,
)
from codey_estimator.refresh import RefreshStatus
from restoricon_core.database import DatabaseManager
from restoricon_core.services.pricing_job_service import PricingJobService
from restoricon_core.services.pricing_repo import (
    PriceObservationRepoImpl,
    RetailerProductRepoImpl,
    SearchCacheRepoImpl,
)

_NOW = "2026-01-01T00:00:00Z"


def _seed_retailer(conn: sqlite3.Connection, code: str = "home_depot") -> None:
    conn.execute(
        "INSERT INTO retailers (code, display_name, created_at, updated_at) VALUES (?, ?, ?, ?);",
        (code, code.replace("_", " ").title(), _NOW, _NOW),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# RetailerProductRepoImpl / RetailerProductRepo
# ---------------------------------------------------------------------------

def test_retailer_product_repo_satisfies_protocol():
    db = DatabaseManager(":memory:")
    repo = RetailerProductRepoImpl(db)
    assert isinstance(repo, RetailerProductRepo)


def test_retailer_product_repo_crud_round_trip():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()
    _seed_retailer(conn)
    repo = RetailerProductRepoImpl(db)

    data = RetailerProductData(
        retailer_code="home_depot",
        retailer_sku="SKU-001",
        title="2x4 Stud Lumber",
        upc="00012345678905",
        model_number="M-100",
        brand="Acme",
        description="8ft stud",
        category_path="lumber/dimensional",
        attributes=(("grade", "1"), ("treated", "no")),
        package_qty=Decimal("1"),
        package_unit="each",
        url="https://example.com/sku-001",
        availability="in_stock",
    )
    created = repo.upsert(data, seen_at=1_700_000_000)
    assert created.id is not None
    assert created.data.retailer_sku == "SKU-001"
    assert created.data.attributes == (("grade", "1"), ("treated", "no"))
    assert created.data.package_qty == Decimal("1")
    assert isinstance(created.data.package_qty, Decimal)
    assert created.first_seen_at == 1_700_000_000
    assert created.active is True
    assert isinstance(created.refresh.refresh_status, RefreshStatus)
    assert created.refresh.refresh_status == RefreshStatus.OK

    fetched = repo.get_by_sku("home_depot", "SKU-001")
    assert fetched == created

    by_upc = repo.get_by_upc("00012345678905")
    assert len(by_upc) == 1
    assert by_upc[0].id == created.id
    by_upc_scoped = repo.get_by_upc("00012345678905", retailer_code="home_depot")
    assert len(by_upc_scoped) == 1
    by_upc_other_retailer = repo.get_by_upc("00012345678905", retailer_code="lowes")
    assert by_upc_other_retailer == ()

    # upsert again with the same (retailer_code, retailer_sku) -> update path,
    # same id, first_seen_at unchanged.
    updated_data = RetailerProductData(
        retailer_code="home_depot",
        retailer_sku="SKU-001",
        title="2x4 Stud Lumber (Updated)",
        attributes=(("grade", "2"),),
    )
    updated = repo.upsert(updated_data, seen_at=1_700_000_500)
    assert updated.id == created.id
    assert updated.data.title == "2x4 Stud Lumber (Updated)"
    assert updated.first_seen_at == created.first_seen_at

    # list_needing_refresh / update_refresh_state round-trip.
    due = repo.list_needing_refresh(now=1_700_000_600, limit=10)
    assert any(r.id == created.id for r in due)

    new_state = RefreshState(
        last_checked_at=1_700_000_600,
        next_refresh_at=1_700_100_000,
        refresh_interval_days=30,
        refresh_status=RefreshStatus.FAILED,
        refresh_error="HTTP 503",
        refresh_priority=5,
        consecutive_failures=2,
    )
    repo.update_refresh_state(created.id, new_state)
    after = repo.get_by_sku("home_depot", "SKU-001")
    assert after.refresh.refresh_status == RefreshStatus.FAILED
    assert isinstance(after.refresh.refresh_status, RefreshStatus)
    assert after.refresh.refresh_error == "HTTP 503"
    assert after.refresh.consecutive_failures == 2

    # A FAILED product is excluded from list_needing_refresh.
    due_after = repo.list_needing_refresh(now=1_700_200_000, limit=10)
    assert all(r.id != created.id for r in due_after)


def test_retailer_products_sku_unique_index_collision():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()
    _seed_retailer(conn)
    now_ts = 1_700_000_000
    conn.execute(
        "INSERT INTO retailer_products (retailer_code, retailer_sku, title, first_seen_at, "
        "created_at, updated_at) VALUES ('home_depot', 'SKU-DUP', 'A', ?, ?, ?);",
        (now_ts, _NOW, _NOW),
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO retailer_products (retailer_code, retailer_sku, title, first_seen_at, "
            "created_at, updated_at) VALUES ('home_depot', 'SKU-DUP', 'B', ?, ?, ?);",
            (now_ts, _NOW, _NOW),
        )


# ---------------------------------------------------------------------------
# PriceObservationRepoImpl / PriceObservationRepo
# ---------------------------------------------------------------------------

def test_price_observation_repo_satisfies_protocol():
    db = DatabaseManager(":memory:")
    repo = PriceObservationRepoImpl(db)
    assert isinstance(repo, PriceObservationRepo)


def test_price_observation_repo_crud_round_trip():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()
    _seed_retailer(conn)
    product_repo = RetailerProductRepoImpl(db)
    product = product_repo.upsert(
        RetailerProductData(retailer_code="home_depot", retailer_sku="SKU-PO", title="Widget"),
        seen_at=1_700_000_000,
    )

    obs_repo = PriceObservationRepoImpl(db)
    obs1 = obs_repo.append(
        PriceObservationData(
            retailer_product_id=product.id,
            price_cents=999,
            observed_at=1_700_000_100,
            source=ObservationSource.MANUAL,
            store_code="0123",
        )
    )
    assert obs1.data.price_cents == 999
    assert isinstance(obs1.data.source, ObservationSource)

    obs2 = obs_repo.append(
        PriceObservationData(
            retailer_product_id=product.id,
            price_cents=899,
            observed_at=1_700_000_200,
            source=ObservationSource.ADAPTER,
        )
    )

    latest = obs_repo.get_latest(product.id)
    assert latest.id == obs2.id
    latest_by_store = obs_repo.get_latest(product.id, store_code="0123")
    assert latest_by_store.id == obs1.id

    history_all = obs_repo.get_history(product.id)
    assert [r.id for r in history_all] == [obs2.id, obs1.id]

    history_since = obs_repo.get_history(product.id, since=1_700_000_150)
    assert [r.id for r in history_since] == [obs2.id]

    history_limited = obs_repo.get_history(product.id, limit=1)
    assert len(history_limited) == 1

    # current_observation_id/current_price_cents on the product were kept
    # in sync by append().
    refreshed_product = product_repo.get_by_sku("home_depot", "SKU-PO")
    assert refreshed_product.current_observation_id == obs2.id
    assert refreshed_product.current_price_cents == 899


def test_price_observations_append_only_triggers():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()
    _seed_retailer(conn)
    product_repo = RetailerProductRepoImpl(db)
    product = product_repo.upsert(
        RetailerProductData(retailer_code="home_depot", retailer_sku="SKU-AO", title="Widget"),
        seen_at=1_700_000_000,
    )
    obs_repo = PriceObservationRepoImpl(db)
    obs = obs_repo.append(
        PriceObservationData(
            retailer_product_id=product.id,
            price_cents=500,
            observed_at=1_700_000_000,
            source=ObservationSource.MANUAL,
        )
    )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute(
            "UPDATE price_observations SET price_cents = 1 WHERE id = ?;", (obs.id,)
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM price_observations WHERE id = ?;", (obs.id,))


# ---------------------------------------------------------------------------
# SearchCacheRepoImpl / SearchCacheRepo
# ---------------------------------------------------------------------------

def test_search_cache_repo_satisfies_protocol():
    db = DatabaseManager(":memory:")
    repo = SearchCacheRepoImpl(db)
    assert isinstance(repo, SearchCacheRepo)


def test_search_cache_repo_crud_round_trip():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()
    _seed_retailer(conn)
    repo = SearchCacheRepoImpl(db)

    assert repo.get("home_depot", "2x4 lumber") is None

    entry = SearchCacheEntry(
        retailer_code="home_depot",
        normalized_query="2x4 lumber",
        result_skus=("SKU-1", "SKU-2", "SKU-3"),
        fetched_at=1_700_000_000,
    )
    repo.put(entry)
    fetched = repo.get("home_depot", "2x4 lumber")
    assert fetched == entry
    assert isinstance(fetched.result_skus, tuple)

    # put() again for the same (retailer_code, normalized_query) -> update,
    # not a duplicate row.
    updated_entry = SearchCacheEntry(
        retailer_code="home_depot",
        normalized_query="2x4 lumber",
        result_skus=("SKU-9",),
        fetched_at=1_700_001_000,
    )
    repo.put(updated_entry)
    assert repo.get("home_depot", "2x4 lumber") == updated_entry
    count = conn.execute(
        "SELECT COUNT(*) FROM search_cache WHERE retailer_code='home_depot' "
        "AND normalized_query='2x4 lumber';"
    ).fetchone()[0]
    assert count == 1


def test_search_cache_unique_index_collision():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()
    _seed_retailer(conn)
    conn.execute(
        "INSERT INTO search_cache (retailer_code, normalized_query, result_skus_json, fetched_at) "
        "VALUES ('home_depot', 'q', '[]', 1700000000);"
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO search_cache (retailer_code, normalized_query, result_skus_json, fetched_at) "
            "VALUES ('home_depot', 'q', '[]', 1700000001);"
        )


# ---------------------------------------------------------------------------
# labor_rates / labor_rate_history append-only trigger + unique index
# ---------------------------------------------------------------------------

def test_labor_rate_history_append_only_triggers():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()
    conn.execute(
        "INSERT INTO labor_rates (labor_type, rate_type, cost_rate_cents, bill_rate_cents, "
        "effective_date, created_at, updated_at) VALUES ('carpenter', 'hourly', 3000, 6000, ?, ?, ?);",
        (_NOW, _NOW, _NOW),
    )
    conn.commit()
    rate_id = conn.execute("SELECT id FROM labor_rates;").fetchone()[0]
    conn.execute(
        "INSERT INTO labor_rate_history (labor_rate_id, cost_rate_cents, bill_rate_cents, changed_at) "
        "VALUES (?, 3000, 6000, ?);",
        (rate_id, _NOW),
    )
    conn.commit()
    hist_id = conn.execute("SELECT id FROM labor_rate_history;").fetchone()[0]

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute(
            "UPDATE labor_rate_history SET cost_rate_cents = 1 WHERE id = ?;", (hist_id,)
        )
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("DELETE FROM labor_rate_history WHERE id = ?;", (hist_id,))


# ---------------------------------------------------------------------------
# canonical_materials / material_matches: JSON round-trip (incl. Measure)
# and unique-index collision
# ---------------------------------------------------------------------------

def _measure_to_json(value: Fraction, unit: str) -> dict:
    # str(Fraction) round-trips exactly via Fraction(str) -- no manual
    # numerator/denominator formatting needed (Fraction(2, 1) stringifies
    # to "2", not "2/1"; Fraction("2") parses back fine either way).
    return {"value": str(value), "unit": unit}


def test_canonical_materials_json_round_trip_with_measure_attribute():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()

    attributes = [
        ["material", "copper"],
        ["nominal_size", _measure_to_json(Fraction(1, 2), "in")],
    ]
    attributes_json = json.dumps(attributes)
    conn.execute(
        "INSERT INTO canonical_materials (category, display_name, attributes_json, created_at, updated_at) "
        "VALUES ('plumbing_pipe', '1/2in Copper Pipe', ?, ?, ?);",
        (attributes_json, _NOW, _NOW),
    )
    conn.commit()
    row = conn.execute(
        "SELECT attributes_json FROM canonical_materials WHERE display_name = '1/2in Copper Pipe';"
    ).fetchone()
    loaded = json.loads(row["attributes_json"])
    assert loaded[0] == ["material", "copper"]
    measure_attr = loaded[1]
    assert measure_attr[0] == "nominal_size"
    restored_fraction = Fraction(measure_attr[1]["value"])
    assert restored_fraction == Fraction(1, 2)
    assert measure_attr[1]["unit"] == "in"


def test_material_matches_unique_index_collision():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()
    _seed_retailer(conn)
    conn.execute(
        "INSERT INTO canonical_materials (category, display_name, attributes_json, created_at, updated_at) "
        "VALUES ('plumbing_pipe', 'Copper Pipe', '[]', ?, ?);",
        (_NOW, _NOW),
    )
    material_id = conn.execute("SELECT id FROM canonical_materials;").fetchone()[0]
    conn.execute(
        "INSERT INTO retailer_products (retailer_code, retailer_sku, title, first_seen_at, created_at, updated_at) "
        "VALUES ('home_depot', 'SKU-M', 'Pipe', 1700000000, ?, ?);",
        (_NOW, _NOW),
    )
    product_id = conn.execute("SELECT id FROM retailer_products;").fetchone()[0]
    conn.commit()

    conn.execute(
        "INSERT INTO material_matches (canonical_material_id, retailer_product_id, confidence_bp, "
        "status, method, created_at) VALUES (?, ?, 9500, 'auto_confirmed', 'upc', ?);",
        (material_id, product_id, _NOW),
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO material_matches (canonical_material_id, retailer_product_id, confidence_bp, "
            "status, method, created_at) VALUES (?, ?, 7000, 'proposed', 'attributes', ?);",
            (material_id, product_id, _NOW),
        )


# ---------------------------------------------------------------------------
# PricingJobService lifecycle
# ---------------------------------------------------------------------------

def test_pricing_job_service_start_and_complete():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()
    _seed_retailer(conn)
    svc = PricingJobService(db)

    job_id = svc.start("home_depot", "refresh_batch")
    row = conn.execute("SELECT * FROM pricing_jobs WHERE id = ?;", (job_id,)).fetchone()
    assert row["status"] == "running"
    assert row["started_at"] is not None

    svc.record_progress(job_id, checked=10, updated=8, failed=2)
    svc.complete(job_id)
    row = conn.execute("SELECT * FROM pricing_jobs WHERE id = ?;", (job_id,)).fetchone()
    assert row["status"] == "succeeded"
    assert row["products_checked"] == 10
    assert row["products_updated"] == 8
    assert row["products_failed"] == 2
    assert row["finished_at"] is not None


def test_pricing_job_service_fail_sets_error_summary():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()
    _seed_retailer(conn)
    svc = PricingJobService(db)

    job_id = svc.start("home_depot", "search_import")
    svc.fail(job_id, "adapter returned HTTP 500")
    row = conn.execute("SELECT * FROM pricing_jobs WHERE id = ?;", (job_id,)).fetchone()
    assert row["status"] == "failed"
    assert row["error_summary"] == "adapter returned HTTP 500"


def test_pricing_job_service_partial():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()
    _seed_retailer(conn)
    svc = PricingJobService(db)

    job_id = svc.start("home_depot", "refresh_batch")
    svc.record_progress(job_id, checked=5, updated=3, failed=2)
    svc.partial(job_id, error_summary="2 of 5 products failed")
    row = conn.execute("SELECT * FROM pricing_jobs WHERE id = ?;", (job_id,)).fetchone()
    assert row["status"] == "partial"
    assert row["error_summary"] == "2 of 5 products failed"


def test_pricing_job_service_start_rejects_invalid_job_type():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()
    _seed_retailer(conn)
    svc = PricingJobService(db)
    with pytest.raises(ValueError):
        svc.start("home_depot", "not_a_real_job_type")


def test_pricing_job_service_finish_rejects_overwriting_a_terminal_job():
    """Code-reviewer finding, 2026-09-30: complete() then fail() on the
    same job must raise instead of silently overwriting a 'succeeded' job
    to 'failed'."""
    db = DatabaseManager(":memory:")
    conn = db.get_connection()
    _seed_retailer(conn)
    svc = PricingJobService(db)

    job_id = svc.start("home_depot", "refresh_batch")
    svc.complete(job_id)
    with pytest.raises(ValueError, match="already in a terminal state"):
        svc.fail(job_id, "too late")
    row = conn.execute("SELECT status, error_summary FROM pricing_jobs WHERE id = ?;", (job_id,)).fetchone()
    assert row["status"] == "succeeded"
    assert row["error_summary"] is None


def test_pricing_job_service_finish_rejects_nonexistent_job_id():
    """Code-reviewer finding, 2026-09-30: calling any finish method with a
    nonexistent job_id must raise instead of silently no-op'ing."""
    db = DatabaseManager(":memory:")
    svc = PricingJobService(db)
    with pytest.raises(ValueError, match="not found"):
        svc.complete(999999)
    with pytest.raises(ValueError, match="not found"):
        svc.fail(999999, "doesn't matter")
    with pytest.raises(ValueError, match="not found"):
        svc.partial(999999)


# ---------------------------------------------------------------------------
# FTS5 search (available on this device -- confirmed via
# sqlite_compileoption_used('ENABLE_FTS5') -> 1, see test_database.py's
# test_pricing_tables_created_fresh)
# ---------------------------------------------------------------------------

def test_product_search_fts_sync_triggers_keep_index_current():
    db = DatabaseManager(":memory:")
    conn = db.get_connection()
    _seed_retailer(conn)
    product_repo = RetailerProductRepoImpl(db)
    product = product_repo.upsert(
        RetailerProductData(
            retailer_code="home_depot", retailer_sku="SKU-FTS", title="Cordless Drill",
            brand="Acme", model_number="D-100",
        ),
        seen_at=1_700_000_000,
    )
    rows = conn.execute(
        "SELECT rowid FROM product_search_fts WHERE product_search_fts MATCH 'drill';"
    ).fetchall()
    assert [r["rowid"] for r in rows] == [product.id]

    # Update the title -- the sync trigger must re-index it.
    product_repo.upsert(
        RetailerProductData(
            retailer_code="home_depot", retailer_sku="SKU-FTS", title="Cordless Impact Wrench",
        ),
        seen_at=1_700_000_100,
    )
    rows_after_update = conn.execute(
        "SELECT rowid FROM product_search_fts WHERE product_search_fts MATCH 'drill';"
    ).fetchall()
    assert rows_after_update == []
    rows_new_term = conn.execute(
        "SELECT rowid FROM product_search_fts WHERE product_search_fts MATCH 'wrench';"
    ).fetchall()
    assert [r["rowid"] for r in rows_new_term] == [product.id]
