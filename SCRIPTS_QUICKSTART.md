# Synthetic Pipeline Scripts - Quick Start Guide

## Overview
Six Python scripts for demonstrating the InterviewGod F14/F16/F3 hiring pipeline with audit logging, recruiter-friendly output, and failure-case validation.

## Running the Scripts

### 1. Full Pipeline Demo (Multiple Output Modes)
```bash
# Default: Both human and JSON output
python scripts/run_full_pipeline.py

# Human-friendly recruiter output only
python scripts/run_full_pipeline.py --view human

# JSON snapshots only (deterministic, machine-readable)
python scripts/run_full_pipeline.py --view json

# Both human and JSON sections sequentially
python scripts/run_full_pipeline.py --view both
```

**Output**: Blueprint, Candidate, Scorecard, Audit Timeline, Replay Validation
**Database**: Creates fresh `scripts/synthetic_pipeline.db` (deleted and recreated each run)

### 2. Failure Case Validation
```bash
python scripts/run_failure_cases.py
```

**Tests** (all should pass):
- ✓ Missing required competency blocked
- ✓ Missing evidence blocked
- ✓ Duplicate competency blocked
- ✓ Feature flag OFF preserves behavior
- ✓ Invalid normalized score rejected
- ✓ Unknown competency rejected
- ✓ Blocked submissions emit audit event

**Result**: Shows deterministic negative-path validation working correctly

### 3. Candidate Timeline Reconstruction
```bash
python scripts/replay_candidate_timeline.py
```

**Output**: 
- Human-readable audit event timeline
- JSON export of all events for the candidate
- Event count and pipeline stage progression

**Uses**: Demo database from previous pipeline run (auto-connects)

### 4. Audit Store Inspection
```bash
python scripts/inspect_audit_store.py
```

**Output**:
- Total audit rows
- Unique event IDs (validates no duplicates)
- Candidate coverage (all rows include candidate_id)
- Action type enumeration
- JSON validation report

**Uses**: Demo database (auto-connects)

## Full Integration Test Suite

```bash
# All tests (49 total)
python -m pytest tests/ -v

# Specific test file
python -m pytest tests/test_full_integration_flow.py -v
python -m pytest tests/test_f16_scorecard.py -v
python -m pytest tests/test_audit_logger.py -v
python -m pytest tests/test_regression.py -v
```

**Result**: 49/49 tests PASS with append-only audit semantics, replay safety, and feature flag isolation

## Pipeline Architecture

### F14 (Append-Only Audit Trail)
- SQLite triggers prevent UPDATE/DELETE on audit_trail table
- Every action emits immutable AuditEvent with timestamp, actor, summary
- Replay metadata captures blueprint version and feature flag state at submission time

### F16 (Interviewer Scorecard)
- Submit-only: No edits after validation passes
- Validates: All required competencies rated, evidence present, scores match labels
- Blocks invalid submissions, emits SCORECARD_BLOCKED event instead of SCORECARD_SUBMITTED

### F3 (Candidate Shell)
- Resume signals with competency scores (0-100)
- Consent tracking (GRANTED/REVOKED)
- Blueprint alignment for hiring group

### Replay Infrastructure
- All audit events include replay_metadata snapshot
- Blueprint version pinned at scorecard submission time
- Feature flags captured in events for deterministic reconstruction

## Key Features

✅ **Deterministic Output**: Same data produces identical results
✅ **Append-Only Audit**: SQLite triggers enforce immutability
✅ **Recruiter-Friendly**: Human output (--view human) with clean formatting
✅ **JSON Export**: Deterministic JSON snapshots for automation
✅ **Negative-Path Testing**: Comprehensive failure case validation
✅ **No Regressions**: 49/49 tests pass, zero breaking changes

## Output Formatting

**Human Output** (`--view human`):
- Clean, recruiter-focused presentation
- Competency ratings with ASCII formatting (-, not •)
- Timeline with event summaries
- Validation report (pass/fail on audit integrity)

**JSON Output** (`--view json`):
- Deterministic formatting (sorted keys)
- UTC timestamps in ISO 8601 format
- Enum values converted to strings
- Complete audit event snapshots

## Database Management

**Automatic Cleanup**: Each `run_full_pipeline.py` invocation:
1. Deletes existing `scripts/synthetic_pipeline.db`
2. Creates fresh database with audit_trail table
3. Initializes with SQLite triggers (append-only enforcement)
4. Populates with deterministic test data

**Manual Database Reset**:
```bash
rm scripts/synthetic_pipeline.db
```

## Configuration

All configuration via `config/feature_flags.py`:
- `f14_audit_logger` (default: OFF) - Enable append-only audit trail
- `f16_interviewer_scorecard` (default: OFF) - Enable scorecard validation
- `f14_replay_reconstruction` (default: OFF) - Include replay metadata in events

## Competency IDs (Backend Engineer Blueprint)
**Always use lower-case**:
- python
- fastapi
- docker
- system_design

Mismatched case causes validation errors: "Missing ratings for required competencies: ['Python', ...]"

## Troubleshooting

**UnicodeEncodeError on Windows**: Formatters now use ASCII-safe characters (-, ->, no •, └─)

**Database locked error**: Delete `scripts/synthetic_pipeline.db` and retry

**Feature flag not applying**: Ensure `clear_store_for_testing()` called before `set_feature_enabled()`

**Missing competency error**: Check competency IDs are lower-case

## Next Steps

1. **Run all scripts** in sequence: `run_full_pipeline.py`, `run_failure_cases.py`, `replay_candidate_timeline.py`, `inspect_audit_store.py`
2. **Inspect JSON output** for automation integration: `python scripts/run_full_pipeline.py --view json`
3. **Review test coverage**: `pytest tests/ -v` (49 tests)
4. **Extend pipeline**: Add new competencies to synthetic_blueprint.py and regenerate demo DB
