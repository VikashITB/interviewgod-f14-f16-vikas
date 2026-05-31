"""
F14 — Audit Logger
==================
Centralized, append-only audit infrastructure for the Hiring Platform.

ARCHITECTURAL ROLE
------------------
F14 is shared platform infrastructure, not scorecard-specific.
Every module that writes a decision (scorecard submission, recommendation,
knockout, consent, HR override) calls log_audit_event() here.

The audit store is append-only by design:
  - In-memory for POC runtime  (swap → ORM insert in production)
  - SQL migration enforces no-UPDATE / no-DELETE at DB trigger level
  - No caller can mutate a past event — not even by importing this module

CALLER MAP (today stubs, tomorrow real)
-----------------------------------------
  scorecards/submission.py      → action_type: SCORECARD_SUBMITTED / SCORECARD_BLOCKED
  recommendation_worker.py      → action_type: RECOMMENDATION_GENERATED
  results/recommendation.py     → action_type: RECOMMENDATION_VIEWED
  candidates/knockout.py        → action_type: CANDIDATE_KNOCKED_OUT
  candidates/consent.py         → action_type: CONSENT_RECORDED
  HR override endpoint          → action_type: HR_OVERRIDE_APPLIED

PRODUCTION SWAP
---------------
Replace _AUDIT_STORE append + _persist_to_db stub with:
    db.session.add(AuditTrailORM(**event.model_dump()))
    db.session.commit()
Everything else (schema, helpers, callers) stays identical.
"""
from __future__ import annotations

import json
from database import get_connection

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field




# ---------------------------------------------------------------------------
# Action type registry
# Centralised here so callers import the enum — no raw string magic.
# ---------------------------------------------------------------------------

class ActionType(str, Enum):
    # Original F14 action taxonomy
    CANDIDATE_VIEWED           = "candidate_viewed"
    STAGE_ADVANCED             = "stage_advanced"
    SCORE_ASSIGNED             = "score_assigned"
    F14_RECOMMENDATION_GENERATED = "recommendation_generated"
    DECISION_MADE              = "decision_made"
    DECISION_OVERRIDDEN        = "decision_overridden"
    CONSENT_GRANTED            = "consent_granted"
    CONSENT_WITHDRAWN          = "consent_withdrawn"
    AI_PROCESSING_BLOCKED      = "ai_processing_blocked"
    F4_FALLBACK_USED           = "f4_fallback_used"

    # Scorecard
    SCORECARD_SUBMITTED         = "SCORECARD_SUBMITTED"
    SCORECARD_BLOCKED           = "SCORECARD_BLOCKED"

    # Recommendation engine
    RECOMMENDATION_GENERATED    = "RECOMMENDATION_GENERATED"
    RECOMMENDATION_VIEWED       = "RECOMMENDATION_VIEWED"

    # Candidate lifecycle
    CANDIDATE_KNOCKED_OUT       = "CANDIDATE_KNOCKED_OUT"
    CONSENT_RECORDED            = "CONSENT_RECORDED"

    # HR override
    HR_OVERRIDE_APPLIED         = "HR_OVERRIDE_APPLIED"

    # Generic / future
    GENERIC_EVENT               = "GENERIC_EVENT"


class PipelineStage(str, Enum):
    RESUME_SCREENING            = "RESUME_SCREENING"
    KNOCKOUT_CHECK              = "KNOCKOUT_CHECK"
    CALL_SCREENING              = "CALL_SCREENING"
    INTERVIEW_INTEGRITY         = "INTERVIEW_INTEGRITY"
    RECOMMENDATION              = "RECOMMENDATION"
    HR_OVERRIDE                 = "HR_OVERRIDE"
    FINAL_DECISION              = "FINAL_DECISION"


DEFAULT_PIPELINE_STAGE_BY_ACTION: dict[ActionType, PipelineStage] = {
    ActionType.CANDIDATE_VIEWED: PipelineStage.RESUME_SCREENING,
    ActionType.STAGE_ADVANCED: PipelineStage.CALL_SCREENING,
    ActionType.SCORE_ASSIGNED: PipelineStage.CALL_SCREENING,
    ActionType.F14_RECOMMENDATION_GENERATED: PipelineStage.RECOMMENDATION,
    ActionType.DECISION_MADE: PipelineStage.FINAL_DECISION,
    ActionType.DECISION_OVERRIDDEN: PipelineStage.HR_OVERRIDE,
    ActionType.CONSENT_GRANTED: PipelineStage.RESUME_SCREENING,
    ActionType.CONSENT_WITHDRAWN: PipelineStage.RESUME_SCREENING,
    ActionType.AI_PROCESSING_BLOCKED: PipelineStage.INTERVIEW_INTEGRITY,
    ActionType.F4_FALLBACK_USED: PipelineStage.INTERVIEW_INTEGRITY,
    ActionType.SCORECARD_SUBMITTED: PipelineStage.CALL_SCREENING,
    ActionType.SCORECARD_BLOCKED: PipelineStage.CALL_SCREENING,
    ActionType.RECOMMENDATION_GENERATED: PipelineStage.RECOMMENDATION,
    ActionType.RECOMMENDATION_VIEWED: PipelineStage.RECOMMENDATION,
    ActionType.CANDIDATE_KNOCKED_OUT: PipelineStage.KNOCKOUT_CHECK,
    ActionType.CONSENT_RECORDED: PipelineStage.RESUME_SCREENING,
    ActionType.HR_OVERRIDE_APPLIED: PipelineStage.HR_OVERRIDE,
}


ORIGINAL_F14_CATEGORY_BY_ACTION: dict[ActionType, str] = {
    ActionType.CANDIDATE_VIEWED: "candidate_viewed",
    ActionType.STAGE_ADVANCED: "stage_advanced",
    ActionType.SCORE_ASSIGNED: "score_assigned",
    ActionType.F14_RECOMMENDATION_GENERATED: "recommendation_generated",
    ActionType.RECOMMENDATION_GENERATED: "recommendation_generated",
    ActionType.DECISION_MADE: "decision_made",
    ActionType.DECISION_OVERRIDDEN: "decision_overridden",
    ActionType.CONSENT_GRANTED: "consent_granted",
    ActionType.CONSENT_WITHDRAWN: "consent_withdrawn",
    ActionType.AI_PROCESSING_BLOCKED: "ai_processing_blocked",
    ActionType.F4_FALLBACK_USED: "f4_fallback_used",
    ActionType.SCORECARD_SUBMITTED: "score_assigned",
    ActionType.SCORECARD_BLOCKED: "ai_processing_blocked",
    ActionType.RECOMMENDATION_VIEWED: "candidate_viewed",
    ActionType.CANDIDATE_KNOCKED_OUT: "decision_made",
    ActionType.CONSENT_RECORDED: "consent_granted",
    ActionType.HR_OVERRIDE_APPLIED: "decision_overridden",
    ActionType.GENERIC_EVENT: "generic_event",
}


EVIDENCE_SCHEMA_VERSION = "v1"


# ---------------------------------------------------------------------------
# AuditEvent — the canonical shape of every audit record.
# Fields are intentionally generic. No scorecard-specific fields live here.
# ---------------------------------------------------------------------------

class AuditEvent(BaseModel):
    """
    Immutable record of a platform action.

    Immutability contract:
        - event_id is assigned once on creation (UUID4)
        - created_at is UTC-stamped on creation
        - model_config forbids post-creation field mutation
        - DB layer enforces no UPDATE / DELETE (see migration 008)
    """

    model_config = {"frozen": True}

    # Identity
    event_id:          str       = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at:        datetime  = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Context
    action_type:       ActionType
    pipeline_stage:    Optional[PipelineStage] = None
    candidate_id:      Optional[str] = None
    round_id:          Optional[str] = None
    hiring_group_id:   Optional[str] = None

    # Actor
    actor_id:          str
    actor_email:       str

    # Payload snapshot
    evidence_snapshot: Optional[dict[str, Any]] = None

    # Optional debug summary
    summary:           Optional[str] = None


# ---------------------------------------------------------------------------
# In-memory store
# Production: replace with DB session insert.
# ---------------------------------------------------------------------------

_AUDIT_STORE: list[AuditEvent] = []


# ---------------------------------------------------------------------------
# Core write path
# ---------------------------------------------------------------------------

def log_audit_event(
    action_type:       ActionType | str,
    actor_id:          str,
    actor_email:       str,
    pipeline_stage:    Optional[PipelineStage | str] = None,
    candidate_id:      Optional[str]       = None,
    round_id:          Optional[str]       = None,
    hiring_group_id:   Optional[str]       = None,
    evidence_snapshot: Optional[dict]      = None,
    summary:           Optional[str]       = None,
) -> AuditEvent:
    """
    Append one immutable audit event.
    """

    resolved_action_type = normalize_action_type(action_type)

    resolved_pipeline_stage = _resolve_pipeline_stage(
        action_type=resolved_action_type,
        pipeline_stage=pipeline_stage,
    )

    event = AuditEvent(
        action_type=resolved_action_type,
        pipeline_stage=resolved_pipeline_stage,
        actor_id=actor_id,
        actor_email=actor_email,
        candidate_id=candidate_id,
        round_id=round_id,
        hiring_group_id=hiring_group_id,
        evidence_snapshot=evidence_snapshot,
        summary=summary,
    )

    _AUDIT_STORE.append(event)
    _persist_to_db(event)

    return event


def normalize_action_type(action_type: ActionType | str) -> ActionType:
    """
    Resolve original F14 strings and semantic replay extensions to ActionType.
    """

    if isinstance(action_type, ActionType):
        return action_type

    return ActionType(action_type)


def get_original_f14_action_category(action_type: ActionType | str) -> str:
    resolved_action_type = normalize_action_type(action_type)
    return ORIGINAL_F14_CATEGORY_BY_ACTION[resolved_action_type]


def _with_taxonomy_metadata(
    action_type: ActionType,
    evidence_snapshot: Optional[dict],
) -> Optional[dict]:

    if evidence_snapshot is None:
        return None

    if "original_f14_action_category" in evidence_snapshot:
        return evidence_snapshot

    return {
        **evidence_snapshot,
        "original_f14_action_category":
            get_original_f14_action_category(action_type),
        "semantic_action_type":
            action_type.value,
    }


def _persist_to_db(event: AuditEvent) -> None:

    conn = get_connection()

    cursor = conn.cursor()

    _ensure_audit_table_shape(cursor)

    conn.commit()

    cursor.execute("""

    INSERT INTO audit_trail (

        event_id,
        created_at,
        action_type,
        pipeline_stage,

        candidate_id,
        round_id,
        hiring_group_id,

        actor_id,
        actor_email,

        evidence_snapshot,
        summary

    )

    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

    """, (

        event.event_id,
        event.created_at,
        event.action_type.value,
        event.pipeline_stage.value if event.pipeline_stage else None,

        event.candidate_id,
        event.round_id,
        event.hiring_group_id,

        event.actor_id,
        event.actor_email,

        (
            json.dumps(event.evidence_snapshot)
            if event.evidence_snapshot is not None
            else None
        ),
        event.summary

    ))

    conn.commit()

    conn.close()
    

def _resolve_pipeline_stage(
    action_type: ActionType,
    pipeline_stage: Optional[PipelineStage | str],
) -> Optional[PipelineStage]:

    if pipeline_stage is None:
        return DEFAULT_PIPELINE_STAGE_BY_ACTION.get(action_type)

    if isinstance(pipeline_stage, PipelineStage):
        return pipeline_stage

    return PipelineStage(pipeline_stage)


def _ensure_audit_table_shape(cursor) -> None:
    """
    Ensure SQLite audit storage exists while preserving append-only events.
    """

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_trail (

        event_id TEXT PRIMARY KEY,
        created_at TEXT NOT NULL,
        action_type TEXT NOT NULL,
        pipeline_stage TEXT,

        candidate_id TEXT,
        round_id TEXT,
        hiring_group_id TEXT,

        actor_id TEXT,
        actor_email TEXT,

        evidence_snapshot TEXT,
        summary TEXT

    )
    """)

    cursor.execute("PRAGMA table_info(audit_trail)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    if "pipeline_stage" not in existing_columns:
        cursor.execute("""
        ALTER TABLE audit_trail
        ADD COLUMN pipeline_stage TEXT
        """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_audit_candidate_id
    ON audit_trail (candidate_id)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_audit_hiring_group_id
    ON audit_trail (hiring_group_id)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_audit_created_at
    ON audit_trail (created_at)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_audit_action_type
    ON audit_trail (action_type)
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_audit_pipeline_stage
    ON audit_trail (pipeline_stage)
    """)

    cursor.execute("""
    CREATE TRIGGER IF NOT EXISTS block_audit_update
    BEFORE UPDATE ON audit_trail
    FOR EACH ROW
    BEGIN
        SELECT RAISE(
            ABORT,
            'audit_trail is append-only. UPDATE is forbidden.'
        );
    END;
    """)

    cursor.execute("""
    CREATE TRIGGER IF NOT EXISTS block_audit_delete
    BEFORE DELETE ON audit_trail
    FOR EACH ROW
    BEGIN
        SELECT RAISE(
            ABORT,
            'audit_trail is append-only. DELETE is forbidden.'
        );
    END;
    """)


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def query_by_candidate(candidate_id: str) -> list[AuditEvent]:
    return [e for e in _AUDIT_STORE if e.candidate_id == candidate_id]


def query_by_candidate_from_db(candidate_id: str) -> list[AuditEvent]:

    conn = get_connection()

    cursor = conn.cursor()

    _ensure_audit_table_shape(cursor)

    cursor.execute("""

    SELECT
        event_id,
        created_at,
        action_type,
        pipeline_stage,
        candidate_id,
        round_id,
        hiring_group_id,
        actor_id,
        actor_email,
        evidence_snapshot,
        summary

    FROM audit_trail

    WHERE candidate_id = ?

    ORDER BY created_at ASC

    """, (candidate_id,))

    rows = cursor.fetchall()

    conn.close()

    return [
        _audit_event_from_db_row(row)
        for row
        in rows
    ]


def query_by_hiring_group(hiring_group_id: str) -> list[AuditEvent]:
    return [e for e in _AUDIT_STORE if e.hiring_group_id == hiring_group_id]


def query_by_hiring_group_from_db(hiring_group_id: str) -> list[AuditEvent]:

    conn = get_connection()

    cursor = conn.cursor()

    _ensure_audit_table_shape(cursor)

    cursor.execute("""

    SELECT
        event_id,
        created_at,
        action_type,
        pipeline_stage,
        candidate_id,
        round_id,
        hiring_group_id,
        actor_id,
        actor_email,
        evidence_snapshot,
        summary

    FROM audit_trail

    WHERE hiring_group_id = ?

    ORDER BY created_at ASC

    """, (hiring_group_id,))

    rows = cursor.fetchall()

    conn.close()

    return [
        _audit_event_from_db_row(row)
        for row
        in rows
    ]


def query_by_action_type_from_db(action_type: ActionType | str) -> list[AuditEvent]:

    resolved_action_type = normalize_action_type(action_type)

    conn = get_connection()

    cursor = conn.cursor()

    _ensure_audit_table_shape(cursor)

    cursor.execute("""

    SELECT
        event_id,
        created_at,
        action_type,
        pipeline_stage,
        candidate_id,
        round_id,
        hiring_group_id,
        actor_id,
        actor_email,
        evidence_snapshot,
        summary

    FROM audit_trail

    WHERE action_type = ?

    ORDER BY created_at ASC

    """, (resolved_action_type.value,))

    rows = cursor.fetchall()

    conn.close()

    return [
        _audit_event_from_db_row(row)
        for row
        in rows
    ]


def query_by_pipeline_stage(
    pipeline_stage: PipelineStage | str,
) -> list[AuditEvent]:

    resolved_pipeline_stage = (
        pipeline_stage
        if isinstance(pipeline_stage, PipelineStage)
        else PipelineStage(pipeline_stage)
    )

    return [
        e
        for e
        in _AUDIT_STORE
        if e.pipeline_stage == resolved_pipeline_stage
    ]


def query_by_date_range(
    start: datetime,
    end: datetime,
) -> list[AuditEvent]:

    return [e for e in _AUDIT_STORE if start <= e.created_at <= end]


def query_all() -> list[AuditEvent]:
    return list(_AUDIT_STORE)


def _audit_event_from_db_row(row) -> AuditEvent:

    evidence_snapshot = None

    if row[9]:
        evidence_snapshot = (
            row[9]
            if isinstance(row[9], dict)
            else json.loads(row[9])
        )

    pipeline_stage = (
        PipelineStage(row[3])
        if row[3]
        else None
    )

    return AuditEvent(
        event_id=str(row[0]),
        created_at=(
            row[1]
            if isinstance(row[1], datetime)
            else datetime.fromisoformat(row[1])
        ),
        action_type=ActionType(row[2]),
        pipeline_stage=pipeline_stage,
        candidate_id=row[4],
        round_id=row[5],
        hiring_group_id=row[6],
        actor_id=row[7],
        actor_email=row[8],
        evidence_snapshot=evidence_snapshot,
        summary=row[10],
    )


def get_store_count() -> int:
    return len(_AUDIT_STORE)


def clear_store_for_testing() -> None:
    _AUDIT_STORE.clear()


# ---------------------------------------------------------------------------
# UPDATE / DELETE guard
# ---------------------------------------------------------------------------

class AuditMutationForbidden(Exception):
    pass


def update_audit_event(*args, **kwargs):
    raise AuditMutationForbidden(
        "Audit events are immutable. UPDATE is forbidden at both application "
        "and database level. See migrations/008_add_audit_trail.sql."
    )


def delete_audit_event(*args, **kwargs):
    raise AuditMutationForbidden(
        "Audit events are immutable. DELETE is forbidden at both application "
        "and database level. See migrations/008_add_audit_trail.sql."
    )


# ---------------------------------------------------------------------------
# Integration stubs
# ---------------------------------------------------------------------------

class IntegrationExamples:

    @staticmethod
    def recommendation_worker_example():

        log_audit_event(
            action_type=ActionType.RECOMMENDATION_GENERATED,
            actor_id="worker::recommendation_engine",
            actor_email="system@platform.internal",
            candidate_id="cand_001",
            round_id="round_007",
            hiring_group_id="hg_eng_backend",
            evidence_snapshot={
                "recommendation_score": 82.5,
                "model_version": "v3.1",
                "contributing_signals": ["scorecard", "resume_score"],
            },
            summary="Recommendation score 82.5 generated for cand_001",
        )

    @staticmethod
    def recommendation_view_example():

        log_audit_event(
            action_type=ActionType.RECOMMENDATION_VIEWED,
            actor_id="recruiter_u42",
            actor_email="recruiter@company.com",
            candidate_id="cand_001",
            hiring_group_id="hg_eng_backend",
            evidence_snapshot={"viewed_at_stage": "final_round"},
            summary="Recommendation viewed by recruiter_u42",
        )

    @staticmethod
    def candidate_knockout_example():

        log_audit_event(
            action_type=ActionType.CANDIDATE_KNOCKED_OUT,
            actor_id="system::knockout_engine",
            actor_email="system@platform.internal",
            candidate_id="cand_099",
            round_id="round_screening",
            hiring_group_id="hg_eng_backend",
            evidence_snapshot={
                "knockout_reason": "minimum_years_experience_not_met",
                "required": 5,
                "provided": 2,
            },
            summary="Candidate cand_099 knocked out at screening",
        )

    @staticmethod
    def hr_override_example():

        log_audit_event(
            action_type=ActionType.HR_OVERRIDE_APPLIED,
            actor_id="hr_director_u01",
            actor_email="hr.director@company.com",
            candidate_id="cand_001",
            round_id="round_final",
            hiring_group_id="hg_eng_backend",
            evidence_snapshot={
                "original_decision": "REJECTED",
                "override_decision": "ADVANCE",
                "override_justification": "Exceptional portfolio reviewed offline",
            },
            summary="HR override: cand_001 advanced despite system rejection",
        )


# ---------------------------------------------------------------------------
# Backward compatibility alias
# ---------------------------------------------------------------------------

F14IntegrationStubs = IntegrationExamples
