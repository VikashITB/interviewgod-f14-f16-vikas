# F14/F16 Architecture Notes

## Scope

Week 1 ownership is limited to F14 Audit Logger and F16 Interviewer Scorecard.
These modules provide production-safe foundations for future systems, but they
do not own blueprint orchestration, recommendation engine design, enrichment,
market adapters, or evaluation engine rewrites.

## What Changed

- F14 now supports pipeline-stage-aware audit events through `PipelineStage`.
- Audit evidence can carry semantic reasoning, confidence, integrity signals,
  recommendation rationale, and blueprint identifiers as flexible payload data.
- Rich evidence payloads include `evidence_schema_version: "v1"` so future
  readers can interpret stored evidence safely.
- Rich evidence payloads may include `replay_metadata` with blueprint version,
  evaluator version, feature flags, and threshold snapshots for historically
  accurate reconstruction.
- SQLite persistence remains append-only and stores evidence as serialized JSON.
- F16 scorecard submissions emit blueprint-aware evidence snapshots and preserve
  the existing validation -> submission -> audit logging flow.

## Generic Evidence Contract

`AuditEvent.evidence_snapshot` intentionally remains a flexible dictionary.
F14 is shared audit infrastructure, not a scorecard-specific model layer.
Callers may store scorecard, recommendation, knockout, integrity, or override
evidence as long as the payload is serializable and reviewable.

The logger must not hardcode scorecard-only fields into `AuditEvent`. Semantic
fields such as `reasoning_quality`, `confidence_score`, `integrity_signals`, and
`recommendation_reasoning` are caller-owned evidence, not audit table columns.
Replay context such as `replay_metadata` is also caller-owned evidence so F14
can remain generic.

## Backward Compatibility Guarantees

- Existing `log_audit_event(...)` calls continue to work without passing
  `pipeline_stage`.
- Existing evidence dictionaries are not mutated by the logger.
- Replay metadata is additive and optional; old events without it remain valid.
- `pipeline_stage` is additive and may be `NULL` for old imported rows.
- The audit table remains append-only; update and delete blockers stay intact.
- Feature flags for stricter future behavior remain off by default.

## Future Extension Intent

Future F2 Blueprint or recommendation systems should extend the evidence payload
by adding versioned keys, not by changing the F14 table for every domain detail.
If stricter validation is needed later, it should be introduced behind feature
flags and should not bypass the F16 validation/submission/audit path.

The intended boundary is simple:

1. F16 validates and submits scorecards.
2. F14 records immutable, reviewable evidence.
3. Downstream systems read evidence and reason from it without mutating history.
