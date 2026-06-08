"""
Deterministic failure-case validation for synthetic pipeline.

Tests negative paths and validation boundaries while preserving replay-safe semantics.
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from config.feature_flags import set_feature_enabled
from database import set_database_path_for_testing
from scorecards.schema import (
    CompetencyRating,
    EvidenceEntry,
    InterviewerScorecard,
    OverallRecommendation,
    ScoreLabel,
    SCORE_MAP,
)
from scorecards.submission import submit_scorecard, clear_stores_for_testing
from scripts.synthetic_blueprint import generate_backend_engine_blueprint
from utils.audit_logger import (
    ActionType,
    clear_store_for_testing,
    log_audit_event,
    query_by_candidate_from_db,
)
from datetime import datetime, timezone


TITLE = "FAILURE CASE VALIDATION"


def print_header() -> None:
    print("\n" + "=" * 50)
    print(TITLE)
    print("=" * 50)


def print_test(message: str, passed: bool) -> None:
    status = "✓" if passed else "✗"
    print(f"{status} {message}")


def test_missing_required_competency() -> bool:
    """Test that missing required competency is blocked."""
    set_feature_enabled("f16_interviewer_scorecard", True)

    blueprint = generate_backend_engine_blueprint()

    incomplete_scorecard = InterviewerScorecard(
        round_id="round_fail_001",
        interviewer_id="interviewer_fail_001",
        blueprint_id=blueprint.blueprint_id,
        blueprint_version=blueprint.blueprint_version,
        candidate_id="cand_fail_missing_comp",
        competency_ratings=[
            CompetencyRating(
                competency="python",
                label=ScoreLabel.LEAN_YES,
                normalized_score=SCORE_MAP[ScoreLabel.LEAN_YES],
                evidence=[
                    EvidenceEntry(
                        competency="python",
                        evidence_text="Candidate demonstrated strong Python fundamentals throughout the interview session.",
                        interview_ts=datetime.now(timezone.utc),
                    )
                ],
            ),
        ],
        overall_recommendation=OverallRecommendation.YES,
    )

    result = submit_scorecard(
        scorecard=incomplete_scorecard,
        blueprint=blueprint,
        candidate_id="cand_fail_missing_comp",
    )

    passed = not result.is_valid and result.blocking_reason
    return passed


def test_missing_evidence() -> bool:
    """Test that missing evidence is blocked."""
    set_feature_enabled("f16_interviewer_scorecard", True)

    blueprint = generate_backend_engine_blueprint()

    no_evidence_scorecard = InterviewerScorecard(
        round_id="round_fail_002",
        interviewer_id="interviewer_fail_002",
        blueprint_id=blueprint.blueprint_id,
        blueprint_version=blueprint.blueprint_version,
        candidate_id="cand_fail_no_evidence",
        competency_ratings=[
            CompetencyRating(
                competency="python",
                label=ScoreLabel.LEAN_YES,
                normalized_score=SCORE_MAP[ScoreLabel.LEAN_YES],
                evidence=[],
            ),
        ],
        overall_recommendation=OverallRecommendation.YES,
    )

    result = submit_scorecard(
        scorecard=no_evidence_scorecard,
        blueprint=blueprint,
        candidate_id="cand_fail_no_evidence",
    )

    passed = not result.is_valid and result.blocking_reason
    return passed


def test_duplicate_competency_rating() -> bool:
    """Test that duplicate competency ratings are rejected."""
    set_feature_enabled("f16_interviewer_scorecard", True)

    blueprint = generate_backend_engine_blueprint()

    duplicate_scorecard = InterviewerScorecard(
        round_id="round_fail_003",
        interviewer_id="interviewer_fail_003",
        blueprint_id=blueprint.blueprint_id,
        blueprint_version=blueprint.blueprint_version,
        candidate_id="cand_fail_duplicate",
        competency_ratings=[
            CompetencyRating(
                competency="python",
                label=ScoreLabel.LEAN_YES,
                normalized_score=SCORE_MAP[ScoreLabel.LEAN_YES],
                evidence=[
                    EvidenceEntry(
                        competency="python",
                        evidence_text="First assessment shows candidate mastered Python fundamentals and patterns effectively.",
                        interview_ts=datetime.now(timezone.utc),
                    )
                ],
            ),
            CompetencyRating(
                competency="python",
                label=ScoreLabel.STRONG_YES,
                normalized_score=SCORE_MAP[ScoreLabel.STRONG_YES],
                evidence=[
                    EvidenceEntry(
                        competency="python",
                        evidence_text="Second assessment shows candidate excelled at advanced Python design patterns comprehensively.",
                        interview_ts=datetime.now(timezone.utc),
                    )
                ],
            ),
        ],
        overall_recommendation=OverallRecommendation.YES,
    )

    result = submit_scorecard(
        scorecard=duplicate_scorecard,
        blueprint=blueprint,
        candidate_id="cand_fail_duplicate",
    )

    passed = not result.is_valid and result.blocking_reason
    return passed


def test_feature_flag_off() -> bool:
    """Test that feature flag OFF preserves old behavior."""
    set_feature_enabled("f16_interviewer_scorecard", False)

    blueprint = generate_backend_engine_blueprint()

    valid_scorecard = InterviewerScorecard(
        round_id="round_fail_flag",
        interviewer_id="interviewer_fail_flag",
        blueprint_id=blueprint.blueprint_id,
        blueprint_version=blueprint.blueprint_version,
        candidate_id="cand_fail_flag_off",
        competency_ratings=[
            CompetencyRating(
                competency="python",
                label=ScoreLabel.LEAN_YES,
                normalized_score=SCORE_MAP[ScoreLabel.LEAN_YES],
                evidence=[
                    EvidenceEntry(
                        competency="python",
                        evidence_text="Candidate demonstrated Python fundamentals and implementation patterns throughout assessment.",
                        interview_ts=datetime.now(timezone.utc),
                    )
                ],
            ),
        ],
        overall_recommendation=OverallRecommendation.YES,
    )

    result = submit_scorecard(
        scorecard=valid_scorecard,
        blueprint=blueprint,
        candidate_id="cand_fail_flag_off",
    )

    passed = result.is_valid and "feature flag disabled" in str(result.blocking_reason).lower()
    return passed


def test_invalid_normalized_score() -> bool:
    """Test that invalid normalized scores are rejected."""
    set_feature_enabled("f16_interviewer_scorecard", True)

    blueprint = generate_backend_engine_blueprint()

    wrong_score_scorecard = InterviewerScorecard(
        round_id="round_fail_score",
        interviewer_id="interviewer_fail_score",
        blueprint_id=blueprint.blueprint_id,
        blueprint_version=blueprint.blueprint_version,
        candidate_id="cand_fail_wrong_score",
        competency_ratings=[
            CompetencyRating(
                competency="python",
                label=ScoreLabel.LEAN_YES,
                normalized_score=999,
                evidence=[
                    EvidenceEntry(
                        competency="python",
                        evidence_text="Candidate demonstrated strong Python fundamentals and comprehensive design skills throughout.",
                        interview_ts=datetime.now(timezone.utc),
                    )
                ],
            ),
        ],
        overall_recommendation=OverallRecommendation.YES,
    )

    result = submit_scorecard(
        scorecard=wrong_score_scorecard,
        blueprint=blueprint,
        candidate_id="cand_fail_wrong_score",
    )

    passed = not result.is_valid and result.blocking_reason
    return passed


def test_unknown_competency() -> bool:
    """Test that unknown competencies are rejected."""
    set_feature_enabled("f16_interviewer_scorecard", True)

    blueprint = generate_backend_engine_blueprint()

    unknown_comp_scorecard = InterviewerScorecard(
        round_id="round_fail_unknown",
        interviewer_id="interviewer_fail_unknown",
        blueprint_id=blueprint.blueprint_id,
        blueprint_version=blueprint.blueprint_version,
        candidate_id="cand_fail_unknown_comp",
        competency_ratings=[
            CompetencyRating(
                competency="unknown_skill",
                label=ScoreLabel.LEAN_YES,
                normalized_score=SCORE_MAP[ScoreLabel.LEAN_YES],
                evidence=[
                    EvidenceEntry(
                        competency="unknown_skill",
                        evidence_text="Candidate demonstrated competency in an unknown skill area beyond blueprint scope.",
                        interview_ts=datetime.now(timezone.utc),
                    )
                ],
            ),
        ],
        overall_recommendation=OverallRecommendation.YES,
    )

    result = submit_scorecard(
        scorecard=unknown_comp_scorecard,
        blueprint=blueprint,
        candidate_id="cand_fail_unknown_comp",
    )

    passed = not result.is_valid and result.blocking_reason
    return passed


def test_blocked_submissions_emit_audit() -> bool:
    """Test that blocked submissions emit SCORECARD_BLOCKED audit event."""
    set_feature_enabled("f16_interviewer_scorecard", True)

    candidate_id = "cand_fail_audit_blocked"
    blueprint = generate_backend_engine_blueprint()

    incomplete_scorecard = InterviewerScorecard(
        round_id="round_fail_audit",
        interviewer_id="interviewer_fail_audit",
        blueprint_id=blueprint.blueprint_id,
        blueprint_version=blueprint.blueprint_version,
        candidate_id=candidate_id,
        competency_ratings=[],
        overall_recommendation=OverallRecommendation.YES,
    )

    submit_scorecard(
        scorecard=incomplete_scorecard,
        blueprint=blueprint,
        candidate_id=candidate_id,
    )

    events = query_by_candidate_from_db(candidate_id)
    has_blocked = any(e.action_type == ActionType.SCORECARD_BLOCKED for e in events)
    has_submitted = any(e.action_type == ActionType.SCORECARD_SUBMITTED for e in events)

    passed = has_blocked and not has_submitted
    return passed


def main() -> int:
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
    tmp.close()
    set_database_path_for_testing(tmp.name)
    clear_store_for_testing()
    clear_stores_for_testing()

    print_header()

    tests = [
        ("Missing required competency blocked", test_missing_required_competency()),
        ("Missing evidence blocked", test_missing_evidence()),
        ("Duplicate competency blocked", test_duplicate_competency_rating()),
        ("Feature flag OFF preserves behavior", test_feature_flag_off()),
        ("Invalid normalized score rejected", test_invalid_normalized_score()),
        ("Unknown competency rejected", test_unknown_competency()),
        ("Blocked submissions emit audit event", test_blocked_submissions_emit_audit()),
    ]

    print("\n" + "-" * 50)
    for test_name, passed in tests:
        print_test(test_name, passed)

    print("\n" + "-" * 50)
    all_passed = all(passed for _, passed in tests)
    if all_passed:
        print("EXPECTED FAILURES VERIFIED: All negative paths working correctly")
    else:
        print("FAILURE: Some negative paths not working as expected")

    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
