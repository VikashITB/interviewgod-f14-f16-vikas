-- =============================================================================
-- Migration: 009_add_interviewer_scorecard.sql
-- Feature:   Interviewer Scorecard Architecture
-- Sprint:    Week 1
-- Owner:     Vikas
-- Depends:   008_add_audit_trail.sql
-- =============================================================================
--
-- PURPOSE
-- -------
-- Creates the interviewer_scorecard table using SQLite-compatible syntax.
--
-- NOTE
-- ----
-- Runtime F16 submission still owns the validation -> persistence -> audit
-- logging flow. This table definition preserves a future SQL-backed scorecard
-- shape without adding a second database-side audit write path.
-- =============================================================================

BEGIN;

CREATE TABLE IF NOT EXISTS interviewer_scorecard (
    scorecard_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    round_id TEXT NOT NULL,
    interviewer_id TEXT NOT NULL,
    blueprint_id TEXT NOT NULL,
    blueprint_version TEXT NOT NULL,
    competency_ratings TEXT NOT NULL DEFAULT '[]',
    overall_recommendation TEXT CHECK (
        overall_recommendation IS NULL
        OR overall_recommendation IN (
            'STRONG_NO',
            'NO',
            'NEUTRAL',
            'YES',
            'STRONG_YES'
        )
    ),
    status TEXT NOT NULL DEFAULT 'DRAFT' CHECK (
        status IN (
            'DRAFT',
            'SUBMITTED',
            'BLOCKED'
        )
    ),
    submitted_at TEXT,
    UNIQUE (round_id, interviewer_id)
);

CREATE INDEX IF NOT EXISTS idx_scorecard_round_id
    ON interviewer_scorecard (round_id);

CREATE INDEX IF NOT EXISTS idx_scorecard_interviewer_id
    ON interviewer_scorecard (interviewer_id);

CREATE INDEX IF NOT EXISTS idx_scorecard_status
    ON interviewer_scorecard (status);

CREATE INDEX IF NOT EXISTS idx_scorecard_blueprint_id
    ON interviewer_scorecard (
        blueprint_id,
        blueprint_version
    );

CREATE TRIGGER IF NOT EXISTS trg_scorecard_updated_at
AFTER UPDATE ON interviewer_scorecard
FOR EACH ROW
WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE interviewer_scorecard
    SET updated_at = CURRENT_TIMESTAMP
    WHERE scorecard_id = OLD.scorecard_id;
END;

INSERT OR IGNORE INTO schema_migrations (
    migration_id,
    description
)
VALUES (
    '009_add_interviewer_scorecard',
    'Interviewer scorecard table'
);

COMMIT;
