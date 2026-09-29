---
name: b9_3_round2_preview_cost_gate_approved
description: B9.3 estimate-routes round2 — preview() ownership+cost-field gate fix verified and APPROVED (final)
metadata:
  type: project
---

Round 2 on [[b9_3_estimate_routes_preview_cost_leak_changes_requested]]. The
Critical (unnarrowed, ungated `EstimateService.preview()`) is fixed and
independently verified, not just re-read:

- **Differential live repro, both directions.** `git stash push -- estimate_service.py`
  then re-ran the new regression test against the OLD code: reproduced the
  exact leak (sales2_tok got 200 + full `material_cost_cents` on `/preview`
  where `/get` correctly 403'd). Stash-popped, re-ran: now 403 on both. This
  is the strongest form of "the bug was real and the fix closes it" —
  matches the project's own established revert-and-rerun technique (see
  [[b8_5b_assessment_photo_round2_approved]]).
- **Full dataclass field-dump cross-check.** Read `codey_estimator/dto.py`
  in full (not grepped) and hand-matched every field of `EstimateResult`,
  `LineResult`, `LineInput`, `MaterialInput`, `LaborInput`, `EquipmentInput`,
  `SubcontractorInput` against `_gate_preview_result_cost_fields()`'s
  null-list. Nothing cost/margin-bearing was missed; the echoed
  `LineResult.input` tree (the part flagged hardest last round) is genuinely
  gated via `dataclasses.replace()` at every nesting level.
- **`dataclasses.replace()` on frozen `slots=True` semantics confirmed
  empirically** (not just read) with a throwaway reproduction: it returns a
  new instance with named fields overridden and all others copied, and
  direct attribute assignment on the original still raises — matches the
  implementer's claim exactly.
- **Line-number citation fix confirmed.** Grepped the whole repo for
  `1397`: two real remaining hits (`CODEY_MASTER_PLAN.md`, an older
  code-reviewer memory file) are in files this diff never touches (`git
  diff --stat` on both shows nothing) — pre-existing historical artifacts
  from an earlier round, not in scope for this commit. `NEW-718`'s body was
  read in full and genuinely never cited `routes.py:1397` (cites
  `web_surfaces.py:7234`/`:7401` instead) — implementer's claim held up.
- **Full suite**: 1418 passed, reproduced exactly (`HTTP_PROXY`/`HTTPS_PROXY`
  unset per [[sandbox_http_proxy_urllib_405_env_artifact]]).

**Verdict: APPROVED (final).** Files to stage for commit (spans both
implementer rounds + both review rounds on top of base B9.3):
- `restoricon_core/api/routes.py`
- `restoricon_core/api/server.py`
- `restoricon_core/services/estimate_service.py`
- `tests/test_restoricon_core/test_b9_2_estimate_service.py`
- `tests/test_restoricon_core/test_b9_3_estimate_routes.py`
- `NEW_ISSUES.md`
- `.claude/agent-memory/code-reviewer/MEMORY.md`
- `.claude/agent-memory/code-reviewer/b9_3_estimate_routes_preview_cost_leak_changes_requested.md`

See also: [[b9_3_estimate_routes_preview_cost_leak_changes_requested]],
[[b8_5b_assessment_photo_round2_approved]].
