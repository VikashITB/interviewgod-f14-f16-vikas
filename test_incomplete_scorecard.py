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
from scorecards.submission import (
    clear_stores_for_testing,
    get_scorecard,
    submit_scorecard,
)


def audit_row(
    db_path: Path,
    action_type: str,
    candidate_id: str,
):
    query = """
    SELECT action_type, candidate_id, created_at
    FROM audit_trail
    WHERE action_type = ? AND candidate_id = ?
    ORDER BY created_at DESC
    LIMIT 1
    """

    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            query,
            (action_type, candidate_id),
        ).fetchone()


def main() -> int:
    db_path = Path(tempfile.mkdtemp()) / "incomplete_scorecard.sqlite"
    set_database_path_for_testing(db_path)
    clear_stores_for_testing()

    set_feature_enabled("f16_interviewer_scorecard", True)

    candidate_id = "cand_incomplete_day3"

    blueprint = RoleBlueprint(
        blueprint_id="bp_day3",
        blueprint_version="v1",
        must_have_skills=[
            "problem_solving",
            "system_design",
        ],
    )

    scorecard = InterviewerScorecard(
        round_id="round_day3_incomplete",
        interviewer_id="interviewer_day3",
        blueprint_id="bp_day3",
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

    print(
        "invalid_payload="
        "{'candidate_id': 'cand_incomplete_day3', "
        "'must_have_skills': ['problem_solving', 'system_design'], "
        "'competency_ratings': ['problem_solving']}"
    )

    result = submit_scorecard(
        scorecard=scorecard,
        blueprint=blueprint,
        candidate_id=candidate_id,
    )

    persisted_scorecard = get_scorecard(
        round_id="round_day3_incomplete",
        interviewer_id="interviewer_day3",
    )
    success_row = audit_row(
        db_path,
        "score_assigned",
        candidate_id,
    )
    blocked_row = audit_row(
        db_path,
        "SCORECARD_BLOCKED",
        candidate_id,
    )

    print(f"incomplete_submit.is_valid={result.is_valid}")
    print(f"incomplete_submit.missing_competencies={result.missing_competencies}")
    print(f"incomplete_submit.blocking_reason={result.blocking_reason}")
    print(f"persisted_scorecard={persisted_scorecard}")
    print(f"score_assigned_audit_row={success_row}")
    print(f"scorecard_blocked_audit_row={blocked_row}")

    incomplete_blocked = (
        not result.is_valid
        and result.missing_competencies == ["system_design"]
        and persisted_scorecard is None
        and success_row is None
        and blocked_row
        and blocked_row[0]
        and blocked_row[1]
        and blocked_row[2]
    )

    set_feature_enabled("f16_interviewer_scorecard", False)
    clear_stores_for_testing()

    old_flow_candidate_id = "cand_feature_flag_off_day3"
    old_flow_scorecard = scorecard.model_copy(
        update={
            "round_id": "round_day3_flag_off",
            "competency_ratings": [
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
        }
    )

    old_flow_result = submit_scorecard(
        scorecard=old_flow_scorecard,
        blueprint=blueprint,
        candidate_id=old_flow_candidate_id,
    )

    old_flow_persisted = get_scorecard(
        round_id="round_day3_flag_off",
        interviewer_id="interviewer_day3",
    )

    print(f"feature_flag_off.is_valid={old_flow_result.is_valid}")
    print(f"feature_flag_off.blocking_reason={old_flow_result.blocking_reason}")
    print(f"feature_flag_off.persisted_scorecard={old_flow_persisted}")

    old_flow_stable = (
        old_flow_result.is_valid
        and old_flow_result.blocking_reason == "F16 feature flag disabled."
        and old_flow_persisted is None
    )

    if incomplete_blocked and old_flow_stable:
        print("SUCCESS: incomplete scorecard rejected and feature flag OFF flow stable")
        return 0

    print("FAILURE: incomplete rejection or feature flag OFF flow check failed")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
