# Week 2 Regression Readiness

This note captures the lightweight safeguards expected before Week 2
integration. It is documentation and configuration support only; it does not
change the F14/F16 ownership boundaries.

## Feature Flag Expectations

- Week 2 flags live in `config.feature_flags`.
- All feature flags are off by default.
- Unknown feature flags must fail safely as disabled.
- Tests and demos that need the F16 path must opt in explicitly with
  `set_feature_enabled("f16_interviewer_scorecard", True)`.

## Old Flow Preservation

- Existing Week 1 imports through `scorecards.schema` remain supported.
- F16 still validates before any scorecard persistence.
- Blocked scorecards still emit `SCORECARD_BLOCKED` audit events.
- Submitted scorecards still emit `SCORECARD_SUBMITTED` audit events and then
  trigger calibration.

## Test Isolation Expectations

- Regression tests must not write to the shared local `hiring_platform.db`.
- Tests should call `set_database_path_for_testing(...)` with a temporary
  SQLite file before writing audit events.
- Each test setup should clear in-memory stores after selecting its isolated
  database path.
- Parallel test runs should not contend on the same SQLite file.

## Replay Determinism Expectations

- Replay metadata must include `blueprint_id`, `blueprint_version`,
  `schema_version`, `evaluator_version`, and a threshold snapshot.
- Historical audit events must be interpreted from their stored metadata, not
  from newer runtime defaults.
- Timeline reconstruction remains read-only and does not mutate audit history.

## Blueprint Contract Expectations

- Blueprint competencies are owned by `blueprints.models.RoleBlueprint`.
- Schema materialization must not invent competencies.
- Synthetic scorecards must use the generated schema and score scale.
- Validation must reject competencies that are not present in the contract.

## Append-Only Guarantees

- F14 remains the generic immutable audit layer.
- Audit logger models must not become scorecard-specific.
- SQLite `audit_trail` update and delete blockers must remain in place.
- Local database files are ignored by Git and should not be deleted
  automatically by hardening tasks.
