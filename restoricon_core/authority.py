"""
Business-mutation authority classification and enforcement for
Restoricon Core (WP2.1 group 7, NEW-919/920/921).

This is a **native, independent mechanism** -- it extends restoricon_core's
own existing `actor_type`/`role` pattern in `auth.py` and does NOT import
`core/action_gateway.py` (Ish decision, 2026-10-14: this codebase's own
authority mechanism, not the coding-agent's). `ACT`/`HIGH_IMPACT` reuse
`core/action_gateway.py`'s names purely for naming consistency across the
two systems; they are two separate classification tables with no shared
state or import.

Gate: `actor.role == ROLE_AI_AGENT` -- NOT `actor.actor_type == "agent"`.
Nine internal "system actor" identities scattered across
`services/crm_service.py` (pdf_system_actor, homecare_system_actor,
clawback_system_actor, intake_system_actor, system_actor x2,
_precedence_actor, commission_system_actor, commission_config_actor) are
all `role=ROLE_ADMIN, actor_type="agent"` -- deterministic internal
automation (PDF generation, commission clawback via
`CommissionService.reverse_commission`, web-intake lead creation). Gating
on `actor_type == "agent"` would refuse every one of these, breaking real
production automation including a genuine financial reversal. Gating on
`role` instead leaves them untouched (they're all `ROLE_ADMIN`); the only
two live `role=ROLE_AI_AGENT` identities are `codey-aigentik-agent` (the
real write-through token, subject to this gate) and
`codey-ccos-crm-reader` (read-only -- every write/manage permission is
already denied via `custom_permissions`, checked before role defaults by
`AuthContext.has_permission()`, so it can never reach a write-gated
method regardless of this module).

Enforcement applies ONLY at HIGH_IMPACT-classified sites. ACT sites are
classified here for coverage-completeness (see the AST coverage test,
`tests/test_business_mutation_authority_coverage.py`) but get no new
gate, no new audit write, and no behavior change -- this preserves every
ACT site's current behavior exactly, including the one pre-existing
unrelated hard-refusal precedent (`estimate_service.py`'s
`convert()`, `actor.role == ROLE_AI_AGENT` -> `PermissionError` for
estimate-to-job conversion, which this module does not touch or
generalize over).
"""

from __future__ import annotations

from typing import Dict, Optional

from .auth import AuthContext, ROLE_AI_AGENT
from .services.audit_service import build_audit_details

ACT = "ACT"
HIGH_IMPACT = "HIGH_IMPACT"

# Keyed by "{module}.{function_name}", where `module` is the service
# module's filename stem (e.g. "crm_service") and `function_name` is the
# enclosing method's name. Required coverage (every site this module MUST
# classify) is derived programmatically by
# tests/test_business_mutation_authority_coverage.py from
# ROLE_PERMISSIONS[ROLE_AI_AGENT] -- every service method whose body
# contains a has_permission() check against a write:/manage:-prefixed
# permission ROLE_AI_AGENT holds, OR against
# {"score:leads", "dispatch:work_orders", "log:communication"} -- the same
# derive-don't-hand-copy approach
# tools/provision_ai_agent_auth.py::_compute_crm_reader_deny_permissions()
# already uses. A handful of entries below (delete_appointment_type,
# cancel_homecare_subscription) are classified beyond that derived minimum
# for future-proofing / documentation even though ROLE_AI_AGENT does not
# currently hold the permission gating them -- extra entries are fine, the
# coverage test only requires the derived set to be a SUBSET of this dict,
# never requires BUSINESS_MUTATION_AUTHORITY == that set exactly.
BUSINESS_MUTATION_AUTHORITY: Dict[str, str] = {
    # -- assessment_service.py --
    "assessment_service.create_assessment_record": ACT,

    # -- automation_service.py --
    "automation_service.add_to_do_not_contact": ACT,
    "automation_service.create_rule": ACT,
    # HIGH_IMPACT: hard delete, PERM_WRITE_AUTOMATION_RULES. Reached live
    # by Aigentik's remove_rule.
    "automation_service.delete_rule": HIGH_IMPACT,
    "automation_service.record_rule_match": ACT,
    # HIGH_IMPACT: compliance-relevant, PERM_WRITE_DNC. Reached live by
    # Aigentik's unblock.
    "automation_service.remove_from_do_not_contact": HIGH_IMPACT,
    "automation_service.upsert_business_profile": ACT,

    # -- business_ops_service.py --
    "business_ops_service.create_campaign": ACT,
    "business_ops_service.create_compliance_item": ACT,
    "business_ops_service.create_purchase_order": ACT,
    "business_ops_service.create_review_request": ACT,
    "business_ops_service.create_vendor": ACT,
    "business_ops_service.receive_purchase_order": ACT,
    "business_ops_service.submit_review": ACT,

    # -- commission_service.py --
    "commission_service.record_commission": ACT,
    # HIGH_IMPACT: financial reversal, PERM_WRITE_TEAM_COMMISSIONS. Not
    # reached by Aigentik; its only live caller is the internal
    # clawback_system_actor (role=ROLE_ADMIN) -- unaffected by this gate
    # because the gate keys on role, not actor_type (see module docstring).
    "commission_service.reverse_commission": HIGH_IMPACT,

    # -- communication_service.py --
    "communication_service.record_communication": ACT,

    # -- crm_service.py --
    "crm_service.claim_lead": ACT,
    "crm_service.claim_opportunity": ACT,
    "crm_service.claim_task": ACT,
    "crm_service.complete_task": ACT,
    "crm_service.create_contact": ACT,
    "crm_service.create_customer": ACT,
    "crm_service.create_document": ACT,
    "crm_service.create_estimate": ACT,
    "crm_service.create_invoice": ACT,
    "crm_service.create_lead": ACT,
    "crm_service.create_opportunity": ACT,
    "crm_service.create_package_option": ACT,
    "crm_service.create_property": ACT,
    "crm_service.create_subcontractor": ACT,
    "crm_service.create_task": ACT,
    # HIGH_IMPACT: hard delete, PERM_WRITE_CONTACTS. Needs the `confirmed`
    # signal plumbed from Aigentik's owner-command.js pendingConfirmations
    # flow (the only confirmed call site) -- see delete_contact's own
    # docstring/call site in api/routes.py.
    "crm_service.delete_contact": HIGH_IMPACT,
    # HIGH_IMPACT: hard delete, PERM_WRITE_SUBCONTRACTORS. Not currently
    # reached live, classified for future-proofing.
    "crm_service.delete_subcontractor": HIGH_IMPACT,
    "crm_service.record_payment": ACT,
    "crm_service.score_lead": ACT,
    "crm_service.send_estimate": ACT,
    "crm_service.submit_work_order_intake": ACT,
    # ACT: insert/update-only, no delete/pruning (verified by reading the
    # method body -- it only ever matches-and-updates or inserts).
    "crm_service.sync_contacts_batch": ACT,
    "crm_service.transition_opportunity_stage": ACT,
    "crm_service.update_contact": ACT,
    "crm_service.update_customer": ACT,
    "crm_service.update_estimate": ACT,
    "crm_service.update_lead": ACT,
    "crm_service.update_opportunity": ACT,
    "crm_service.update_property": ACT,
    "crm_service.update_subcontractor": ACT,
    "crm_service.update_subcontractor_qualification": ACT,
    "crm_service.update_task": ACT,
    "crm_service.upsert_contact": ACT,
    "crm_service.upsert_customer": ACT,
    "crm_service.upsert_subcontractor": ACT,
    # ACT (not in the derived-required set -- gated on PERM_WRITE_CONTRACTS,
    # which ROLE_AI_AGENT does not hold -- classified anyway for
    # completeness/documentation): status-field update; the 90-day clawback
    # it may trigger runs under the internal role=ROLE_ADMIN
    # clawback_system_actor, unaffected by this gate.
    "crm_service.cancel_homecare_subscription": ACT,

    # -- estimate_service.py --
    "estimate_service.add_line": ACT,
    "estimate_service.claim": ACT,
    # ACT: pre-existing, already-shipped hard-refusal precedent lives
    # inside convert() itself (estimate-to-job conversion,
    # `if actor.role == ROLE_AI_AGENT: raise PermissionError(...)`) --
    # deliberately left untouched and not generalized by this module.
    "estimate_service.convert": ACT,
    "estimate_service.create": ACT,
    "estimate_service.preview": ACT,
    # HIGH_IMPACT: hard delete of an estimate line item,
    # PERM_WRITE_ESTIMATES.
    "estimate_service.remove_line": HIGH_IMPACT,
    "estimate_service.reorder_lines": ACT,
    "estimate_service.revise": ACT,
    "estimate_service.transition": ACT,
    "estimate_service.unclaim": ACT,
    "estimate_service.update_header": ACT,
    "estimate_service.update_line": ACT,

    # -- finance_service.py --
    "finance_service.record_transaction": ACT,

    # -- financing_service.py --
    "financing_service.create_financing_record": ACT,
    "financing_service.update_financing_record": ACT,

    # -- operations_service.py --
    "operations_service._actor_reaches_only_via_sold_projects": ACT,
    "operations_service.accept_work_order": ACT,
    "operations_service.create_equipment": ACT,
    "operations_service.create_milestone": ACT,
    "operations_service.create_work_order": ACT,
    "operations_service.deploy_equipment": ACT,
    "operations_service.dispatch_work_order": ACT,
    "operations_service.get_project": ACT,
    "operations_service.get_project_summary": ACT,
    "operations_service.return_equipment": ACT,
    "operations_service.split_work_order": ACT,
    "operations_service.transition_project_stage": ACT,
    "operations_service.update_milestone_status": ACT,
    "operations_service.update_work_order": ACT,
    "operations_service.update_work_order_execution_status": ACT,

    # -- scheduling_service.py --
    "scheduling_service.create_appointment": ACT,
    "scheduling_service.create_staff_schedule": ACT,
    # ACT (not in the derived-required set -- gated on
    # PERM_WRITE_APPOINTMENT_TYPES, which ROLE_AI_AGENT does not hold --
    # classified anyway for completeness/documentation): HIGH_IMPACT, hard
    # delete, PERM_WRITE_APPOINTMENT_TYPES.
    "scheduling_service.delete_appointment_type": HIGH_IMPACT,
    # HIGH_IMPACT: hard delete, PERM_WRITE_STAFF_SCHEDULES.
    "scheduling_service.delete_staff_schedule": HIGH_IMPACT,
    # ACT, per the architect's explicit correction: update_appointment is a
    # generic field update (also used for reschedules) -- ordinary CRUD.
    # A second, independent, unconfirmed caller exists for appointment
    # cancellation (Aigentik's handleCancelRequest(), a customer cancelling
    # their OWN appointment with no confirmation step) that hits this same
    # method via the same HTTP route as the owner-confirmed path.
    # Classifying this HIGH_IMPACT would break that live customer
    # self-service flow -- no `confirmed` signal is plumbed here.
    "scheduling_service.update_appointment": ACT,
    "scheduling_service.update_appointment_status": ACT,
    "scheduling_service.update_staff_schedule": ACT,
    "scheduling_service.upsert_appointment": ACT,
    "scheduling_service.upsert_schedule_config": ACT,
}


def check_business_mutation_authority(
    actor: AuthContext,
    method_key: str,
    audit,
    confirmed: bool = False,
) -> None:
    """Fail-closed HIGH_IMPACT gate for ROLE_AI_AGENT actors (NEW-919/920/921).

    Call as the FIRST statement in every HIGH_IMPACT-classified method --
    before any has_permission() check's own early-return and before the
    method's own DB transaction (`with conn:` / `BEGIN IMMEDIATE`) opens.
    This ordering lets the refusal-audit write below commit cleanly and
    independently (AuditService.log() opens and commits its own
    transaction, restoricon_core/services/audit_service.py:308-328) before
    this function raises -- so the refusal is always durably recorded even
    though the caller's own mutation transaction never opens.

    No-op (returns without raising) for:
      - any actor whose role is not ROLE_AI_AGENT (see module docstring:
        this is role-keyed, not actor_type-keyed, so internal
        role=ROLE_ADMIN system actors are never affected);
      - any method_key classified ACT (or not classified at all -- unknown
        keys default to ACT, i.e. no new gate, rather than failing closed
        on a classification gap);
      - a HIGH_IMPACT method_key when `confirmed` is True.

    Raises PermissionError (mapped to HTTP 403 by api/routes.py's existing
    global `except PermissionError` handler -- no new exception-mapping
    needed) when the actor is ROLE_AI_AGENT, the method is classified
    HIGH_IMPACT, and `confirmed` is not True.

    `confirmed` is a CALLER-ASSERTED boolean, not verified consent --
    Core has no way to cryptographically confirm a human actually
    replied "yes" upstream (e.g. in Aigentik's owner-command.js). It is
    an assertion made over the same static bearer token as every other
    call, not a stronger authentication factor. Code-reviewer W3
    (2026-10-15): any ai_agent-token caller can send `confirmed: true`
    and bypass this gate; it is enforced by caller discipline (only
    owner-command.js's post-"yes" `pendingConfirmations` closures set it
    today), not by this function. Treat this as a known, accepted limit
    of the design, not a proof of real human confirmation.
    """
    if actor.role != ROLE_AI_AGENT:
        return

    classification = BUSINESS_MUTATION_AUTHORITY.get(method_key, ACT)
    if classification != HIGH_IMPACT:
        return

    if confirmed:
        return

    reason = (
        f"Refused unconfirmed HIGH_IMPACT business mutation '{method_key}' "
        f"for ai_agent actor (user_id={actor.user_id})"
    )
    if audit is not None:
        audit.log(
            action="refused",
            entity_type="business_mutation_authority",
            entity_id=None,
            change_summary=reason,
            actor=actor,
            details=build_audit_details(
                snapshot={"method": method_key, "confirmed": confirmed}
            ),
        )
    raise PermissionError(reason)
