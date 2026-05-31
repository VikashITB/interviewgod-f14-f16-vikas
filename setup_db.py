from database import get_connection


conn = get_connection()
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS audit_trail (
    event_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    action_type TEXT NOT NULL,
    pipeline_stage TEXT,
    candidate_id TEXT,
    round_id TEXT,
    hiring_group_id TEXT,
    actor_id TEXT NOT NULL,
    actor_email TEXT NOT NULL,
    evidence_snapshot TEXT,
    summary TEXT
)
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

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_audit_candidate_id
ON audit_trail (candidate_id)
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_audit_pipeline_stage
ON audit_trail (pipeline_stage)
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_audit_hiring_group_id
ON audit_trail (hiring_group_id)
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_audit_action_type
ON audit_trail (action_type)
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_audit_created_at
ON audit_trail (created_at)
""")

conn.commit()
conn.close()

print("SQLite audit_trail table created")
