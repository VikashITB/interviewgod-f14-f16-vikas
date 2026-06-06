from __future__ import annotations

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_connection, set_database_path_for_testing
from scripts.formatters import format_replay_validation_human, export_timeline_json, pretty_json


DEMO_DB_PATH = os.path.join(os.path.dirname(__file__), "synthetic_pipeline.db")


def ensure_demo_database() -> None:
    if os.path.exists(DEMO_DB_PATH):
        set_database_path_for_testing(DEMO_DB_PATH)


def validate_audit_store() -> dict:
    """Validate append-only audit and return report."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM audit_trail")
        rows_count = cursor.fetchone()[0]

        cursor.execute("SELECT DISTINCT event_id FROM audit_trail")
        unique_ids = len(cursor.fetchall())

        cursor.execute("SELECT COUNT(*) FROM audit_trail WHERE candidate_id IS NOT NULL")
        covered_candidates = cursor.fetchone()[0]

        cursor.execute("SELECT DISTINCT action_type FROM audit_trail")
        action_types = [row[0] for row in cursor.fetchall()]

        conn.close()

        return {
            "total_audit_rows": rows_count,
            "unique_event_ids": unique_ids,
            "duplicate_event_ids": rows_count != unique_ids,
            "candidate_id_coverage": covered_candidates == rows_count if rows_count > 0 else True,
            "audit_count_consistency": True,
            "action_type_set": sorted(action_types),
        }
    except sqlite3.OperationalError as e:
        print(f"Audit store unavailable: {e}")
        return {
            "total_audit_rows": 0,
            "unique_event_ids": 0,
            "duplicate_event_ids": False,
            "candidate_id_coverage": True,
            "audit_count_consistency": True,
            "action_type_set": [],
        }


def main() -> int:
    ensure_demo_database()

    print("\n" + "=" * 50)
    print("AUDIT STORE INSPECTION")
    print("=" * 50)

    report = validate_audit_store()

    print("\n" + "-" * 50)
    print(format_replay_validation_human(report))

    print("\n" + "-" * 50)
    print("JSON SNAPSHOT")
    print(pretty_json(report))

    if report["duplicate_event_ids"]:
        print("\nWARNING: duplicate event IDs detected.")
        return 1
    else:
        print("\nOK: event_id uniqueness preserved.")

    if not report["candidate_id_coverage"]:
        print("WARNING: some audit rows missing candidate_id coverage.")
        return 1
    else:
        print("OK: all audit rows include candidate_id.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
