import sqlite3
import tempfile
from pathlib import Path

from config.feature_flags import set_feature_enabled
from database import set_database_path_for_testing
from scorecards.schema import (
    CompetencyRating,
    EvidenceEntry,
    InterviewerScorecard,
    OverallRecommendation,
    RoleBlueprint,
    SCORE_MAP,
    ScoreLabel,
)
from scorecards.submission import submit_scorecard


def main() -> int:
    db_path = Path(tempfile.mkdtemp()) / "audit_stub.sqlite"
    set_database_path_for_testing(db_path)
    set_feature_enabled("f16_interviewer_scorecard", True)

    candidate_id = "cand_day1_test"

    blueprint = RoleBlueprint(
        blueprint_id="bp_day1",
        blueprint_version="v1",
        must_have_skills=["problem_solving"],
    )

    scorecard = InterviewerScorecard(
        round_id="round_day1",
        interviewer_id="interviewer_day1",
        blueprint_id="bp_day1",
        blueprint_version="v1",
        competency_ratings=[
            CompetencyRating(
                competency="problem_solving",
                label=ScoreLabel.STRONG_YES,
                normalized_score=SCORE_MAP[ScoreLabel.STRONG_YES],
                evidence=[
                    EvidenceEntry(
                        competency="problem_solving",
                        evidence_text=(
                            "Candidate gave a clear and complete answer."
                        ),
                    )
                ],
            )
        ],
        overall_recommendation=OverallRecommendation.STRONG_YES,
    )

    result = submit_scorecard(
        scorecard=scorecard,
        blueprint=blueprint,
        candidate_id=candidate_id,
    )

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
            ("score_assigned", candidate_id),
        ).fetchone()

    print(f"submit_scorecard.is_valid={result.is_valid}")
    print(f"audit_row={row}")

    if result.is_valid and row and row[0] and row[1] and row[2]:
        print("SUCCESS: score_assigned audit_trail row inserted")
        return 0

    print("FAILURE: score_assigned audit_trail row missing or incomplete")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
