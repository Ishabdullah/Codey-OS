"""
Authentication, Session Token Management, and Role-Based Access Control (RBAC)
for Restoricon Core.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

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
ROLE_SALES_MANAGER = "sales_manager"
ROLE_PROJECT_MANAGER = "project_manager"
ROLE_TECHNICIAN = "technician"
ROLE_AI_AGENT = "ai_agent"
ROLE_CUSTOMER = "customer"
# Phase 0b, B8.16 (2026-09-27): a subcontractor's own login, not the
# `subcontractors` table row itself (which pre-dates this role and has no
# login of its own). Deliberately narrower than ROLE_TECHNICIAN -- see
# ROLE_PERMISSIONS[ROLE_SUBCONTRACTOR] below for the exact subset and why.
ROLE_SUBCONTRACTOR = "subcontractor"

ALL_ROLES = {
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_SALES,
    ROLE_SALES_MANAGER,
    ROLE_PROJECT_MANAGER,
    ROLE_TECHNICIAN,
    ROLE_AI_AGENT,
    ROLE_CUSTOMER,
    ROLE_SUBCONTRACTOR,
}

# B8.16 Phase 4 (NEW-680, 2026-09-29): the first place in this codebase
# that codifies which roles are legitimate holders of a sales-attribution
# user id (e.g. Customer.assigned_user_id / submit_work_order_intake's
# salesperson_user_id). Verified directly: neither
# CRMService.submit_work_order_intake nor CommissionService validates the
# role behind an assigned_user_id today -- this constant doesn't change
# that (out of scope here, logged separately as NEW-682), it only scopes
# AuthService.list_salesperson_roster's read so the picker it powers
# doesn't offer every active user in the system, just the roles this
# business's sales/commission workflow already treats as real sales
# attribution owners. ROLE_ADMIN/ROLE_MANAGER included because an
# owner/manager legitimately sells jobs directly in this business, not
# just ROLE_SALES/ROLE_SALES_MANAGER. Deliberately excludes
# ROLE_PROJECT_MANAGER, ROLE_TECHNICIAN, ROLE_SUBCONTRACTOR, ROLE_CUSTOMER,
# ROLE_AI_AGENT.
SALES_ATTRIBUTION_ROLES = {
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_SALES,
    ROLE_SALES_MANAGER,
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

# B8.12a, 2026-09-24: replaces PERM_READ_ALL_PROJECTS/PERM_READ_OPERATIONS on
# ROLE_SALES, which were flat, company-wide over-grants with zero per-row
# ownership check anywhere in crm_service.py/operations_service.py (NEW-628).
# Narrowed to projects a rep actually sold: crm_service.py/
# operations_service.py filter to rows where a `contracts` row exists with
# matching project_id AND assigned_user_id == actor.user_id.
# assigned_user_id IS NULL (an unclaimed contract) is DENIED, not treated as
# visible -- deliberately different from the leads/opportunities
# unclaimed-pool leniency (_scoped_assignee_filter), since granting an
# unclaimed project to every rep would recreate the exact over-grant this
# permission replaces. A rep additionally holding PERM_READ_TEAM_SALES_DATA
# (i.e. ROLE_SALES_MANAGER, via its derived-permissions union below) bypasses
# the ownership filter entirely and keeps full visibility, same team-wide
# semantics as every other PERM_READ_TEAM_SALES_DATA narrowing in this file.
PERM_READ_OWN_SOLD_PROJECTS = "read:own_sold_projects"

# NEW-533, 2026-09-16 (permission introduced); D2, sales_rep_portal.md §4,
# Ish-approved, 2026-09-16 (real ROLE_SALES_MANAGER role added on top).
# Holding PERM_READ_TEAM_SALES_DATA lets an actor see every rep's leads,
# opportunities, and tasks, not just their own assigned_user_id -- without
# it, a `sales` (or `project_manager`, which also holds PERM_READ_CRM/
# PERM_WRITE_CRM) actor is narrowed to their own assignments plus the
# unclaimed pool. Default-granted to admin/manager/ai_agent so none of them
# regress below their current unrestricted CRM read; deliberately withheld
# from sales/project_manager/technician/customer by default. Note
# ROLE_PROJECT_MANAGER is narrowed by this fix too, not just ROLE_SALES --
# a deliberate, in-scope side effect per Ish's own framing of the ask, not
# an accidental regression.
#
# Two ways to grant it, both still live:
#   1. ROLE_SALES_MANAGER (D2): a real, separate role -- see
#      ROLE_PERMISSIONS[ROLE_SALES_MANAGER] below, granted this permission
#      by default (plus everything ROLE_SALES already has). Use this when
#      the actor should permanently act as a sales manager.
#   2. The original NEW-533 mechanism: grant PERM_READ_TEAM_SALES_DATA to
#      an ordinary `sales`-role (or any other role's) user directly via
#      that user's `custom_permissions` override, with no role change.
#      This general-purpose per-user override stays available for any
#      other one-off grant -- it is not superseded or removed by (1).
PERM_READ_TEAM_SALES_DATA = "read:team_sales_data"

# B8.1, D4 (sales_rep_portal.md §4, Ish-approved 2026-09-16). Genuinely
# separate from PERM_READ_TEAM_SALES_DATA above, not implied by it:
# PERM_READ_TEAM_SALES_DATA governs pipeline visibility (leads,
# opportunities, tasks), which is operational data a sales manager needs
# to run a team day-to-day. Commission ledger rows are compensation --
# financial data an actor may legitimately need team-pipeline visibility
# for without also being entitled to see what every rep is being paid.
# Financial data warrants its own gate even for someone who already sees
# team pipeline -- this mirrors why PERM_SIGN_CONTRACTS is split from
# PERM_WRITE_CONTRACTS (being able to edit a contract's terms doesn't
# imply authority to execute a signature on it). Holding
# PERM_READ_TEAM_COMMISSIONS lets an actor read (and, per
# CommissionService's minimal write gate, record/reverse) any rep's
# commission ledger rows, not just rows where rep_user_id == their own
# user_id. Default-granted to admin/manager/ai_agent (ROLE_PERMISSIONS
# below) and to ROLE_SALES_MANAGER (see its derived-permissions line
# further down), same set that holds PERM_READ_TEAM_SALES_DATA today.
# Deliberately withheld from sales/project_manager/technician/customer by
# default -- an ordinary sales rep may read/have recorded their own
# commission rows (CommissionService narrows to rep_user_id == actor.user_id
# without this permission) but not another rep's.
PERM_READ_TEAM_COMMISSIONS = "read:team_commissions"

# code-reviewer round 2 (B8.1): split from PERM_READ_TEAM_COMMISSIONS
# above, following the exact PERM_SIGN_CONTRACTS / PERM_WRITE_CONTRACTS
# precedent this same comment block already cites -- being able to see
# every rep's commissions does not imply authority to author or reverse
# money-moving ledger rows (CommissionService.record_commission /
# reverse_commission). Granted to the identical default set as the read
# permission (admin/manager/ai_agent, plus ROLE_SALES_MANAGER via its
# derived-permissions line further down) so no default-role behavior
# changes; this only matters the day a role or custom_permissions_json
# grant holds read without write.
PERM_WRITE_TEAM_COMMISSIONS = "write:team_commissions"

# B6.1, 2026-09-02: reassigning the PM, employees, or subcontractors
# on an existing project is split from ordinary project edits into two
# additive permissions, mirroring the PERM_SIGN_CONTRACTS / NEW-192 scoped-vs-
# unrestricted precedent. PERM_REASSIGN_PROJECT_STAFF is the scoped grant --
# the holder may reassign staff only on projects where they are the
# project_manager_id. PERM_REASSIGN_ANY_PROJECT_STAFF is the unrestricted
# grant -- reassign on any project regardless of ownership. admin/manager
# hold both; project_manager holds only the scoped one; sales, technician,
# and customer hold neither. ai_agent holds neither -- a placeholder policy
# exactly like PERM_SIGN_CONTRACTS, pending Ish's real rule for what an
# autonomous agent may reassign; revisit when that policy is settled.
# PERM_MANAGE_PROJECTS already sits with project_manager, so it cannot be
# the "unrestricted reassign" discriminator -- hence these two new perms.
# Deliberately no implication logic: PERM_MANAGE_PROJECTS / PERM_WRITE_PROJECTS
# do NOT imply either of these.
PERM_REASSIGN_PROJECT_STAFF = "reassign:project_staff"
PERM_REASSIGN_ANY_PROJECT_STAFF = "reassign:any_project_staff"

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

# Final scheduling round Phase 2: appointment_types (the "service type" axis
# -- Emergency / Standard estimate / Consultation -- that Phase 4's
# concurrency enforcement reads). Own pair rather than reusing
# PERM_*_SCHEDULE_CONFIG: writing a service type is business-config work
# (create/rename/deactivate a bookable offering), whereas ROLE_AI_AGENT
# needs only to *read* caps/hours to offer slots. Reusing the config pair
# would have handed the agent create/rename/deactivate power over business
# service types.
PERM_READ_APPOINTMENT_TYPES = "read:appointment_types"
PERM_WRITE_APPOINTMENT_TYPES = "write:appointment_types"

PERM_READ_STAFF_SCHEDULES = "read:staff_schedules"
PERM_WRITE_STAFF_SCHEDULES = "write:staff_schedules"

# NEW-547: a narrow, self-only tier of PERM_READ_STAFF_SCHEDULES, distinct
# from it -- granting the full permission to ROLE_SALES would hand every
# sales rep company-wide staff-schedule visibility via direct API calls,
# not just what the sales portal's "My Schedule" panel displays. Holders
# of this permission alone are forced to their own user_id in
# list_staff_schedules/get_staff_schedule regardless of what they request
# (see SchedulingService); get_active_staff_schedules_for_user and
# list_staff_schedules_archive deliberately stay gated on the FULL
# permission only -- this narrow tier does not unlock either of them.
PERM_READ_OWN_STAFF_SCHEDULE = "read:own_staff_schedule"

# Contacts permissions (Track B Phase B2 cutover)
PERM_READ_CONTACTS = "read:contacts"
PERM_WRITE_CONTACTS = "write:contacts"

# CRM & Sales Domain permissions (Track B Phase B3)
PERM_READ_CRM = "read:crm"
PERM_WRITE_CRM = "write:crm"
PERM_MANAGE_PIPELINE = "manage:pipeline"
PERM_SCORE_LEADS = "score:leads"

# B8.9a: territory management -- defining what territories EXIST (create/
# rename/edit the lookup table itself) is an operational/admin decision,
# same class as appointment_types (own dedicated read/write pair, not a
# reuse of PERM_MANAGE_USERS -- that permission is admin-only and cannot
# express a read/write split, and territory names need to be readable by
# a broader tier than "can manage user accounts" the moment any rep-
# facing surface lists them). Assigning a territory_id TO a user/lead/
# customer is NOT gated by this pair -- that's already covered by the
# existing PERM_MANAGE_USERS (users.territory_id via update_user) and
# PERM_WRITE_LEADS/PERM_WRITE_CUSTOMERS (leads/customers.territory_id via
# update_lead/update_customer) gates on those write paths.
PERM_READ_TERRITORIES = "read:territories"
PERM_WRITE_TERRITORIES = "write:territories"

# Operations Domain permissions (Track B Phase B3)
PERM_READ_OPERATIONS = "read:operations"
PERM_WRITE_OPERATIONS = "write:operations"
PERM_MANAGE_PROJECTS = "manage:projects"
PERM_DISPATCH_WORK_ORDERS = "dispatch:work_orders"

# B8.16 Phase 4 (NEW-680, 2026-09-29, Ish decision): a deliberately narrow
# permission for AuthService.list_salesperson_roster -- returns ONLY
# {id, name} pairs for users in SALES_ATTRIBUTION_ROLES below, never a
# full User record (no email/phone/role/permissions). This exists
# specifically so ROLE_TECHNICIAN/ROLE_SUBCONTRACTOR can populate the
# work-order-intake form's salesperson picker without holding
# PERM_MANAGE_USERS, which would repeat the exact over-grant shape
# code-reviewer already removed twice this phase (NEW-668/NEW-669: a
# broad read grant handing an external party company-wide data). Not
# reusing PERM_READ_TEAM_SALES_DATA -- that permission is treated as an
# ownership-narrowing BYPASS by every B8.12a-era filter branch in
# crm_service.py/operations_service.py (verified directly, not assumed),
# so granting it here would hand technician/subcontractor actors
# team-wide pipeline reads, a strictly worse over-grant than the numeric-
# id input it replaces.
PERM_READ_SALESPERSON_ROSTER = "read:salesperson_roster"

# Phase B5a Domain Permissions
PERM_READ_FINANCE = "read:finance"
PERM_WRITE_FINANCE = "write:finance"
PERM_READ_MARKETING = "read:marketing"
PERM_WRITE_MARKETING = "write:marketing"
PERM_READ_COMPLIANCE = "read:compliance"
PERM_WRITE_COMPLIANCE = "write:compliance"
PERM_READ_HR = "read:hr"
PERM_WRITE_HR = "write:hr"
PERM_READ_PROCUREMENT = "read:procurement"
PERM_WRITE_PROCUREMENT = "write:procurement"
PERM_GLOBAL_SEARCH = "search:global"
PERM_VIEW_REPORTS = "view:reports"

# Role permissions matrix
ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    ROLE_ADMIN: {
        PERM_READ_ALL_CUSTOMERS,
        PERM_WRITE_CUSTOMERS,
        PERM_READ_LEADS,
        PERM_WRITE_LEADS,
        PERM_READ_OPPORTUNITIES,
        PERM_WRITE_OPPORTUNITIES,
        PERM_READ_CRM,
        PERM_WRITE_CRM,
        PERM_MANAGE_PIPELINE,
        PERM_SCORE_LEADS,
        PERM_READ_TEAM_SALES_DATA,
        PERM_READ_TEAM_COMMISSIONS,
        PERM_WRITE_TEAM_COMMISSIONS,
        PERM_READ_ALL_PROJECTS,
        PERM_WRITE_PROJECTS,
        PERM_REASSIGN_PROJECT_STAFF,
        PERM_REASSIGN_ANY_PROJECT_STAFF,
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
        PERM_READ_APPOINTMENT_TYPES,
        PERM_WRITE_APPOINTMENT_TYPES,
        PERM_READ_STAFF_SCHEDULES,
        PERM_WRITE_STAFF_SCHEDULES,
        PERM_READ_DNC,
        PERM_WRITE_DNC,
        PERM_READ_CONTACTS,
        PERM_WRITE_CONTACTS,
        PERM_READ_OPERATIONS,
        PERM_WRITE_OPERATIONS,
        PERM_MANAGE_PROJECTS,
        PERM_DISPATCH_WORK_ORDERS,
        PERM_READ_FINANCE,
        PERM_WRITE_FINANCE,
        PERM_READ_MARKETING,
        PERM_WRITE_MARKETING,
        PERM_READ_COMPLIANCE,
        PERM_WRITE_COMPLIANCE,
        PERM_READ_HR,
        PERM_WRITE_HR,
        PERM_READ_PROCUREMENT,
        PERM_WRITE_PROCUREMENT,
        PERM_GLOBAL_SEARCH,
        PERM_VIEW_REPORTS,
        PERM_READ_TERRITORIES,
        PERM_WRITE_TERRITORIES,
    },
    ROLE_MANAGER: {
        PERM_READ_ALL_CUSTOMERS,
        PERM_WRITE_CUSTOMERS,
        PERM_READ_LEADS,
        PERM_WRITE_LEADS,
        PERM_READ_OPPORTUNITIES,
        PERM_WRITE_OPPORTUNITIES,
        PERM_READ_CRM,
        PERM_WRITE_CRM,
        PERM_MANAGE_PIPELINE,
        PERM_SCORE_LEADS,
        PERM_READ_TEAM_SALES_DATA,
        PERM_READ_TEAM_COMMISSIONS,
        PERM_WRITE_TEAM_COMMISSIONS,
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
        PERM_REASSIGN_PROJECT_STAFF,
        PERM_REASSIGN_ANY_PROJECT_STAFF,
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
        PERM_READ_APPOINTMENT_TYPES,
        PERM_WRITE_APPOINTMENT_TYPES,
        PERM_READ_STAFF_SCHEDULES,
        PERM_WRITE_STAFF_SCHEDULES,
        PERM_READ_DNC,
        PERM_WRITE_DNC,
        PERM_READ_CONTACTS,
        PERM_WRITE_CONTACTS,
        PERM_READ_OPERATIONS,
        PERM_WRITE_OPERATIONS,
        PERM_MANAGE_PROJECTS,
        PERM_DISPATCH_WORK_ORDERS,
        PERM_READ_FINANCE,
        PERM_WRITE_FINANCE,
        PERM_READ_MARKETING,
        PERM_WRITE_MARKETING,
        PERM_READ_COMPLIANCE,
        PERM_WRITE_COMPLIANCE,
        PERM_READ_HR,
        PERM_WRITE_HR,
        PERM_READ_PROCUREMENT,
        PERM_WRITE_PROCUREMENT,
        PERM_GLOBAL_SEARCH,
        PERM_VIEW_REPORTS,
        PERM_READ_TERRITORIES,
        PERM_WRITE_TERRITORIES,
    },
    ROLE_SALES: {
        PERM_READ_ALL_CUSTOMERS,
        PERM_WRITE_CUSTOMERS,
        PERM_READ_LEADS,
        PERM_WRITE_LEADS,
        PERM_READ_OPPORTUNITIES,
        PERM_WRITE_OPPORTUNITIES,
        PERM_READ_CRM,
        PERM_WRITE_CRM,
        PERM_MANAGE_PIPELINE,
        PERM_SCORE_LEADS,
        # B8.12a, 2026-09-24 (NEW-628): PERM_READ_ALL_PROJECTS and
        # PERM_READ_OPERATIONS were removed from here -- both were flat,
        # company-wide over-grants with zero per-row ownership check,
        # letting any sales rep read every project/work order/equipment
        # deployment in the company. Replaced with PERM_READ_OWN_SOLD_PROJECTS
        # (see its definition above), which crm_service.py/
        # operations_service.py narrow to projects the rep actually sold via
        # a matching Contract row. This also intentionally denies ROLE_SALES
        # get_equipment/list_equipment/deploy_equipment/return_equipment/
        # list_project_deployments/get_active_work_orders_for_subcontractor/
        # match_subcontractors_for_trade -- none of those had a legitimate
        # sales-rep use case and PERM_READ_OWN_SOLD_PROJECTS does not cover
        # them; this is the intended narrowing outcome, not a gap.
        PERM_READ_OWN_SOLD_PROJECTS,
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
        PERM_READ_MARKETING,
        PERM_WRITE_MARKETING,
        PERM_READ_PROCUREMENT,
        PERM_GLOBAL_SEARCH,
        PERM_VIEW_REPORTS,
        # NEW-565, 2026-09-18 (Ish): sales reps need to see a customer's
        # invoices on the Customer 360 panel; verified this only gates
        # list_invoices/get_invoice in crm_service.py, nothing else.
        PERM_READ_FINANCIALS,
        # NEW-547: self-only staff-schedule visibility for the sales
        # portal's "My Schedule" panel -- NOT the full company-wide
        # PERM_READ_STAFF_SCHEDULES (that stays admin/manager/PM/ai_agent
        # only, see below).
        PERM_READ_OWN_STAFF_SCHEDULE,
    },
    ROLE_PROJECT_MANAGER: {
        PERM_READ_ALL_CUSTOMERS,
        PERM_READ_CRM,
        PERM_WRITE_CRM,
        PERM_MANAGE_PIPELINE,
        PERM_READ_ALL_PROJECTS,
        PERM_WRITE_PROJECTS,
        PERM_REASSIGN_PROJECT_STAFF,
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
        PERM_READ_STAFF_SCHEDULES,
        PERM_WRITE_STAFF_SCHEDULES,
        PERM_READ_DNC,
        PERM_READ_CONTACTS,
        PERM_WRITE_CONTACTS,
        PERM_READ_OPERATIONS,
        PERM_WRITE_OPERATIONS,
        PERM_MANAGE_PROJECTS,
        PERM_DISPATCH_WORK_ORDERS,
        PERM_READ_FINANCE,
        PERM_READ_COMPLIANCE,
        PERM_WRITE_COMPLIANCE,
        PERM_READ_HR,
        PERM_READ_PROCUREMENT,
        PERM_WRITE_PROCUREMENT,
        PERM_GLOBAL_SEARCH,
        PERM_VIEW_REPORTS,
    },
    ROLE_TECHNICIAN: {
        PERM_READ_ASSIGNED_PROJECTS,
        PERM_READ_DOCUMENTS,
        PERM_WRITE_DOCUMENTS,
        PERM_LOG_COMMUNICATION,
        PERM_READ_OPERATIONS,
        PERM_WRITE_OPERATIONS,
        PERM_READ_HR,
        PERM_WRITE_HR,
        PERM_READ_COMPLIANCE,
        # NEW-680, B8.16 Phase 4: populates the work-order-intake form's
        # salesperson picker -- id+name only, see PERM_READ_SALESPERSON_ROSTER's
        # own definition above for why this is not PERM_MANAGE_USERS/
        # PERM_READ_TEAM_SALES_DATA.
        PERM_READ_SALESPERSON_ROSTER,
    },
    ROLE_AI_AGENT: {
        PERM_READ_ALL_CUSTOMERS,
        PERM_WRITE_CUSTOMERS,
        PERM_READ_LEADS,
        PERM_WRITE_LEADS,
        PERM_READ_OPPORTUNITIES,
        PERM_WRITE_OPPORTUNITIES,
        PERM_READ_CRM,
        PERM_WRITE_CRM,
        PERM_MANAGE_PIPELINE,
        PERM_SCORE_LEADS,
        PERM_READ_TEAM_SALES_DATA,
        PERM_READ_TEAM_COMMISSIONS,
        PERM_WRITE_TEAM_COMMISSIONS,
        PERM_READ_ALL_PROJECTS,
        PERM_READ_ESTIMATES,
        PERM_READ_CONTRACTS,
        PERM_READ_DOCUMENTS,
        PERM_WRITE_DOCUMENTS,
        PERM_READ_FINANCIALS,
        PERM_WRITE_FINANCIALS,
        PERM_LOG_COMMUNICATION,
        PERM_READ_COMMUNICATIONS,
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
        PERM_READ_APPOINTMENT_TYPES,
        PERM_READ_STAFF_SCHEDULES,
        PERM_WRITE_STAFF_SCHEDULES,
        PERM_READ_DNC,
        PERM_WRITE_DNC,
        PERM_READ_CONTACTS,
        PERM_WRITE_CONTACTS,
        PERM_READ_OPERATIONS,
        PERM_WRITE_OPERATIONS,
        PERM_MANAGE_PROJECTS,
        PERM_DISPATCH_WORK_ORDERS,
        PERM_READ_FINANCE,
        PERM_WRITE_FINANCE,
        PERM_READ_MARKETING,
        PERM_WRITE_MARKETING,
        PERM_READ_COMPLIANCE,
        PERM_WRITE_COMPLIANCE,
        PERM_READ_HR,
        PERM_READ_PROCUREMENT,
        PERM_WRITE_PROCUREMENT,
        PERM_GLOBAL_SEARCH,
        PERM_VIEW_REPORTS,
        # B8.9a: read-only, mirroring PERM_READ_APPOINTMENT_TYPES' own
        # ai_agent grant above -- the agent needs to read territory names
        # (e.g. to render them in a write-through payload) but authoring
        # what territories exist is an admin/manager decision.
        PERM_READ_TERRITORIES,
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
        PERM_GLOBAL_SEARCH,
    },
    # Phase 0b, B8.16 (2026-09-27): a deliberately narrower subset of
    # ROLE_TECHNICIAN's own grant (verified directly against the block
    # above, not assumed) -- a subcontractor is an external party engaged
    # per work order, not an employee. Included: PERM_READ_OPERATIONS/
    # PERM_WRITE_OPERATIONS (work order visibility, narrowed at the row
    # level to the subcontractor's own assigned_subcontractor_id by
    # OperationsService._actor_owns_work_order_via_subcontractor, mirroring
    # ROLE_TECHNICIAN's own _actor_assigned_to_project narrowing),
    # PERM_LOG_COMMUNICATION (log interactions). Explicitly excluded, never
    # grant without a separate, logged decision: PERM_READ_HR/PERM_WRITE_HR
    # (not an employee -- no personnel record), PERM_DISPATCH_WORK_ORDERS,
    # PERM_MANAGE_PROJECTS, PERM_WRITE_CUSTOMERS, PERM_WRITE_FINANCIALS,
    # (code-reviewer, 2026-09-27, NEW-668) PERM_READ_COMPLIANCE --
    # BusinessOpsService.list_compliance_items has zero entity-level
    # narrowing, so this permission would hand an external subcontractor
    # read access to every other party's license/insurance/COI records
    # company-wide, not the "their own status" the original grant's comment
    # claimed; it also gates scan_compliance_expirations, a write path --
    # and (code-reviewer round 2, 2026-09-27, NEW-669) PERM_READ_DOCUMENTS/
    # PERM_WRITE_DOCUMENTS -- CRMService.get_document/list_documents only
    # apply per-customer narrowing when the actor LACKS PERM_READ_DOCUMENTS
    # (the NEW-665 fix keys on `if not actor.has_permission(PERM_READ_DOCUMENTS)`),
    # so holding the broad permission skips narrowing entirely and would let
    # an external subcontractor read every customer's contracts/insurance
    # certs/ID scans/financial paperwork/photos in the system, including via
    # a raw-bytes download by id with no ownership check; create_document has
    # no role/entity check beyond PERM_WRITE_DOCUMENTS, so holding the write
    # side would let a subcontractor create a document row under any
    # customer_id/project_id. Does NOT hold PERM_READ_ASSIGNED_PROJECTS
    # (ROLE_TECHNICIAN's project-level read) -- a subcontractor's read access
    # is scoped to their own work orders, not full project detail.
    ROLE_SUBCONTRACTOR: {
        PERM_READ_OPERATIONS,
        PERM_WRITE_OPERATIONS,
        PERM_LOG_COMMUNICATION,
        # NEW-680, B8.16 Phase 4: same narrow salesperson-roster read as
        # ROLE_TECHNICIAN above -- id+name only, needed for this role's
        # own work-order-intake form.
        PERM_READ_SALESPERSON_ROSTER,
    },
}

# Granted by role default -- see D2, sales_rep_portal.md §4: a sales_manager
# is a real role (not the NEW-533 custom_permissions_json grant), but keeps
# exactly ROLE_SALES's permission set plus PERM_READ_TEAM_SALES_DATA, same
# as how ROLE_ADMIN/ROLE_MANAGER/ROLE_AI_AGENT already get it by default.
# Derived from ROLE_PERMISSIONS[ROLE_SALES] (not a duplicated literal list)
# so it can never drift out of sync if ROLE_SALES's set changes later.
# Deliberately NOT given PERM_REASSIGN_PROJECT_STAFF/
# PERM_REASSIGN_ANY_PROJECT_STAFF or PERM_MANAGE_USERS -- a sales manager
# manages sales reps' leads/opportunities/tasks, not project staffing or
# user accounts.
#
# B8.1, D4, 2026-09-16: also given PERM_READ_TEAM_COMMISSIONS by default,
# same as how admin/manager/ai_agent hold both team-visibility permissions
# together -- a sales manager who can see the whole team's pipeline is
# also expected to see the whole team's commissions (e.g. to verify a
# rep's payout against their own pipeline). Also given
# PERM_WRITE_TEAM_COMMISSIONS (code-reviewer round 2) -- a sales manager
# correcting a payout is exactly the role this write gate is meant for,
# same default set as the read permission it was split from.
#
# B8.12a, 2026-09-24: confirmed this union needs no change for
# get_project/get_milestone/list_milestones/get_work_order/
# list_work_orders and get_project_summary's project/milestone/work-order
# data -- PERM_READ_ALL_PROJECTS/PERM_READ_OPERATIONS were removed from
# ROLE_SALES and replaced with PERM_READ_OWN_SOLD_PROJECTS above. A manager
# inherits PERM_READ_OWN_SOLD_PROJECTS from ROLE_SALES (passing the
# crm_service.py/operations_service.py gate on those six methods) and
# independently holds PERM_READ_TEAM_SALES_DATA right here, which every
# ownership-filter branch B8.12a added treats as a bypass.
#
# NEW-630 (2026-09-25, Ish decision -- dd244d5): PERM_READ_OPERATIONS was
# re-granted to ROLE_SALES_MANAGER below. That was NOT an ownership-scoped
# re-grant -- PERM_READ_OPERATIONS is a flat, company-wide permission
# gating get_equipment/list_equipment/
# get_active_work_orders_for_subcontractor/match_subcontractors_for_trade/
# list_project_deployments in operations_service.py, and every one of
# NEW-628's ownership-narrowing branches on those methods keys
# specifically on `actor.role == ROLE_TECHNICIAN`, not on the permission
# itself. ROLE_SALES_MANAGER is not that role, so the 2026-09-25 grant was
# a full, org-wide read grant on equipment/deployment/subcontractor-
# matching data across every project, not one narrowed to the manager's
# own team's sold projects (unlike PERM_READ_OWN_SOLD_PROJECTS/
# PERM_READ_TEAM_SALES_DATA above, which are narrowed).
#
# NEW-630, superseded (2026-09-27, direct Ish decision): the 2026-09-25
# grant is reversed. PERM_READ_OPERATIONS is deliberately NOT included in
# ROLE_SALES_MANAGER's permission set below -- a sales manager gets no
# equipment/deployment/subcontractor-matching visibility, same as plain
# ROLE_SALES. get_project_summary's equipment_summary field goes back to
# returning None for a sales_manager actor (see L1875-ish's
# `PERM_READ_OPERATIONS or PERM_MANAGE_PROJECTS` gate on that field).
# deploy_equipment/return_equipment were never affected either way: both
# gate on PERM_WRITE_OPERATIONS or PERM_MANAGE_PROJECTS, neither of which
# this permission touches.
ROLE_PERMISSIONS[ROLE_SALES_MANAGER] = ROLE_PERMISSIONS[ROLE_SALES] | {
    PERM_READ_TEAM_SALES_DATA,
    PERM_READ_TEAM_COMMISSIONS,
    PERM_WRITE_TEAM_COMMISSIONS,
}

# Permissions catalog grouped by domain for dynamic permissions UI and validation
PERMISSIONS_CATALOG: Dict[str, Dict[str, Any]] = {
    "customers": {
        "title": "Customer Accounts",
        "description": "Manage and view customer records",
        "permissions": [
            {"id": PERM_READ_ALL_CUSTOMERS, "name": "Read All Customers", "description": "View all customer accounts"},
            {"id": PERM_WRITE_CUSTOMERS, "name": "Write Customers", "description": "Create and edit customer accounts"},
            {"id": PERM_READ_OWN_CUSTOMER, "name": "Read Own Customer", "description": "View own customer profile"},
        ],
    },
    "crm": {
        "title": "CRM, Leads & Pipeline",
        "description": "Sales pipeline, lead scoring, and opportunities",
        "permissions": [
            {"id": PERM_READ_LEADS, "name": "Read Leads", "description": "View incoming leads"},
            {"id": PERM_WRITE_LEADS, "name": "Write Leads", "description": "Create and edit leads"},
            {"id": PERM_READ_OPPORTUNITIES, "name": "Read Opportunities", "description": "View deal opportunities"},
            {"id": PERM_WRITE_OPPORTUNITIES, "name": "Write Opportunities", "description": "Create and edit opportunities"},
            {"id": PERM_READ_CRM, "name": "Read CRM", "description": "Access CRM overview"},
            {"id": PERM_WRITE_CRM, "name": "Write CRM", "description": "Manage CRM activities"},
            {"id": PERM_MANAGE_PIPELINE, "name": "Manage Pipeline", "description": "Move stages and configure pipeline"},
            {"id": PERM_SCORE_LEADS, "name": "Score Leads", "description": "Run lead qualification scoring"},
            {"id": PERM_READ_TEAM_SALES_DATA, "name": "Read Team Sales Data", "description": "See leads, opportunities, and tasks assigned to other sales reps, not just your own (sales manager view)"},
            {"id": PERM_READ_TEAM_COMMISSIONS, "name": "Read Team Commissions", "description": "See commission ledger entries for every sales rep, not just your own -- separate from Read Team Sales Data since compensation is more sensitive than pipeline visibility"},
            {"id": PERM_WRITE_TEAM_COMMISSIONS, "name": "Write Team Commissions", "description": "Record and reverse commission ledger entries -- separate from Read Team Commissions since seeing compensation data doesn't imply authority to author or reverse money-moving ledger rows"},
            {"id": PERM_READ_TERRITORIES, "name": "Read Territories", "description": "View the territory lookup list (name/code/notes)"},
            {"id": PERM_WRITE_TERRITORIES, "name": "Write Territories", "description": "Create and edit territory definitions -- separate from assigning a territory to a user/lead/customer, which is gated by that record's own write permission"},
        ],
    },
    "operations": {
        "title": "Field Operations & Projects",
        "description": "Projects, work orders, and drying fleet",
        "permissions": [
            {"id": PERM_READ_ALL_PROJECTS, "name": "Read All Projects", "description": "View all job sites and projects"},
            {"id": PERM_READ_OWN_SOLD_PROJECTS, "name": "Read Own Sold Projects", "description": "View projects, work orders, and status for jobs the actor personally sold (has a matching Contract), not the whole company's -- default sales-rep grant"},
            {"id": PERM_READ_ASSIGNED_PROJECTS, "name": "Read Assigned Projects", "description": "View assigned project jobs"},
            {"id": PERM_READ_OWN_PROJECTS, "name": "Read Own Projects", "description": "View own customer projects"},
            {"id": PERM_WRITE_PROJECTS, "name": "Write Projects", "description": "Create and update project records"},
            {"id": PERM_REASSIGN_PROJECT_STAFF, "name": "Reassign Project Staff (Own Projects)", "description": "Reassign the PM, employees, or subcontractors on projects where the actor is the project manager"},
            {"id": PERM_REASSIGN_ANY_PROJECT_STAFF, "name": "Reassign Project Staff (Any Project)", "description": "Reassign the PM, employees, or subcontractors on any project regardless of ownership"},
            {"id": PERM_MANAGE_PROJECTS, "name": "Manage Projects", "description": "Full project lifecycle management"},
            {"id": PERM_READ_OPERATIONS, "name": "Read Operations", "description": "View operations dashboard"},
            {"id": PERM_WRITE_OPERATIONS, "name": "Write Operations", "description": "Modify operational assets and equipment"},
            {"id": PERM_DISPATCH_WORK_ORDERS, "name": "Dispatch Work Orders", "description": "Assign and dispatch work orders"},
            {"id": PERM_READ_SALESPERSON_ROSTER, "name": "Read Salesperson Roster", "description": "See a narrow id+name-only list of users in sales-attribution-eligible roles, for populating a salesperson picker -- not the full user roster (Manage Users)"},
        ],
    },
    "estimates_contracts": {
        "title": "Estimates, Contracts & Documents",
        "description": "Scoping, agreements, and document repository",
        "permissions": [
            {"id": PERM_READ_ESTIMATES, "name": "Read Estimates", "description": "View project estimates"},
            {"id": PERM_WRITE_ESTIMATES, "name": "Write Estimates", "description": "Generate and revise estimates"},
            {"id": PERM_READ_OWN_ESTIMATES, "name": "Read Own Estimates", "description": "View own estimates in portal"},
            {"id": PERM_READ_CONTRACTS, "name": "Read Contracts", "description": "View contracts and agreements"},
            {"id": PERM_WRITE_CONTRACTS, "name": "Write Contracts", "description": "Generate and edit contracts"},
            {"id": PERM_SIGN_CONTRACTS, "name": "Sign Contracts", "description": "Execute digital signatures on contracts"},
            {"id": PERM_READ_OWN_CONTRACTS, "name": "Read Own Contracts", "description": "View own contracts in portal"},
            {"id": PERM_READ_DOCUMENTS, "name": "Read Documents", "description": "Access document repository"},
            {"id": PERM_WRITE_DOCUMENTS, "name": "Write Documents", "description": "Upload and manage documents"},
            {"id": PERM_READ_OWN_DOCUMENTS, "name": "Read Own Documents", "description": "Access customer portal documents"},
        ],
    },
    "finance": {
        "title": "Finance & Invoicing",
        "description": "Invoices, double-entry bookkeeping, AR aging",
        "permissions": [
            {"id": PERM_READ_FINANCIALS, "name": "Read Financials", "description": "View financial summary data"},
            {"id": PERM_WRITE_FINANCIALS, "name": "Write Financials", "description": "Post financial adjustments"},
            {"id": PERM_READ_OWN_FINANCIALS, "name": "Read Own Financials", "description": "View invoice balances in portal"},
            {"id": PERM_READ_FINANCE, "name": "Read Finance Domain", "description": "Full finance domain reading"},
            {"id": PERM_WRITE_FINANCE, "name": "Write Finance Domain", "description": "Full finance domain management"},
        ],
    },
    "communications": {
        "title": "Communications & Rules",
        "description": "Messaging history, automation triggers, DNC",
        "permissions": [
            {"id": PERM_LOG_COMMUNICATION, "name": "Log Communication", "description": "Log interactions and messages"},
            {"id": PERM_READ_COMMUNICATIONS, "name": "Read Communications", "description": "View complete communication log"},
            {"id": PERM_READ_OWN_COMMUNICATIONS, "name": "Read Own Communications", "description": "View own portal message thread"},
            {"id": PERM_READ_AUTOMATION_RULES, "name": "Read Automation Rules", "description": "View automated message rules"},
            {"id": PERM_WRITE_AUTOMATION_RULES, "name": "Write Automation Rules", "description": "Configure automated rules"},
            {"id": PERM_READ_DNC, "name": "Read Do Not Contact", "description": "View DNC suppression list"},
            {"id": PERM_WRITE_DNC, "name": "Write Do Not Contact", "description": "Manage DNC suppression list"},
        ],
    },
    "subcontractors_contacts": {
        "title": "Subcontractors & Contacts",
        "description": "Trade partner network and external contact sync",
        "permissions": [
            {"id": PERM_READ_SUBCONTRACTORS, "name": "Read Subcontractors", "description": "View trade partner network"},
            {"id": PERM_WRITE_SUBCONTRACTORS, "name": "Write Subcontractors", "description": "Onboard and edit subcontractors"},
            {"id": PERM_READ_CONTACTS, "name": "Read Contacts", "description": "View unified contact directory"},
            {"id": PERM_WRITE_CONTACTS, "name": "Write Contacts", "description": "Create and update contacts"},
        ],
    },
    "scheduling": {
        "title": "Scheduling & Operating Hours",
        "description": "Appointment calendar and booking rules",
        "permissions": [
            {"id": PERM_READ_APPOINTMENTS, "name": "Read Appointments", "description": "View scheduled appointments"},
            {"id": PERM_WRITE_APPOINTMENTS, "name": "Write Appointments", "description": "Book and reschedule appointments"},
            {"id": PERM_READ_SCHEDULE_CONFIG, "name": "Read Schedule Config", "description": "View booking availability rules"},
            {"id": PERM_WRITE_SCHEDULE_CONFIG, "name": "Write Schedule Config", "description": "Update booking parameters and hours"},
            {"id": PERM_READ_APPOINTMENT_TYPES, "name": "Read Appointment Types", "description": "View bookable service types and their caps/hours"},
            {"id": PERM_WRITE_APPOINTMENT_TYPES, "name": "Write Appointment Types", "description": "Create, rename, and deactivate bookable service types"},
            {"id": PERM_READ_STAFF_SCHEDULES, "name": "Read Staff Schedules", "description": "View staff schedules"},
            {"id": PERM_WRITE_STAFF_SCHEDULES, "name": "Write Staff Schedules", "description": "Manage staff schedules"},
            {"id": PERM_READ_OWN_STAFF_SCHEDULE, "name": "Read Own Staff Schedule", "description": "View own staff schedule only (self-scoped, not company-wide)"},
        ],
    },
    "business_ops": {
        "title": "Business Operations & Enterprise",
        "description": "Marketing, Compliance, HR, Procurement, Profile",
        "permissions": [
            {"id": PERM_READ_BUSINESS_PROFILE, "name": "Read Business Profile", "description": "View company identity info"},
            {"id": PERM_WRITE_BUSINESS_PROFILE, "name": "Write Business Profile", "description": "Update company profile and LLM prompt"},
            {"id": PERM_READ_MARKETING, "name": "Read Marketing", "description": "View campaigns and reviews"},
            {"id": PERM_WRITE_MARKETING, "name": "Write Marketing", "description": "Manage campaigns and review requests"},
            {"id": PERM_READ_COMPLIANCE, "name": "Read Compliance", "description": "View licenses and expirations"},
            {"id": PERM_WRITE_COMPLIANCE, "name": "Write Compliance", "description": "Manage compliance items"},
            {"id": PERM_READ_HR, "name": "Read HR", "description": "View employees and timesheets"},
            {"id": PERM_WRITE_HR, "name": "Write HR", "description": "Manage employees and payroll records"},
            {"id": PERM_READ_PROCUREMENT, "name": "Read Procurement", "description": "View vendors and purchase orders"},
            {"id": PERM_WRITE_PROCUREMENT, "name": "Write Procurement", "description": "Create and manage purchase orders"},
            {"id": PERM_GLOBAL_SEARCH, "name": "Global Search", "description": "Execute cross-system keyword search"},
            {"id": PERM_VIEW_REPORTS, "name": "View Reports", "description": "Access executive intelligence and reporting"},
        ],
    },
    "administration": {
        "title": "Administration & Security",
        "description": "User accounts, dynamic permissions, audit log",
        "permissions": [
            {"id": PERM_MANAGE_USERS, "name": "Manage Users", "description": "Create, edit, suspend users and grant permissions"},
            {"id": PERM_READ_AUDIT_LOG, "name": "Read Audit Log", "description": "Inspect immutable system audit trail"},
        ],
    },
}


def _parse_custom_permissions(raw: Any) -> Dict[str, bool]:
    """Safely parse custom_permissions_json from string or dict into Dict[str, bool]."""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return {str(k): bool(v) for k, v in raw.items()}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return {str(k): bool(v) for k, v in parsed.items()}
        except Exception:
            return {}
    return {}


def _validate_custom_permissions(perms: Dict[str, Any]) -> None:
    """Reject any custom_permissions key not present in PERMISSIONS_CATALOG
    (NEW-300). Raises ValueError to match this module's established
    convention for rejected input (_validate_user_role_invariants and the
    inline role check in update_user both raise ValueError, which the API
    layer maps to 400)."""
    valid_ids = {
        p["id"]
        for domain in PERMISSIONS_CATALOG.values()
        for p in domain["permissions"]
    }
    unknown = set(perms) - valid_ids
    if unknown:
        raise ValueError(f"Unknown permission key(s): {sorted(unknown)}")


def _validate_user_role_invariants(role: str, customer_id: Optional[int]) -> None:
    """Enforce cross-field invariants for a user row, on create or update.
    Currently: a ``customer``-role user must have a ``customer_id``. Evaluate
    against the *resulting* state — update callers pass post-update values.
    Raises ValueError; the API layer maps that to 400.

    Deliberately no equivalent ``subcontractor``/``subcontractor_id``
    invariant (Phase 0b, B8.16): unlike ``customer_id``, ``create_user`` has
    no ``subcontractor_id`` parameter at all yet (see ``update_user``'s
    ``allowed_fields`` for the only supported way to set it, post-creation),
    so requiring it at creation time would make creating a
    ``ROLE_SUBCONTRACTOR`` user impossible outright. A ``ROLE_SUBCONTRACTOR``
    user with ``subcontractor_id IS NULL`` is therefore a real, reachable
    state -- deliberately fail-closed to zero work-order access by
    ``OperationsService._actor_owns_work_order_via_subcontractor`` rather
    than rejected here.
    """
    if role == ROLE_CUSTOMER and customer_id is None:
        raise ValueError("Customer user role requires an associated customer_id")


@dataclass
class AuthContext:
    """Represents authenticated caller identity and permissions."""
    user_id: int
    username: str
    role: str
    actor_type: str  # 'human' or 'agent'
    customer_id: Optional[int] = None
    # Phase 0b, B8.16: populated for a ROLE_SUBCONTRACTOR actor, mirroring
    # customer_id's ROLE_CUSTOMER self-scoping. None for every other role.
    subcontractor_id: Optional[int] = None
    token: Optional[str] = None
    custom_permissions: Dict[str, bool] = field(default_factory=dict)

    def has_permission(self, permission: str) -> bool:
        """Check if custom permissions or role grants specific permission."""
        if permission in self.custom_permissions:
            return bool(self.custom_permissions[permission])
        perms = ROLE_PERMISSIONS.get(self.role, set())
        return permission in perms

    def can_access_customer(self, target_customer_id: int) -> bool:
        """Enforce strict isolation for customer roles."""
        if self.role == ROLE_CUSTOMER:
            return self.customer_id is not None and self.customer_id == target_customer_id
        return self.has_permission(PERM_READ_ALL_CUSTOMERS)


def _actor_may_reassign_project_staff(actor: AuthContext, project_row) -> bool:
    """Permission-keyed ownership narrowing for project staff reassignment (B6.1 / decision 2).
    Keyed on permissions, never actor.role, to avoid NEW-194's 'gate exists but
    narrowing is role-keyed' shape. Unrestricted grant bypasses ownership; scoped
    grant is limited to projects the actor manages.
    """
    if actor.has_permission(PERM_REASSIGN_ANY_PROJECT_STAFF):
        return True
    if actor.has_permission(PERM_REASSIGN_PROJECT_STAFF):
        pm_id = project_row["project_manager_id"]
        return pm_id is not None and pm_id == actor.user_id
    return False


class AuthService:
    """Handles password hashing, token creation, validation, and user management."""

    def __init__(self, db_manager: DatabaseManager, audit_service=None):
        self.db = db_manager
        self.audit = audit_service  # Optional; injected by APIRouter.__init__ for role-change audit (NEW-267)


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
        custom_permissions: Optional[Dict[str, bool]] = None,
        actor_context: Optional[AuthContext] = None,
    ) -> User:
        """Create a new user with hashed credentials and optional custom permissions."""
        if role not in ALL_ROLES:
            raise ValueError(f"Invalid role '{role}'. Must be one of {sorted(ALL_ROLES)}")

        _validate_user_role_invariants(role, customer_id)

        if actor_context and not actor_context.has_permission(PERM_MANAGE_USERS):
            raise PermissionError("Actor lacks permission to create users")

        now = utc_now_iso()
        password_hash = self.hash_password(plain_password)
        cleaned_perms = _parse_custom_permissions(custom_permissions)
        perms_json = json.dumps(cleaned_perms)

        conn = self.db.get_connection()
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO users (
                    username, password_hash, full_name, email, phone, role,
                    department, customer_id, custom_permissions_json, active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?);
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
                    perms_json,
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
            custom_permissions=cleaned_perms,
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

        perms = _parse_custom_permissions(row["custom_permissions_json"] if "custom_permissions_json" in row.keys() else None)
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
            custom_permissions=perms,
            active=row["active"],
            terminated_at=row["terminated_at"] if "terminated_at" in row.keys() else None,
            territory_id=row["territory_id"] if "territory_id" in row.keys() else None,
            subcontractor_id=row["subcontractor_id"] if "subcontractor_id" in row.keys() else None,
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
                   u.username, u.customer_id, u.subcontractor_id, u.active,
                   u.custom_permissions_json
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
        perms = _parse_custom_permissions(row["custom_permissions_json"] if "custom_permissions_json" in row.keys() else None)
        return AuthContext(
            user_id=row["user_id"],
            username=row["username"],
            role=row["role"],
            actor_type=actor_type,
            customer_id=row["customer_id"],
            subcontractor_id=row["subcontractor_id"] if "subcontractor_id" in row.keys() else None,
            token=token,
            custom_permissions=perms,
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
        perms = _parse_custom_permissions(row["custom_permissions_json"] if "custom_permissions_json" in row.keys() else None)
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
            custom_permissions=perms,
            active=row["active"],
            terminated_at=row["terminated_at"] if "terminated_at" in row.keys() else None,
            territory_id=row["territory_id"] if "territory_id" in row.keys() else None,
            subcontractor_id=row["subcontractor_id"] if "subcontractor_id" in row.keys() else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_users(
        self,
        actor_context: AuthContext,
        role: Optional[str] = None,
        active: Optional[int] = None,
    ) -> List[User]:
        """List all users with optional role and active filters (requires PERM_MANAGE_USERS)."""
        if not actor_context.has_permission(PERM_MANAGE_USERS):
            raise PermissionError("Actor lacks permission to list users")

        query = "SELECT * FROM users WHERE 1=1"
        params: List[Any] = []

        if role:
            query += " AND role = ?"
            params.append(role)
        if active is not None:
            query += " AND active = ?"
            params.append(active)

        query += " ORDER BY id ASC;"

        conn = self.db.get_connection()
        rows = conn.execute(query, tuple(params)).fetchall()
        users: List[User] = []
        for r in rows:
            perms = _parse_custom_permissions(r["custom_permissions_json"] if "custom_permissions_json" in r.keys() else None)
            users.append(
                User(
                    id=r["id"],
                    username=r["username"],
                    password_hash=r["password_hash"],
                    full_name=r["full_name"],
                    email=r["email"],
                    phone=r["phone"],
                    role=r["role"],
                    department=r["department"],
                    customer_id=r["customer_id"],
                    custom_permissions=perms,
                    active=r["active"],
                    terminated_at=r["terminated_at"] if "terminated_at" in r.keys() else None,
                    territory_id=r["territory_id"] if "territory_id" in r.keys() else None,
                    subcontractor_id=r["subcontractor_id"] if "subcontractor_id" in r.keys() else None,
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
            )
        return users

    def list_salesperson_roster(self, actor_context: AuthContext) -> List[Dict[str, Any]]:
        """NEW-680, B8.16 Phase 4: a deliberately narrow read for populating
        the work-order-intake form's salesperson picker (requires
        PERM_READ_SALESPERSON_ROSTER, held by ROLE_TECHNICIAN/
        ROLE_SUBCONTRACTOR -- see that permission's own definition above
        for why this isn't PERM_MANAGE_USERS or PERM_READ_TEAM_SALES_DATA).

        Returns ONLY {"id": ..., "name": ...} pairs -- no email, phone,
        role, or any other user field -- for active users
        (`active = 1`) whose role is in SALES_ATTRIBUTION_ROLES. The
        projection happens in this SQL SELECT itself (not by fetching full
        User rows and trimming fields in a route handler), so there is no
        later call site that could accidentally widen the response by
        returning a fuller object.

        `name` falls back to `username` when `full_name` is blank/NULL, so
        a user is never silently omitted from the picker just because
        their full_name wasn't set -- deliberate choice, not an oversight:
        username is still not email/phone/role/any other user field, so it
        does not violate this endpoint's "id+name only" contract, even
        though it is a login identifier rather than a display name.
        """
        if not actor_context.has_permission(PERM_READ_SALESPERSON_ROSTER):
            raise PermissionError("Actor lacks permission to read the salesperson roster")

        ordered_roles = sorted(SALES_ATTRIBUTION_ROLES)
        placeholders = ",".join("?" for _ in ordered_roles)
        query = (
            f"SELECT id, full_name, username FROM users "
            f"WHERE active = 1 AND role IN ({placeholders}) "
            f"ORDER BY full_name ASC, username ASC;"
        )
        conn = self.db.get_connection()
        rows = conn.execute(query, tuple(ordered_roles)).fetchall()
        roster: List[Dict[str, Any]] = []
        for r in rows:
            name = (r["full_name"] or "").strip() or r["username"]
            roster.append({"id": r["id"], "name": name})
        return roster

    def update_user(
        self,
        user_id: int,
        updates: Dict[str, Any],
        actor_context: AuthContext,
    ) -> Tuple[Optional[User], bool]:
        """Update user profile fields (requires PERM_MANAGE_USERS).

        Returns ``(updated_user, role_changed)`` (NEW-310) so callers get
        the internally-computed ``role_changed`` boolean directly, instead
        of re-deriving it a second, separately-timed way against a fresh
        before/after read.

        ``active`` is deliberately not settable here: token revocation on
        suspend/activate stays on a single path via ``set_user_active``, or a
        re-activation would resurrect pre-suspension tokens (NEW-264). A
        real ``active`` change is rejected with a pointer; a no-op echo-back
        of the current value is tolerated. Cross-field invariants (e.g. a
        ``customer`` role needs a ``customer_id``) are validated against the
        post-update state via ``_validate_user_role_invariants`` (NEW-266).
        """
        if not actor_context.has_permission(PERM_MANAGE_USERS):
            raise PermissionError("Actor lacks permission to update users")

        user = self.get_user_by_id(user_id)
        if not user:
            return None, False

        # territory_id (B8.9a): setting it to None is how a rep is returned
        # to "no territory" -- no None-guard exists on this dict-driven
        # UPDATE path (unlike update_customer's explicit None-rejection),
        # so an explicit territory_id=None in `updates` is accepted and
        # clears the column, same as every other nullable field here.
        # subcontractor_id (Phase 0b, B8.16): same convention -- this is the
        # only supported way to populate a ROLE_SUBCONTRACTOR user's own
        # subcontractor_id today (create_user has no parameter for it, same
        # as territory_id), gated on the same PERM_MANAGE_USERS check above.
        allowed_fields = {
            "full_name", "email", "phone", "role", "department", "customer_id",
            "territory_id", "subcontractor_id",
        }
        set_clauses: List[str] = []
        params: List[Any] = []

        for k, v in updates.items():
            if k in allowed_fields:
                if k == "role":
                    if v not in ALL_ROLES:
                        raise ValueError(f"Invalid role '{v}'. Must be one of {sorted(ALL_ROLES)}")
                if k == "email" and v:
                    v = str(v).strip().lower()
                set_clauses.append(f"{k} = ?")
                params.append(v)

        if "custom_permissions" in updates and isinstance(updates["custom_permissions"], dict):
            cleaned_perms = _parse_custom_permissions(updates["custom_permissions"])
            _validate_custom_permissions(cleaned_perms)
            set_clauses.append("custom_permissions_json = ?")
            params.append(json.dumps(cleaned_perms))

        if "active" in updates:
            try:
                requested_active = int(updates["active"])
            except (TypeError, ValueError):
                raise ValueError(
                    "active must be 0 or 1; use the suspend/activate endpoints to change account status"
                )
            if requested_active not in (0, 1) or requested_active != user.active:
                raise ValueError(
                    "active status cannot be changed here; use set_user_active "
                    "(POST /api/v1/users/{id}/suspend or /activate) so session tokens are revoked correctly"
                )

        effective_role = updates["role"] if "role" in updates else user.role
        effective_customer_id = updates["customer_id"] if "customer_id" in updates else user.customer_id
        _validate_user_role_invariants(effective_role, effective_customer_id)

        if not set_clauses:
            return user, False

        # api_tokens.role is a snapshot taken at login time and
        # authenticate_token reads that snapshot, not the live user row --
        # so a role change must revoke existing tokens or the user keeps
        # acting under the old role until they expire. The actor's own
        # token is deliberately NOT spared (unlike change_password): a
        # self-demotion leaving a stale-role token alive is the exact bug.
        role_changed = "role" in updates and updates["role"] != user.role

        now = utc_now_iso()
        set_clauses.append("updated_at = ?")
        params.append(now)
        params.append(user_id)

        conn = self.db.get_connection()
        try:
            with conn:
                conn.execute(
                    f"UPDATE users SET {', '.join(set_clauses)} WHERE id = ?;",
                    tuple(params),
                )
                if role_changed:
                    conn.execute(
                        "UPDATE api_tokens SET is_revoked = 1 WHERE user_id = ?;",
                        (user_id,),
                    )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"Update violates a data constraint: {e}") from e

        if role_changed and self.audit is not None:
            from .services.audit_service import build_audit_details
            role_change_details = build_audit_details(
                before={"role": user.role},
                after={"role": updates["role"]},
                fields={"role"},
                side_effects={"sessions_revoked": "all"},
            )
            self.audit.log(
                action="update",
                entity_type="user",
                entity_id=user_id,
                change_summary=f"User role changed from {user.role!r} to {updates['role']!r}; all sessions revoked",
                actor=actor_context,
                details=role_change_details,
            )

        return self.get_user_by_id(user_id), role_changed

    def set_user_active(
        self,
        user_id: int,
        active: int,
        actor_context: AuthContext,
    ) -> Optional[User]:
        """Activate or suspend user account (requires PERM_MANAGE_USERS).

        terminated_at (B8.7c, D6): set to the current timestamp ONLY on a
        genuine active 1->0 transition (checked against this SAME
        get_user_by_id read below, before the UPDATE -- a repeated
        suspend call against an already-suspended user is a no-op
        transition and must not keep bumping terminated_at forward,
        which would silently move CRMService's portfolio-override
        termination gate later than the rep's real departure). Cleared
        back to NULL on a 0->1 reactivation -- a rehired rep isn't
        "still terminated" for future GC projects. Built into ONE UPDATE
        below (not a second follow-up statement) so there is no
        partial-write window between the active flag and terminated_at
        landing -- same atomicity discipline as the B8.6d-b finding.
        Known, accepted TOCTOU (not fixed here, same class as NEW-606):
        the get_user_by_id read above and the UPDATE below are not one
        atomic operation, so two concurrent set_user_active calls on the
        same user (a suspend racing a reactivate) could interleave and
        land active=1 with a stale terminated_at still set, or vice
        versa -- no lock exists on this row for that window. Consequence
        for the active=1/terminated_at-stale case specifically: CRMService's
        portfolio-override gate 5 (crm_service.py,
        _resolve_portfolio_override_eligibility) treats a non-NULL
        terminated_at as "this rep departed on this date" regardless of
        the active flag, so a currently-employed rep left in this state
        would have a legitimate override silently rejected (fail-closed
        money loss, not a security exposure) on every payment until the
        stale terminated_at is corrected -- and since normal-ineligible
        outcomes aren't audit-logged, there would be no trail pointing at
        why.
        """
        if not actor_context.has_permission(PERM_MANAGE_USERS):
            raise PermissionError("Actor lacks permission to manage users")

        if active not in (0, 1):
            raise ValueError("Active status must be 0 (suspended) or 1 (active)")

        user = self.get_user_by_id(user_id)
        if not user:
            return None

        now = utc_now_iso()
        conn = self.db.get_connection()
        with conn:
            if user.active == 1 and active == 0:
                # Genuine 1->0 transition: stamp terminated_at.
                conn.execute(
                    "UPDATE users SET active = ?, terminated_at = ?, updated_at = ? WHERE id = ?;",
                    (active, now, now, user_id),
                )
            elif user.active == 0 and active == 1:
                # Genuine 0->1 transition: clear terminated_at.
                conn.execute(
                    "UPDATE users SET active = ?, terminated_at = NULL, updated_at = ? WHERE id = ?;",
                    (active, now, user_id),
                )
            else:
                # No actual transition (e.g. suspend called again on an
                # already-suspended user) -- leave terminated_at
                # untouched.
                conn.execute(
                    "UPDATE users SET active = ?, updated_at = ? WHERE id = ?;",
                    (active, now, user_id),
                )
            # If suspending, immediately revoke all active sessions
            if active == 0:
                conn.execute(
                    "UPDATE api_tokens SET is_revoked = 1 WHERE user_id = ?;",
                    (user_id,),
                )

        return self.get_user_by_id(user_id)

    def change_password(
        self,
        user_id: int,
        new_password: str,
        actor_context: AuthContext,
        old_password: Optional[str] = None,
    ) -> bool:
        """Change user password. Self-service requires old_password; admin requires PERM_MANAGE_USERS."""
        is_self = (actor_context.user_id == user_id)
        is_admin = actor_context.has_permission(PERM_MANAGE_USERS)

        if not is_self and not is_admin:
            raise PermissionError("Actor lacks permission to change this password")

        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        if is_self and not is_admin:
            if not old_password or not self.verify_password(old_password, user.password_hash):
                raise ValueError("Current password verification failed")

        if len(new_password) < 6:
            raise ValueError("Password must be at least 6 characters long")

        new_hash = self.hash_password(new_password)
        now = utc_now_iso()

        conn = self.db.get_connection()
        with conn:
            conn.execute(
                "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?;",
                (new_hash, now, user_id),
            )
            # Invalidate other active sessions
            conn.execute(
                "UPDATE api_tokens SET is_revoked = 1 WHERE user_id = ? AND token != ?;",
                (user_id, actor_context.token or ""),
            )
        return True

    def delete_user(self, user_id: int, actor_context: AuthContext) -> bool:
        """Delete user account and all associated tokens (requires PERM_MANAGE_USERS).

        Archive-then-delete (Delete-buttons round, Ish 2026-09-11 policy
        decision, NEW-493): staff_schedules.user_id carries
        FOREIGN KEY ... ON DELETE CASCADE, so DELETE FROM users below would
        silently wipe this user's staff_schedules rows -- including
        terminal/historical ('completed'/'cancelled') ones -- violating
        Ish's "keep historical info" policy. ALL remaining staff_schedules
        rows for this user are copied into staff_schedules_archive
        unconditionally (no status filter here) in the SAME transaction,
        immediately before DELETE FROM users, so the CASCADE that follows
        deletes only rows whose content already survives elsewhere. The
        only production caller (routes.py's DELETE /api/v1/users/<id>
        handler) already runs the active-reference precheck first and
        blocks the whole delete if any 'scheduled' rows exist, so in
        practice every row archived here is terminal -- but that guarantee
        lives in the route, not in this method: a direct/future caller
        that skips the route-level precheck still archives (not loses)
        whatever status is present, rather than relying on an invariant
        this function does not itself enforce. If the archive insert
        fails, the `with conn:` block rolls back the whole delete -- a user
        is never removed with a half-archived schedule history.

        Behavior note: a `user.username` is needed to denormalize
        `original_username` into each archived row, so this method now
        looks the user up first and returns False immediately if no such
        user exists -- unlike the pre-archive version, this means
        `DELETE FROM api_tokens WHERE user_id = ?` is no longer run for a
        nonexistent user_id (previously a harmless no-op delete ran
        regardless). Externally identical (the route still returns 404
        either way); noted here since it's a real behavior change inside
        this method.

        Also nulls out `subcontractors.user_id` and
        `appointments.assigned_user_id` for this user (both FK-less,
        NEW-494/NEW-519) -- a plain null-out, not an archive, since
        neither column's data is itself a historical record the way
        `staff_schedules` rows are; the subcontractor/appointment rows
        they point from survive fully intact.
        """
        if not actor_context.has_permission(PERM_MANAGE_USERS):
            raise PermissionError("Actor lacks permission to delete users")

        if actor_context.user_id == user_id:
            raise ValueError("Cannot delete currently authenticated user")

        user = self.get_user_by_id(user_id)
        if not user:
            return False

        now = utc_now_iso()
        conn = self.db.get_connection()
        with conn:
            # Single INSERT ... SELECT rather than a per-row Python loop:
            # one statement archives every row while the write transaction
            # is held, instead of N round-trips for a long-tenured user.
            conn.execute(
                """
                INSERT INTO staff_schedules_archive
                    (original_schedule_id, original_user_id, original_username,
                     title, start_time, end_time, status, notes,
                     archived_at, archived_reason)
                SELECT id, user_id, ?, title, start_time, end_time, status, notes,
                       ?, 'user_deleted'
                FROM staff_schedules WHERE user_id = ?;
                """,
                (user.username, now, user_id),
            )
            conn.execute(
                "UPDATE subcontractors SET user_id = NULL WHERE user_id = ?;",
                (user_id,),
            )
            conn.execute(
                "UPDATE appointments SET assigned_user_id = NULL WHERE assigned_user_id = ?;",
                (user_id,),
            )
            conn.execute("DELETE FROM api_tokens WHERE user_id = ?;", (user_id,))
            cursor = conn.execute("DELETE FROM users WHERE id = ?;", (user_id,))
            return cursor.rowcount > 0

    def set_user_permissions(
        self,
        user_id: int,
        custom_permissions: Dict[str, bool],
        actor_context: AuthContext,
    ) -> User:
        """Assign or revoke custom permissions directly for a user (requires PERM_MANAGE_USERS)."""
        if not actor_context.has_permission(PERM_MANAGE_USERS):
            raise PermissionError("Actor lacks permission to manage user permissions")

        user = self.get_user_by_id(user_id)
        if not user:
            raise ValueError(f"User with ID {user_id} not found")

        cleaned_perms = _parse_custom_permissions(custom_permissions)
        _validate_custom_permissions(cleaned_perms)
        perms_json = json.dumps(cleaned_perms)
        now = utc_now_iso()

        conn = self.db.get_connection()
        with conn:
            conn.execute(
                "UPDATE users SET custom_permissions_json = ?, updated_at = ? WHERE id = ?;",
                (perms_json, now, user_id),
            )

        updated = self.get_user_by_id(user_id)
        return updated or user

    update_user_permissions = set_user_permissions  # alias for backward compatibility

    def get_effective_permissions(self, user: User) -> List[str]:
        """Compute the full set of active permissions for a user taking role + custom into account."""
        perms = set(ROLE_PERMISSIONS.get(user.role, set()))
        for perm, enabled in user.custom_permissions.items():
            if enabled:
                perms.add(perm)
            elif perm in perms:
                perms.remove(perm)
        return sorted(list(perms))
