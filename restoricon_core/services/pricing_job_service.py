"""Codey-Estimator Phase B9.x pricing round (2026-09-30): lifecycle
service for the `pricing_jobs` table -- a genuine lifecycle service (not a
bare CRUD repo, per this round's own scoping), tracking one row per
retailer refresh/import batch (`RetailerProductRepoImpl`/
`PriceObservationRepoImpl` in `pricing_repo.py` do the actual per-product
writes; this service only tracks the enclosing job's progress/outcome).
"""

from __future__ import annotations

from typing import Optional

from ..database import DatabaseManager
from ..models import utc_now_iso


class PricingJobService:
    """Tracks the lifecycle of one `pricing_jobs` row: pending -> running
    -> (succeeded | failed | partial). Constructor matches
    `EstimateService`'s convention (`db: DatabaseManager`)."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def start(
        self,
        retailer_code: str,
        job_type: str,
        triggered_by_user_id: Optional[int] = None,
    ) -> int:
        """Create a new job row and transition it straight to 'running'
        (there is no separate caller-visible 'pending' state in practice --
        a job is created the moment work begins), returning the new job id."""
        if job_type not in ("refresh_batch", "search_import", "manual_import"):
            raise ValueError(f"invalid job_type: {job_type!r}")
        conn = self.db.get_connection()
        now = utc_now_iso()
        with conn:
            conn.execute("BEGIN IMMEDIATE;")
            cursor = conn.execute(
                """
                INSERT INTO pricing_jobs (
                    retailer_code, job_type, status, started_at,
                    triggered_by_user_id, created_at
                ) VALUES (?, ?, 'running', ?, ?, ?);
                """,
                (retailer_code, job_type, now, triggered_by_user_id, now),
            )
            job_id = cursor.lastrowid
        return job_id

    def record_progress(
        self, job_id: int, checked: int = 0, updated: int = 0, failed: int = 0
    ) -> None:
        """Increment this job's running counters by the given deltas
        (NOT an absolute set -- callers report progress incrementally as
        each product in the batch is processed)."""
        conn = self.db.get_connection()
        with conn:
            conn.execute("BEGIN IMMEDIATE;")
            conn.execute(
                """
                UPDATE pricing_jobs SET
                    products_checked = products_checked + ?,
                    products_updated = products_updated + ?,
                    products_failed = products_failed + ?
                WHERE id = ?;
                """,
                (checked, updated, failed, job_id),
            )

    def complete(self, job_id: int) -> None:
        """Mark the job 'succeeded'. Callers that had any per-product
        failures but still want to report an overall success should use
        `partial()` instead -- this method is for a clean run only."""
        self._finish(job_id, status="succeeded")

    def fail(self, job_id: int, error_summary: str) -> None:
        """Mark the job 'failed', with a required `error_summary`."""
        self._finish(job_id, status="failed", error_summary=error_summary)

    def partial(self, job_id: int, error_summary: Optional[str] = None) -> None:
        """Mark the job 'partial' -- some products succeeded, some failed
        (the counts already recorded via `record_progress()` are the
        source of truth for which; `error_summary` here is optional
        supplementary context, e.g. a summary of the failure modes seen)."""
        self._finish(job_id, status="partial", error_summary=error_summary)

    def _finish(
        self, job_id: int, *, status: str, error_summary: Optional[str] = None
    ) -> None:
        """Guarded state-transition (code-reviewer finding, 2026-09-30):
        the original UPDATE had no status predicate and no `rowcount`
        check, so `complete()` then `fail()` (or any ordering) silently
        overwrote a `succeeded` job to `failed`, and calling any finish
        method with a nonexistent `job_id` silently no-op'd with zero
        feedback. `WHERE ... AND finished_at IS NULL` makes the UPDATE
        itself the atomic guard against a concurrent finish race (matches
        `EstimateService._lock_version_write`'s "not found" / "already in
        a terminal state" `ValueError` convention, e.g. `estimate_service.py`
        lines ~1662-1666); `rowcount == 0` after the guarded UPDATE means
        either the job_id never existed or it was already finished
        (possibly concurrently, between the pre-read and this UPDATE)."""
        conn = self.db.get_connection()
        with conn:
            conn.execute("BEGIN IMMEDIATE;")
            row = conn.execute(
                "SELECT finished_at FROM pricing_jobs WHERE id = ?;", (job_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"Pricing job {job_id} not found")
            if row["finished_at"] is not None:
                raise ValueError(f"Pricing job {job_id} is already in a terminal state")
            cursor = conn.execute(
                "UPDATE pricing_jobs SET status = ?, finished_at = ?, error_summary = ? "
                "WHERE id = ? AND finished_at IS NULL;",
                (status, utc_now_iso(), error_summary, job_id),
            )
            if cursor.rowcount == 0:
                raise ValueError(
                    f"Pricing job {job_id} was finished concurrently; lost the race"
                )
