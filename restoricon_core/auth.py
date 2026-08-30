"""
Authentication, Session Token Management, and Role-Based Access Control (RBAC)
for Restoricon Core.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from .database import DatabaseManager
from .models import User, utc_now_iso

# PBKDF2 parameters
SALT_BYTES = 16
HASH_ITERATIONS = 100_000
TOKEN_EXPIRY_DAYS = 7

# Role definitions per CODEY_MASTER_PLAN.md §6.3 & Appendix C §16
ROLE_ADMIN = "admin"
ROLE_MANAGER = "manager"
ROLE_SALES = "sales"
ROLE_PROJECT_MANAGER = "project_manager"
ROLE_TECHNICIAN = "technician"
ROLE_AI_AGENT = "ai_agent"
ROLE_CUSTOMER = "customer"

ALL_ROLES = {
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_SALES,
    ROLE_PROJECT_MANAGER,
    ROLE_TECHNICIAN,
    ROLE_AI_AGENT,
    ROLE_CUSTOMER,
}

# Permissions
PERM_READ_ALL_CUSTOMERS = "read:all_customers"
PERM_WRITE_CUSTOMERS = "write:customers"
PERM_READ_OWN_CUSTOMER = "read:own_customer"

PERM_READ_LEADS = "read:leads"
PERM_WRITE_LEADS = "write:leads"

PERM_READ_OPPORTUNITIES = "read:opportunities"
PERM_WRITE_OPPORTUNITIES = "write:opportunities"

PERM_READ_ALL_PROJECTS = "read:all_projects"
PERM_READ_ASSIGNED_PROJECTS = "read:assigned_projects"
PERM_READ_OWN_PROJECTS = "read:own_projects"
PERM_WRITE_PROJECTS = "write:projects"

PERM_READ_ESTIMATES = "read:estimates"
PERM_WRITE_ESTIMATES = "write:estimates"
PERM_READ_OWN_ESTIMATES = "read:own_estimates"

PERM_READ_CONTRACTS = "read:contracts"
PERM_WRITE_CONTRACTS = "write:contracts"
# NEW-192, 2026-08-26: PERM_SIGN_CONTRACTS is granted to admin/manager/
# sales/project_manager (company-side signers) and customer (the other
# party). Deliberately withheld from technician (not a signing role) and
# ai_agent (an autonomous agent should not hold binding-signature
# authority by default). This is a placeholder policy per Ish's own
# framing — Restoricon's real signing workflow is still being defined —
# not a final business rule; revisit when that policy is settled.
PERM_SIGN_CONTRACTS = "sign:contracts"
PERM_READ_OWN_CONTRACTS = "read:own_contracts"

PERM_READ_DOCUMENTS = "read:documents"
PERM_WRITE_DOCUMENTS = "write:documents"
PERM_READ_OWN_DOCUMENTS = "read:own_documents"

PERM_READ_FINANCIALS = "read:financials"
PERM_WRITE_FINANCIALS = "write:financials"
PERM_READ_OWN_FINANCIALS = "read:own_financials"

PERM_LOG_COMMUNICATION = "log:communication"
PERM_READ_COMMUNICATIONS = "read:communications"
PERM_READ_OWN_COMMUNICATIONS = "read:own_communications"

PERM_READ_AUDIT_LOG = "read:audit_log"
PERM_MANAGE_USERS = "manage:users"

# B2/NEW-209, 2026-08-27: Ish decided to build all five of Aigentik-CLI's
# real data shapes now, not just the two (contacts/customers) that already
# had a Core-table destination. These five permission pairs cover the
# newly-added subcontractors/appointments/automation_rules/business_profile/
# do_not_contact tables. Deliberately no PERM_READ_OWN_* variant for any of
# them and ROLE_CUSTOMER holds none of them (see ROLE_PERMISSIONS below) --
# all five are internal-only data with no legitimate customer-facing read
# path, so there is no customer-scoped narrowing branch to key off
# `actor.role` the way NEW-194 found `get_project()`/`list_projects()`
# does. This isn't an oversight; it's how NEW-194's whole class of bug is
# avoided here instead of retrofitted later.
PERM_READ_SUBCONTRACTORS = "read:subcontractors"
PERM_WRITE_SUBCONTRACTORS = "write:subcontractors"

PERM_READ_APPOINTMENTS = "read:appointments"
PERM_WRITE_APPOINTMENTS = "write:appointments"

PERM_READ_AUTOMATION_RULES = "read:automation_rules"
PERM_WRITE_AUTOMATION_RULES = "write:automation_rules"

PERM_READ_BUSINESS_PROFILE = "read:business_profile"
PERM_WRITE_BUSINESS_PROFILE = "write:business_profile"

PERM_READ_DNC = "read:do_not_contact"
PERM_WRITE_DNC = "write:do_not_contact"

# NEW-216, 2026-08-27: schedule_config (business hours / booking defaults,
# mirrors Aigentik-CLI's schedule-config.json) is operational settings, not
# identity/onboarding like business_profile, so it gets its own pair rather
# than reusing PERM_READ/WRITE_BUSINESS_PROFILE -- keeping the one-pair-per-
# table convention this round's other five tables established avoids a
# future "give sales read access to business hours" change silently also
# granting business-profile writes.
PERM_READ_SCHEDULE_CONFIG = "read:schedule_config"
PERM_WRITE_SCHEDULE_CONFIG = "write:schedule_config"

# Contacts permissions (Track B Phase B2 cutover)
PERM_READ_CONTACTS = "read:contacts"
PERM_WRITE_CONTACTS = "write:contacts"

# Role permissions matrix
ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    ROLE_ADMIN: {
        PERM_READ_ALL_CUSTOMERS,
        PERM_WRITE_CUSTOMERS,
        PERM_READ_LEADS,
        PERM_WRITE_LEADS,
        PERM_READ_OPPORTUNITIES,
        PERM_WRITE_OPPORTUNITIES,
        PERM_READ_ALL_PROJECTS,
        PERM_WRITE_PROJECTS,
        PERM_READ_ESTIMATES,
        PERM_WRITE_ESTIMATES,
        PERM_READ_CONTRACTS,
        PERM_WRITE_CONTRACTS,
        PERM_SIGN_CONTRACTS,
        PERM_READ_DOCUMENTS,
        PERM_WRITE_DOCUMENTS,
        PERM_READ_FINANCIALS,
        PERM_WRITE_FINANCIALS,
        PERM_LOG_COMMUNICATION,
        PERM_READ_COMMUNICATIONS,
        PERM_READ_AUDIT_LOG,
        PERM_MANAGE_USERS,
        PERM_READ_SUBCONTRACTORS,
        PERM_WRITE_SUBCONTRACTORS,
        PERM_READ_APPOINTMENTS,
        PERM_WRITE_APPOINTMENTS,
        PERM_READ_AUTOMATION_RULES,
        PERM_WRITE_AUTOMATION_RULES,
        PERM_READ_BUSINESS_PROFILE,
        PERM_WRITE_BUSINESS_PROFILE,
        PERM_READ_SCHEDULE_CONFIG,
        PERM_WRITE_SCHEDULE_CONFIG,
        PERM_READ_DNC,
        PERM_WRITE_DNC,
        PERM_READ_CONTACTS,
        PERM_WRITE_CONTACTS,
    },
    ROLE_MANAGER: {
        PERM_READ_ALL_CUSTOMERS,
        PERM_WRITE_CUSTOMERS,
        PERM_READ_LEADS,
        PERM_WRITE_LEADS,
        PERM_READ_OPPORTUNITIES,
        PERM_WRITE_OPPORTUNITIES,
        PERM_READ_ALL_PROJECTS,
        PERM_WRITE_PROJECTS,
        PERM_READ_ESTIMATES,
        PERM_WRITE_ESTIMATES,
        PERM_READ_CONTRACTS,
        PERM_WRITE_CONTRACTS,
        PERM_SIGN_CONTRACTS,
        PERM_READ_DOCUMENTS,
        PERM_WRITE_DOCUMENTS,
        PERM_READ_FINANCIALS,
        PERM_WRITE_FINANCIALS,
        PERM_LOG_COMMUNICATION,
        PERM_READ_COMMUNICATIONS,
        PERM_READ_AUDIT_LOG,
        PERM_READ_SUBCONTRACTORS,
        PERM_WRITE_SUBCONTRACTORS,
        PERM_READ_APPOINTMENTS,
        PERM_WRITE_APPOINTMENTS,
        PERM_READ_AUTOMATION_RULES,
        PERM_WRITE_AUTOMATION_RULES,
        PERM_READ_BUSINESS_PROFILE,
        PERM_WRITE_BUSINESS_PROFILE,
        PERM_READ_SCHEDULE_CONFIG,
        PERM_WRITE_SCHEDULE_CONFIG,
        PERM_READ_DNC,
        PERM_WRITE_DNC,
        PERM_READ_CONTACTS,
        PERM_WRITE_CONTACTS,
    },
    ROLE_SALES: {
        PERM_READ_ALL_CUSTOMERS,
        PERM_WRITE_CUSTOMERS,
        PERM_READ_LEADS,
        PERM_WRITE_LEADS,
        PERM_READ_OPPORTUNITIES,
        PERM_WRITE_OPPORTUNITIES,
        PERM_READ_ALL_PROJECTS,
        PERM_READ_ESTIMATES,
        PERM_WRITE_ESTIMATES,
        PERM_READ_CONTRACTS,
        PERM_WRITE_CONTRACTS,
        PERM_SIGN_CONTRACTS,
        PERM_READ_DOCUMENTS,
        PERM_WRITE_DOCUMENTS,
        PERM_LOG_COMMUNICATION,
        PERM_READ_COMMUNICATIONS,
        PERM_READ_SUBCONTRACTORS,
        PERM_READ_APPOINTMENTS,
        PERM_WRITE_APPOINTMENTS,
        PERM_READ_AUTOMATION_RULES,
        PERM_READ_DNC,
        PERM_READ_CONTACTS,
        PERM_WRITE_CONTACTS,
    },
    ROLE_PROJECT_MANAGER: {
        PERM_READ_ALL_CUSTOMERS,
        PERM_READ_ALL_PROJECTS,
        PERM_WRITE_PROJECTS,
        PERM_READ_ESTIMATES,
        PERM_READ_CONTRACTS,
        PERM_SIGN_CONTRACTS,
        PERM_READ_DOCUMENTS,
        PERM_WRITE_DOCUMENTS,
        PERM_READ_FINANCIALS,
        PERM_LOG_COMMUNICATION,
        PERM_READ_COMMUNICATIONS,
        PERM_READ_SUBCONTRACTORS,
        PERM_WRITE_SUBCONTRACTORS,
        PERM_READ_APPOINTMENTS,
        PERM_WRITE_APPOINTMENTS,
        PERM_READ_AUTOMATION_RULES,
        PERM_READ_DNC,
        PERM_READ_CONTACTS,
        PERM_WRITE_CONTACTS,
    },
    ROLE_TECHNICIAN: {
        PERM_READ_ASSIGNED_PROJECTS,
        PERM_READ_DOCUMENTS,
        PERM_WRITE_DOCUMENTS,
        PERM_LOG_COMMUNICATION,
    },
    ROLE_AI_AGENT: {
        PERM_READ_ALL_CUSTOMERS,
        PERM_WRITE_CUSTOMERS,
        PERM_READ_LEADS,
        PERM_WRITE_LEADS,
        PERM_READ_OPPORTUNITIES,
        PERM_WRITE_OPPORTUNITIES,
        PERM_READ_ALL_PROJECTS,
        PERM_READ_ESTIMATES,
        PERM_READ_CONTRACTS,
        PERM_READ_DOCUMENTS,
        PERM_WRITE_DOCUMENTS,
        PERM_READ_FINANCIALS,
        PERM_WRITE_FINANCIALS,
        PERM_LOG_COMMUNICATION,
        PERM_READ_COMMUNICATIONS,
        # ai_agent is the actor identity Codey-Aigentik authenticates as
        # once B2's write-through replacement lands (§6.4) -- it needs
        # full read/write on exactly the modules it owns today.
        PERM_READ_SUBCONTRACTORS,
        PERM_WRITE_SUBCONTRACTORS,
        PERM_READ_APPOINTMENTS,
        PERM_WRITE_APPOINTMENTS,
        PERM_READ_AUTOMATION_RULES,
        PERM_WRITE_AUTOMATION_RULES,
        PERM_READ_BUSINESS_PROFILE,
        PERM_WRITE_BUSINESS_PROFILE,
        PERM_READ_SCHEDULE_CONFIG,
        PERM_WRITE_SCHEDULE_CONFIG,
        PERM_READ_DNC,
        PERM_WRITE_DNC,
        PERM_READ_CONTACTS,
        PERM_WRITE_CONTACTS,
    },
    ROLE_CUSTOMER: {
        PERM_READ_OWN_CUSTOMER,
        PERM_READ_OWN_PROJECTS,
        PERM_READ_OWN_ESTIMATES,
        PERM_READ_OWN_CONTRACTS,
        PERM_SIGN_CONTRACTS,
        PERM_READ_OWN_DOCUMENTS,
        PERM_READ_OWN_FINANCIALS,
        PERM_READ_OWN_COMMUNICATIONS,
        PERM_LOG_COMMUNICATION,
    },
}


@dataclass
class AuthContext:
    """Represents authenticated caller identity and permissions."""
    user_id: int
    username: str
    role: str
    actor_type: str  # 'human' or 'agent'
    customer_id: Optional[int] = None
    token: Optional[str] = None

    def has_permission(self, permission: str) -> bool:
        """Check if role grants specific permission."""
        perms = ROLE_PERMISSIONS.get(self.role, set())
        return permission in perms

    def can_access_customer(self, target_customer_id: int) -> bool:
        """Enforce strict isolation for customer roles."""
        if self.role == ROLE_CUSTOMER:
            return self.customer_id is not None and self.customer_id == target_customer_id
        return self.has_permission(PERM_READ_ALL_CUSTOMERS)


class AuthService:
    """Handles password hashing, token creation, validation, and user management."""

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a plain password using PBKDF2-HMAC-SHA256 with random salt."""
        salt = os.urandom(SALT_BYTES)
        hash_bytes = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, HASH_ITERATIONS)
        return f"pbkdf2_sha256${HASH_ITERATIONS}${salt.hex()}${hash_bytes.hex()}"

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify password against stored PBKDF2 hash using constant-time comparison."""
        try:
            algorithm, iterations_str, salt_hex, expected_hash_hex = hashed_password.split("$")
            if algorithm != "pbkdf2_sha256":
                return False
            iterations = int(iterations_str)
            salt = bytes.fromhex(salt_hex)
            expected_hash = bytes.fromhex(expected_hash_hex)
            actual_hash = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, iterations)
            return hmac.compare_digest(actual_hash, expected_hash)
        except Exception:
            return False

    def create_user(
        self,
        username: str,
        plain_password: str,
        full_name: str,
        email: str,
        role: str,
        phone: Optional[str] = None,
        department: Optional[str] = None,
        customer_id: Optional[int] = None,
        actor_context: Optional[AuthContext] = None,
    ) -> User:
        """Create a new user with hashed credentials."""
        if role not in ALL_ROLES:
            raise ValueError(f"Invalid role '{role}'. Must be one of {sorted(ALL_ROLES)}")

        if role == ROLE_CUSTOMER and customer_id is None:
            raise ValueError("Customer user role requires an associated customer_id")

        if actor_context and not actor_context.has_permission(PERM_MANAGE_USERS):
            raise PermissionError("Actor lacks permission to create users")

        now = utc_now_iso()
        password_hash = self.hash_password(plain_password)

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO users (
                    username, password_hash, full_name, email, phone, role,
                    department, customer_id, active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?);
                """,
                (
                    username.strip().lower(),
                    password_hash,
                    full_name.strip(),
                    email.strip().lower(),
                    phone,
                    role,
                    department,
                    customer_id,
                    now,
                    now,
                ),
            )
            user_id = cursor.lastrowid

        return User(
            id=user_id,
            username=username.strip().lower(),
            password_hash=password_hash,
            full_name=full_name.strip(),
            email=email.strip().lower(),
            phone=phone,
            role=role,
            department=department,
            customer_id=customer_id,
            active=1,
            created_at=now,
            updated_at=now,
        )

    def authenticate_user(self, username_or_email: str, plain_password: str) -> Optional[User]:
        """Verify user credentials and return User if valid and active."""
        conn = self.db.get_connection()
        row = conn.execute(
            """
            SELECT * FROM users
            WHERE (username = ? OR email = ?) AND active = 1;
            """,
            (username_or_email.strip().lower(), username_or_email.strip().lower()),
        ).fetchone()

        if not row:
            return None

        if not self.verify_password(plain_password, row["password_hash"]):
            return None

        return User(
            id=row["id"],
            username=row["username"],
            password_hash=row["password_hash"],
            full_name=row["full_name"],
            email=row["email"],
            phone=row["phone"],
            role=row["role"],
            department=row["department"],
            customer_id=row["customer_id"],
            active=row["active"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def create_token(self, user: User, expires_in_days: int = TOKEN_EXPIRY_DAYS) -> str:
        """Issue a cryptographically secure session token."""
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = (now + timedelta(days=expires_in_days)).isoformat()

        conn = self.db.get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO api_tokens (token, user_id, role, created_at, expires_at, is_revoked)
                VALUES (?, ?, ?, ?, ?, 0);
                """,
                (token, user.id, user.role, now.isoformat(), expires_at),
            )
        return token

    def authenticate_token(self, token: str) -> Optional[AuthContext]:
        """Validate token and return AuthContext if active and not expired."""
        if not token:
            return None

        conn = self.db.get_connection()
        row = conn.execute(
            """
            SELECT t.token, t.user_id, t.role, t.expires_at, t.is_revoked,
                   u.username, u.customer_id, u.active
            FROM api_tokens t
            JOIN users u ON t.user_id = u.id
            WHERE t.token = ? AND t.is_revoked = 0 AND u.active = 1;
            """,
            (token,),
        ).fetchone()

        if not row:
            return None

        # Check expiration
        expires_at = datetime.fromisoformat(row["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            return None

        actor_type = "agent" if row["role"] == ROLE_AI_AGENT else "human"
        return AuthContext(
            user_id=row["user_id"],
            username=row["username"],
            role=row["role"],
            actor_type=actor_type,
            customer_id=row["customer_id"],
            token=token,
        )

    def revoke_token(self, token: str) -> bool:
        """Revoke an active API token."""
        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                "UPDATE api_tokens SET is_revoked = 1 WHERE token = ?;",
                (token,),
            )
            return cursor.rowcount > 0

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Retrieve user by ID."""
        conn = self.db.get_connection()
        row = conn.execute("SELECT * FROM users WHERE id = ?;", (user_id,)).fetchone()
        if not row:
            return None
        return User(
            id=row["id"],
            username=row["username"],
            password_hash=row["password_hash"],
            full_name=row["full_name"],
            email=row["email"],
            phone=row["phone"],
            role=row["role"],
            department=row["department"],
            customer_id=row["customer_id"],
            active=row["active"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
