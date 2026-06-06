from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import set_database_path_for_testing
from scripts.formatters import format_audit_timeline_human, export_timeline_json, pretty_json
from utils.audit_logger import (
    query_by_candidate_from_db,
)


DEFAULT_CANDIDATE_ID = "cand_backend_001"
DEMO_DB_PATH = os.path.join(os.path.dirname(__file__), "synthetic_pipeline.db")


def ensure_demo_database() -> None:
    if os.path.exists(DEMO_DB_PATH):
        set_database_path_for_testing(DEMO_DB_PATH)


def main() -> int:
    ensure_demo_database()
    candidate_id = DEFAULT_CANDIDATE_ID
    events = query_by_candidate_from_db(candidate_id)

    print("\n" + "=" * 50)
    print("CANDIDATE TIMELINE RECONSTRUCTION")
    print("=" * 50)

    print(f"\nCandidate ID: {candidate_id}")
    print(f"Events Found: {len(events)}")

    if not events:
        print("\nNo audit history found for this candidate.")
        return 0

    print("\n" + "-" * 50)
    print(format_audit_timeline_human(events))

    print("\n" + "-" * 50)
    print("JSON SNAPSHOT")
    print(pretty_json(export_timeline_json(events)))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
