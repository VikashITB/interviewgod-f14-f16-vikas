# InterviewGod 2.5.3 - F14/F16 Sprint

Week 1 sprint implementation for auditability, replayability, evidence
traceability, recruiter reviewability, and safe Week 2 integration.

## Architecture Overview

This repository contains two backend modules:

- F14 Audit Logger: shared append-only audit infrastructure for platform
  decisions.
- F16 Interviewer Scorecard: blueprint-aware structured scorecards with
  validation, evidence capture, and calibration checks.

The current sprint persistence layer is SQLite. It keeps infrastructure simple
while preserving stable public boundaries: `database.get_connection()`,
`utils.audit_logger.log_audit_event()`, and the F16 submission pipeline.

## Repository Structure

```text
InterviewGod/
├── README.md
├── requirements.txt
├── .gitignore
├── database.py
├── setup_db.py
├── blueprints/
│   ├── __init__.py
│   └── models.py
├── config/
│   ├── __init__.py
│   └── feature_flags.py
├── docs/
│   ├── f14_f16_architecture_notes.md
│   └── week2_regression_readiness.md
├── utils/
│   ├── __init__.py
│   └── audit_logger.py
├── scorecards/
│   ├── __init__.py
│   ├── schema.py
│   ├── validator.py
│   ├── submission.py
│   └── calibration.py
├── replay/
│   ├── __init__.py
│   └── reconstruct_candidate_timeline.py
├── demos/
│   ├── __init__.py
│   ├── audit_benchmark.py
│   ├── schema_demo.py
│   ├── synthetic_demo.py
│   ├── terminal_demo.py
│   └── view_audit_logs.py
├── tests/
│   ├── __init__.py
│   ├── test_audit_logger.py
│   └── test_f16_scorecard.py
└── migrations/
    ├── 008_add_audit_trail.sql
    └── 009_add_interviewer_scorecard.sql
```

## F14 Audit Logger

F14 is generic platform infrastructure. It records immutable audit events for
scorecard submissions, blocked submissions, recommendation generation, knockout
checks, consent, and HR override flows.

The single write path is:

```python
from utils.audit_logger import ActionType, log_audit_event

log_audit_event(
    action_type=ActionType.SCORECARD_SUBMITTED,
    actor_id="interviewer_vikas",
    actor_email="vikas@company.com",
    candidate_id="cand_001",
    round_id="round_007",
    hiring_group_id="hg_eng_backend",
    evidence_snapshot={"normalized_scores": {"system_design": 75}},
    summary="Scorecard submitted for round_007",
)
```

F14 remains append-only. Application helpers reject update/delete attempts, and
SQLite triggers block direct `UPDATE` and `DELETE` statements on `audit_trail`.

## F16 Scorecard System

F16 replaces free-text interview feedback with blueprint-driven scorecards.
Blueprint contract models live in `blueprints.models`; `scorecards.schema`
keeps compatibility imports for Week 1 callers. The schema generator only
materializes deterministic scorecard schemas from the blueprint contract.

Validation stays pure and runs before persistence:

```text
submit_scorecard()
  -> validate_scorecard()
  -> if invalid: emit SCORECARD_BLOCKED audit event
  -> if valid: persist scorecard, emit SCORECARD_SUBMITTED, run calibration
```

Calibration detects interviewer scoring drift after enough submitted
scorecards. Week 2 feature flags are off by default in `config.feature_flags`;
tests and demos opt into F16 explicitly.

## SQLite Persistence

SQLite is the active sprint persistence layer. The local database file is
`hiring_platform.db` and is intentionally ignored by Git.

Run setup before demos or tests:

```bash
python setup_db.py
```

The audit table stores `evidence_snapshot` as serialized JSON at the database
boundary. In application code it remains a flexible dictionary owned by callers.

## Replayability

Audit evidence includes `evidence_schema_version` and optional
`replay_metadata` with blueprint versions, schema versions, evaluator versions,
feature flags, and threshold snapshots. This keeps historical decisions
explainable without hardcoding scorecard-only fields into F14.

## Timeline Reconstruction

The replay module reads persisted audit events and reconstructs a
candidate-focused timeline for recruiter review:

```bash
python replay/reconstruct_candidate_timeline.py --latest-only --stage-order
```

For demo reviews that should show the latest replayable evidence payload, use:

```bash
python replay/reconstruct_candidate_timeline.py --latest-semantic-event --stage-order
```

## Demos

```bash
python demos/synthetic_demo.py
python demos/schema_demo.py
python demos/terminal_demo.py
python demos/view_audit_logs.py
python demos/audit_benchmark.py
```

- `synthetic_demo.py` generates replayable audit events using schema-conformant
  scorecards and contract-derived metadata.
- `schema_demo.py` shows the scorecard shape reviewers should expect from
  blueprint-driven schema materialization.
- `terminal_demo.py` runs the end-to-end F14/F16 flow, including immutable audit
  logging, blocked mutations, validation, submission, and calibration.
- `view_audit_logs.py` gives reviewer-visible audit output for persisted local
  events.
- `audit_benchmark.py` exercises audit infrastructure behavior under repeated
  writes for lightweight regression confidence.

## Tests

```bash
python tests/test_audit_logger.py
python tests/test_f16_scorecard.py
```

## Future Direction

A PostgreSQL migration can be reconsidered later if deployment needs a server
database. For this sprint, SQLite is the merge-ready implementation because it
keeps the architecture stable, replayable, and easy to review.
