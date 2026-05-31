-- =============================================================================
-- Migration: 008_add_audit_trail.sql
-- Feature:   Audit Logger
-- Sprint:    Week 1
-- Owner:     Vikas
-- =============================================================================
--
-- PURPOSE
-- -------
-- Creates the append-only SQLite audit_trail table that backs
-- utils/audit_logger.py.
--
-- IMMUTABILITY ENFORCEMENT
-- ------------------------
-- UPDATE and DELETE are blocked at database level via SQLite triggers.
-- Application-level guards in audit_logger.py are secondary protection only.
--
-- ROLLBACK STRATEGY
-- -----------------
-- This migration is intentionally NOT reversible. Audit records are compliance
-- evidence. Once created they must not be destroyed.
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS audit_trail (
    event_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    action_type TEXT NOT NULL CHECK (
        action_type IN (
            'candidate_viewed',
            'stage_advanced',
            'score_assigned',
            'recommendation_generated',
            'decision_made',
            'decision_overridden',
            'consent_granted',
            'consent_withdrawn',
            'ai_processing_blocked',
            'f4_fallback_used',
            'SCORECARD_SUBMITTED',
            'SCORECARD_BLOCKED',
            'RECOMMENDATION_GENERATED',
            'RECOMMENDATION_VIEWED',
            'CANDIDATE_KNOCKED_OUT',
            'CONSENT_RECORDED',
            'HR_OVERRIDE_APPLIED',
            'GENERIC_EVENT'
        )
    ),
    pipeline_stage TEXT CHECK (
        pipeline_stage IS NULL
        OR pipeline_stage IN (
            'RESUME_SCREENING',
            'KNOCKOUT_CHECK',
            'CALL_SCREENING',
            'INTERVIEW_INTEGRITY',
            'RECOMMENDATION',
            'HR_OVERRIDE',
            'FINAL_DECISION'
        )
    ),
    candidate_id TEXT,
    round_id TEXT,
    hiring_group_id TEXT,
    actor_id TEXT NOT NULL,
    actor_email TEXT NOT NULL,
    evidence_snapshot TEXT,
    summary TEXT,
    schema_version INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_audit_candidate_id
    ON audit_trail (candidate_id);

CREATE INDEX IF NOT EXISTS idx_audit_hiring_group_id
    ON audit_trail (hiring_group_id);

CREATE INDEX IF NOT EXISTS idx_audit_created_at
    ON audit_trail (created_at);

CREATE INDEX IF NOT EXISTS idx_audit_action_type
    ON audit_trail (action_type);

CREATE INDEX IF NOT EXISTS idx_audit_pipeline_stage
    ON audit_trail (pipeline_stage);

CREATE TRIGGER IF NOT EXISTS block_audit_update
BEFORE UPDATE ON audit_trail
FOR EACH ROW
BEGIN
    SELECT RAISE(
        ABORT,
        'audit_trail is append-only. UPDATE is forbidden.'
    );
END;

CREATE TRIGGER IF NOT EXISTS block_audit_delete
BEFORE DELETE ON audit_trail
FOR EACH ROW
BEGIN
    SELECT RAISE(
        ABORT,
        'audit_trail is append-only. DELETE is forbidden.'
    );
END;

CREATE TABLE IF NOT EXISTS schema_migrations (
    migration_id TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

INSERT OR IGNORE INTO schema_migrations (
    migration_id,
    description
)
VALUES (
    '008_add_audit_trail',
    'Audit logger append-only table with immutable SQLite triggers'
);

COMMIT;
