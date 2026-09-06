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

# Contacts permissions (Track B Phase B2 cutover)
PERM_READ_CONTACTS = "read:contacts"
PERM_WRITE_CONTACTS = "write:contacts"

# CRM & Sales Domain permissions (Track B Phase B3)
PERM_READ_CRM = "read:crm"
PERM_WRITE_CRM = "write:crm"
PERM_MANAGE_PIPELINE = "manage:pipeline"
PERM_SCORE_LEADS = "score:leads"

# Operations Domain permissions (Track B Phase B3)
PERM_READ_OPERATIONS = "read:operations"
PERM_WRITE_OPERATIONS = "write:operations"
PERM_MANAGE_PROJECTS = "manage:projects"
PERM_DISPATCH_WORK_ORDERS = "dispatch:work_orders"

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
        PERM_READ_OPERATIONS,
        PERM_READ_MARKETING,
        PERM_WRITE_MARKETING,
        PERM_READ_PROCUREMENT,
        PERM_GLOBAL_SEARCH,
        PERM_VIEW_REPORTS,
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
        ],
    },
    "operations": {
        "title": "Field Operations & Projects",
        "description": "Projects, work orders, and drying fleet",
        "permissions": [
            {"id": PERM_READ_ALL_PROJECTS, "name": "Read All Projects", "description": "View all job sites and projects"},
            {"id": PERM_READ_ASSIGNED_PROJECTS, "name": "Read Assigned Projects", "description": "View assigned project jobs"},
            {"id": PERM_READ_OWN_PROJECTS, "name": "Read Own Projects", "description": "View own customer projects"},
            {"id": PERM_WRITE_PROJECTS, "name": "Write Projects", "description": "Create and update project records"},
            {"id": PERM_REASSIGN_PROJECT_STAFF, "name": "Reassign Project Staff (Own Projects)", "description": "Reassign the PM, employees, or subcontractors on projects where the actor is the project manager"},
            {"id": PERM_REASSIGN_ANY_PROJECT_STAFF, "name": "Reassign Project Staff (Any Project)", "description": "Reassign the PM, employees, or subcontractors on any project regardless of ownership"},
            {"id": PERM_MANAGE_PROJECTS, "name": "Manage Projects", "description": "Full project lifecycle management"},
            {"id": PERM_READ_OPERATIONS, "name": "Read Operations", "description": "View operations dashboard"},
            {"id": PERM_WRITE_OPERATIONS, "name": "Write Operations", "description": "Modify operational assets and equipment"},
            {"id": PERM_DISPATCH_WORK_ORDERS, "name": "Dispatch Work Orders", "description": "Assign and dispatch work orders"},
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


def _validate_user_role_invariants(role: str, customer_id: Optional[int]) -> None:
    """Enforce cross-field invariants for a user row, on create or update.
    Currently: a ``customer``-role user must have a ``customer_id``. Evaluate
    against the *resulting* state — update callers pass post-update values.
    Raises ValueError; the API layer maps that to 400.
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
                   u.username, u.customer_id, u.active, u.custom_permissions_json
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
                    created_at=r["created_at"],
                    updated_at=r["updated_at"],
                )
            )
        return users

    def update_user(
        self,
        user_id: int,
        updates: Dict[str, Any],
        actor_context: AuthContext,
    ) -> Optional[User]:
        """Update user profile fields (requires PERM_MANAGE_USERS).

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
            return None

        allowed_fields = {"full_name", "email", "phone", "role", "department", "customer_id"}
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
            return user

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

        return self.get_user_by_id(user_id)

    def set_user_active(
        self,
        user_id: int,
        active: int,
        actor_context: AuthContext,
    ) -> Optional[User]:
        """Activate or suspend user account (requires PERM_MANAGE_USERS)."""
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
        """Delete user account and all associated tokens (requires PERM_MANAGE_USERS)."""
        if not actor_context.has_permission(PERM_MANAGE_USERS):
            raise PermissionError("Actor lacks permission to delete users")

        if actor_context.user_id == user_id:
            raise ValueError("Cannot delete currently authenticated user")

        conn = self.db.get_connection()
        with conn:
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
