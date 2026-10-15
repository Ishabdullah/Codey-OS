# WP2.1 group 12 — persistence boundary contract

Architect-scoped against live code on 2026-10-15, starting at `77fcd71`.
This is a boundary disposition, not a claim that WP2.1 is complete.
The blueprint §21 owns progress; NEW_ISSUES.md owns finding status.

## Operations requiring authority

Slice 12a covers `SymbolicGraph.execute` (QUERY: READ; seven mutation
operations: ACT), its batch and memory wrappers, and `SymbolicGraph.clear`
(HIGH_IMPACT). Relation auto-creation is subordinate to the containing
operation. Clear requires an actual approving confirmation callback;
callback availability alone cannot authorize deletion. SQL failure must
be audited as failed; a handler returning an error dictionary is failure.
A four-table clear must roll back together, with caches cleared only after
successful persistence. The CLI must report refusal/failure truthfully.

Slice 12b covers independent destructive persistence entry points:
`PreferenceManager.clear`, `ErrorDatabase.clear`, `StrategyTracker.clear`,
`StrategyTracker.reset_strategy`,
`LearningManager.clear_all`, `StateStore.clear_old_actions`, and
`TaskBlackboard.cleanup_task`. These were found dormant by the architect;
hardening them must not introduce callers. Important-history deletion is
HIGH_IMPACT, with no callback-free Boolean authorization. Aggregate reset
must confirm once, retain independently gated public reset methods, and
report any partial completion honestly. Implementation/review evidence
belongs in the log; listing a boundary here does not establish completion.

## Subordinate recording and coordination

These are narrow dispositions for the stated mechanics, not exemptions
for their modules or permission to route new agent actions through them.

| Mechanic | Why it does not require another action decision | Boundary retained |
| --- | --- | --- |
| `action_gateway._append_audit` | Direct ledger persistence avoids recursive auditing. | The operation invoking the gateway retains its authority decision. |
| State schema initialization, episodic appends, daemon timestamps and task progress | Fixed-purpose recording of runtime state. | Arbitrary SQL/key APIs confer no authority for agent-selected writes, task submission, configuration or cancellation. |
| Trajectory hooks and benchmark labels | Recording and verification bookkeeping. | Existing opt-in and train/evaluation partition remain required; export and labeling policies are independent. |
| Resource leases, flock and reaping | RAM/context accounting and coordination. | Model loading and process actions remain group 13. |
| RAM-only working/project memory and summaries | No independent persistent deletion. | Persisting/exporting such data requires its own boundary classification. |
| Fixed-key diagnostic and preference appends | Record observations of existing actions. | Destructive resets are 12b; CODEY.md synchronization retains its existing independent gateway. |
| CCOS task results, workflow/events, performance and telemetry records | Data-only recording of execution. | Executable artifact generation and promotion remain group 14. |
| Blackboard task/checkpoint/escalation metadata | Records task coordination. | Peer execution retains its HIGH_IMPACT gate; caller-selected cleanup is 12b. |
| Blackboard `purge_expired` | Bounded TTL retention using stored expiry. | This does not authorize arbitrary caller-selected deletion. |
| Pipeline SQLite/vector ingestion writes | Storage subordinate to the ingestion operation. | Independently chosen ingestion/export/artifact paths are not authorized by this disposition. |

## Explicit residuals

NEW-939 remains open: CLI ignore/CODEY.md/session/voice persistence and
its unresolved taskqueue/config/design/KB/export/model-artifact candidates
need their own caller-level disposition in the final census. A group label
or absence from the original AST inventory is not an exemption.

`LongTermMemory.store_file/remove_file` and
`StructuredDB.store_skill/set_config/set_preference` had no production
callers found during scoping. This does not establish authority for future
callers or executable skills. Self-improvement artifacts remain group 14.
The final closure census must retain uncertain reachability explicitly.

All verification uses disposable state and audit files. No model load,
external recipient, live-store mutation, service restart or cloud-policy
change is authorized by this contract.
