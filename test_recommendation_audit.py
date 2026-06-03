import sqlite3
import tempfile
from pathlib import Path

from database import set_database_path_for_testing
from scorecards.submission import record_recommendation_generated_audit


def main() -> int:
    db_path = Path(tempfile.mkdtemp()) / "recommendation_audit.sqlite"
    set_database_path_for_testing(db_path)

    candidate_id = "cand_recommendation_day2"

    record_recommendation_generated_audit(candidate_id)

    query = """
    SELECT action_type, candidate_id, created_at
    FROM audit_trail
    WHERE action_type = ? AND candidate_id = ?
    ORDER BY created_at DESC
    LIMIT 1
    """

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            query,
            ("recommendation_generated", candidate_id),
        ).fetchone()

    print(f"audit_row={row}")

    if row and row[0] and row[1] and row[2]:
        print(
            "SUCCESS: recommendation_generated audit_trail row inserted"
        )
        return 0

    print(
        "FAILURE: recommendation_generated audit_trail row missing or incomplete"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
