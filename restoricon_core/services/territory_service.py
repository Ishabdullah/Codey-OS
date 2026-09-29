"""
Territory Management Domain Engine for Restoricon Core (B8.9a,
sales_rep_portal.md §5 B8.9, corrected scope 2026-09-23 -- territory
management only, NOT referral compensation; see NEW-545's resolution).

Minimal CRUD for the territories lookup table itself:
create_territory, list_territories, get_territory, update_territory.
No delete -- see database.py's territories table comment for why (a
territory with users/leads/customers still referencing it would
silently orphan those FK-less references; no "active reference" guard
concept has been designed for this yet).

Dedicated service, not folded into CRMService/AuthService, because its
RBAC gate (PERM_READ_TERRITORIES/PERM_WRITE_TERRITORIES, a new
dedicated pair mirroring appointment_types' own pair) doesn't match
either host service's gates -- same reasoning FinancingService's module
docstring gives for its own dedicated-service split.

Explicit, human-set assignment only -- no ZIP/geocoding inference.
Assigning a territory_id TO a user/lead/customer is handled entirely by
the existing update_user/update_lead/update_customer write paths (gated
by PERM_MANAGE_USERS / PERM_WRITE_LEADS / PERM_WRITE_CUSTOMERS
respectively) -- this service only manages the territories table rows
themselves.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..auth import AuthContext, PERM_READ_TERRITORIES, PERM_WRITE_TERRITORIES
from ..database import DatabaseManager
from ..models import Territory, utc_now_iso
from .audit_service import AuditService, build_audit_details, _AUDITABLE_TERRITORY_FIELDS


class TerritoryService:
    """Manages the territories lookup table. See module docstring for
    scope and gate rationale."""

    ALLOWED_TERRITORY_UPDATE_FIELDS = {"name", "code", "notes"}

    def __init__(self, db: DatabaseManager, audit: AuditService):
        self.db = db
        self.audit = audit

    @staticmethod
    def _row_to_territory(row: Any) -> Territory:
        return Territory(
            id=row["id"],
            name=row["name"],
            code=row["code"],
            notes=row["notes"],
            created_at=row["created_at"],
        )

    def create_territory(self, territory: Territory, actor: AuthContext) -> Territory:
        if not actor.has_permission(PERM_WRITE_TERRITORIES):
            raise PermissionError("Actor lacks permission to create territories")

        if not territory.name or not str(territory.name).strip():
            raise ValueError("Territory name is required")
        territory.name = str(territory.name).strip()

        now = utc_now_iso()
        territory.created_at = now

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO territories (name, code, notes, created_at)
                VALUES (?, ?, ?, ?);
                """,
                (territory.name, territory.code, territory.notes, now),
            )
            territory.id = cursor.lastrowid

        self.audit.log(
            action="create",
            entity_type="territory",
            entity_id=territory.id,
            change_summary=f"Created territory '{territory.name}'",
            actor=actor,
            details=build_audit_details(after=territory.to_dict(), fields=_AUDITABLE_TERRITORY_FIELDS),
        )
        return territory

    def list_territories(self, actor: AuthContext) -> List[Territory]:
        if not actor.has_permission(PERM_READ_TERRITORIES):
            raise PermissionError("Actor lacks permission to view territories")

        conn = self.db.get_connection()
        rows = conn.execute("SELECT * FROM territories ORDER BY name ASC;").fetchall()
        return [self._row_to_territory(r) for r in rows]

    def get_territory(self, territory_id: int, actor: AuthContext) -> Optional[Territory]:
        if not actor.has_permission(PERM_READ_TERRITORIES):
            raise PermissionError("Actor lacks permission to view territories")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM territories WHERE id = ?;", (territory_id,)).fetchone()
        if not row:
            return None
        return self._row_to_territory(row)

    def update_territory(
        self, territory_id: int, updates: Dict[str, Any], actor: AuthContext
    ) -> Optional[Territory]:
        if not actor.has_permission(PERM_WRITE_TERRITORIES):
            raise PermissionError("Actor lacks permission to update territories")

        unknown = set(updates) - self.ALLOWED_TERRITORY_UPDATE_FIELDS
        if unknown:
            raise ValueError(f"Unknown field(s) for territory update: {sorted(unknown)}")

        if "name" in updates and (updates["name"] is None or not str(updates["name"]).strip()):
            raise ValueError("Territory name cannot be cleared")

        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM territories WHERE id = ?;", (territory_id,)).fetchone()
        if not row:
            return None

        territory = self._row_to_territory(row)
        _before = territory.to_dict()

        for key, value in updates.items():
            if key == "name" and isinstance(value, str):
                value = value.strip()
            setattr(territory, key, value)

        with conn:
            conn.execute(
                "UPDATE territories SET name = ?, code = ?, notes = ? WHERE id = ?;",
                (territory.name, territory.code, territory.notes, territory_id),
            )

        self.audit.log(
            action="update",
            entity_type="territory",
            entity_id=territory_id,
            change_summary=f"Updated territory {territory_id}",
            actor=actor,
            details=build_audit_details(before=_before, after=territory.to_dict(), fields=_AUDITABLE_TERRITORY_FIELDS),
        )
        return territory
