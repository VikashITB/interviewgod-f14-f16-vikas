"""
tests/test_f16_scorecard.py
===========================
Scorecard — EOD test suite.

Covers:
    1. Incomplete scorecard blocked
    2. Complete scorecard succeeds
    3. Calibration check on mock dataset
    4. Audit event emitted on successful submission
"""

import sys
import os
import tempfile
import importlib.util

sys.path.insert(

    0,

    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )

)

from datetime import (

    datetime,
    timezone,

)

from scorecards.schema import (

    BlueprintCompetency,
    CompetencyRating,
    EvidenceEntry,
    InterviewerScorecard,
    materialize_scorecard_schema,
    OverallRecommendation,
    RoleBlueprint,
    ScoreLabel,
    SCORE_MAP,
    CalibrationSnapshot,

)

from scorecards.validator import (
    validate_scorecard
)

from scorecards import calibration as cal

from scorecards.submission import (

    submit_scorecard,
    get_scorecard,
    get_scorecards_by_interviewer,
    clear_stores_for_testing,

)

from config.feature_flags import (
    is_feature_enabled,
    set_feature_enabled,
)

from database import set_database_path_for_testing

from utils.audit_logger import (

    query_by_candidate,
    query_all,
    clear_store_for_testing
        as clear_audit_store,
    ActionType,

)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_blueprint(
    must_have: list[str] = None
) -> RoleBlueprint:

    return RoleBlueprint(

        blueprint_id=
            "bp_backend",

        blueprint_version=
            "v1",

        must_have_skills=(
            must_have
            or [
                "problem_solving",
                "system_design",
                "communication",
            ]
        ),

    )

# ---------------------------------------------------------------------------

def make_contract_blueprint() -> RoleBlueprint:

    return RoleBlueprint(

        blueprint_id="bp_backend",

        blueprint_version="v1",

        competencies=[

            BlueprintCompetency(
                competency_id="problem_solving",
                required=True,
                weight=0.35,
                evidence_required=True,
                knockout_candidate=True,
            ),

            BlueprintCompetency(
                competency_id="system_design",
                required=True,
                weight=0.40,
                evidence_required=True,
                knockout_candidate=True,
            ),

            BlueprintCompetency(
                competency_id="communication",
                required=True,
                weight=0.25,
                evidence_required=True,
                knockout_candidate=False,
            ),

        ],

    )

# ---------------------------------------------------------------------------

def make_evidence(
    competency: str,
    text: str = None,
) -> EvidenceEntry:

    return EvidenceEntry(

        competency=competency,

        evidence_text=(
            text
            or
            f"Candidate demonstrated "
            f"strong {competency} "
            f"through a structured approach."
        ),

        interview_ts=datetime.now(
            timezone.utc
        ),

    )

# ---------------------------------------------------------------------------

def make_rating(

    competency: str,

    label: ScoreLabel =
        ScoreLabel.LEAN_YES,

    evidence_text: str = None,

) -> CompetencyRating:

    return CompetencyRating(

        competency=competency,

        label=label,

        normalized_score=
            SCORE_MAP[label],

        evidence=[

            make_evidence(
                competency,
                evidence_text
            )

        ],

    )

# ---------------------------------------------------------------------------

def make_complete_scorecard(

    round_id: str =
        "round_001",

    interviewer_id: str =
        "interviewer_vikas",

    competencies: list[str] = None,

    label: ScoreLabel =
        ScoreLabel.LEAN_YES,

) -> InterviewerScorecard:

    comps = (

        competencies
        or [
            "problem_solving",
            "system_design",
            "communication",
        ]

    )

    return InterviewerScorecard(

        round_id=round_id,

        interviewer_id=interviewer_id,

        blueprint_id="bp_backend",

        blueprint_version="v1",

        competency_ratings=[

            make_rating(
                competency=c,
                label=label
            )

            for c in comps

        ],

        overall_recommendation=
            OverallRecommendation.YES,

    )

# ---------------------------------------------------------------------------

def setup():

    temp_db = tempfile.NamedTemporaryFile(
        suffix=".sqlite3",
        delete=False,
    )

    temp_db.close()

    set_database_path_for_testing(
        temp_db.name
    )

    clear_stores_for_testing()

    clear_audit_store()

    set_feature_enabled(
        "f16_interviewer_scorecard",
        True,
    )

# ---------------------------------------------------------------------------
# Test 1 — Incomplete scorecard blocked
# ---------------------------------------------------------------------------

def test_unknown_feature_flag_disabled():

    assert not is_feature_enabled(
        "unknown_future_flag"
    )

    set_feature_enabled(
        "unknown_future_flag",
        True,
    )

    assert not is_feature_enabled(
        "unknown_future_flag"
    )

    print(
        "  [ok] "
        "test_unknown_feature_flag_disabled"
    )

# ---------------------------------------------------------------------------

def test_incomplete_scorecard_blocked():

    setup()

    blueprint = make_blueprint()

    incomplete = InterviewerScorecard(

        round_id="round_001",

        interviewer_id=
            "interviewer_vikas",

        blueprint_id=
            "bp_backend",

        blueprint_version=
            "v1",

        competency_ratings=[

            make_rating(
                "problem_solving"
            ),

            make_rating(
                "system_design"
            ),

        ],

        overall_recommendation=
            OverallRecommendation.NEUTRAL,

    )

    result = submit_scorecard(

        scorecard=incomplete,

        blueprint=blueprint,

        candidate_id="cand_001",

        hiring_group_id="hg_backend",

    )

    assert not result.is_valid

    assert (
        "communication"
        in result.missing_competencies
    )

    persisted = get_scorecard(

        "round_001",

        "interviewer_vikas",

    )

    assert persisted is None

    audit_events = query_by_candidate(
        "cand_001"
    )

    blocked_events = [

        event

        for event
        in audit_events

        if event.action_type
        ==
        ActionType.SCORECARD_BLOCKED

    ]

    assert len(blocked_events) == 1

    submitted_events = [

        event

        for event
        in audit_events

        if event.action_type
        ==
        ActionType.SCORECARD_SUBMITTED

    ]

    assert len(submitted_events) == 0

    print(
        "  [ok] "
        "test_incomplete_scorecard_blocked"
    )

# ---------------------------------------------------------------------------
# Test 2 — Missing evidence blocked
# ---------------------------------------------------------------------------

def test_missing_evidence_blocked():

    setup()

    blueprint = make_blueprint(
        must_have=["problem_solving"]
    )

    bad_rating = CompetencyRating(

        competency=
            "problem_solving",

        label=
            ScoreLabel.LEAN_YES,

        normalized_score=
            SCORE_MAP[
                ScoreLabel.LEAN_YES
            ],

        evidence=[],

    )

    scorecard = InterviewerScorecard(

        round_id="round_002",

        interviewer_id=
            "interviewer_test",

        blueprint_id=
            "bp_backend",

        blueprint_version=
            "v1",

        competency_ratings=[
            bad_rating
        ],

        overall_recommendation=
            OverallRecommendation.YES,

    )

    result = validate_scorecard(
        scorecard,
        blueprint
    )

    assert not result.is_valid

    assert (
        "problem_solving"
        in result.missing_evidence
    )

    print(
        "  [ok] "
        "test_missing_evidence_blocked"
    )

# ---------------------------------------------------------------------------

def test_missing_evidence_submission_blocked():

    setup()

    blueprint = make_contract_blueprint()

    bad_rating = CompetencyRating(

        competency=
            "problem_solving",

        label=
            ScoreLabel.LEAN_YES,

        normalized_score=
            SCORE_MAP[
                ScoreLabel.LEAN_YES
            ],

        evidence=[],

    )

    scorecard = InterviewerScorecard(

        round_id="round_002_blocked",

        interviewer_id=
            "interviewer_test",

        blueprint_id=
            "bp_backend",

        blueprint_version=
            "v1",

        competency_ratings=[
            bad_rating
        ],

        overall_recommendation=
            OverallRecommendation.YES,

    )

    result = submit_scorecard(

        scorecard=scorecard,

        blueprint=blueprint,

        candidate_id="cand_missing_evidence",

        hiring_group_id="hg_backend",

    )

    assert not result.is_valid

    assert (
        "problem_solving"
        in result.missing_evidence
    )

    persisted = get_scorecard(

        "round_002_blocked",

        "interviewer_test",

    )

    assert persisted is None

    audit_events = query_by_candidate(
        "cand_missing_evidence"
    )

    assert all(
        event.action_type
        !=
        ActionType.SCORECARD_SUBMITTED
        for event
        in audit_events
    )

    blocked_events = [

        event

        for event
        in audit_events

        if event.action_type
        ==
        ActionType.SCORECARD_BLOCKED

    ]

    assert len(blocked_events) == 1

    print(
        "  [ok] "
        "test_missing_evidence_submission_blocked"
    )

# ---------------------------------------------------------------------------

def test_duplicate_competency_submission_blocked():

    setup()

    blueprint = make_contract_blueprint()

    repeated_rating = make_rating(
        "problem_solving"
    )

    scorecard = InterviewerScorecard(

        round_id="round_002_duplicate",

        interviewer_id=
            "interviewer_test",

        blueprint_id=
            "bp_backend",

        blueprint_version=
            "v1",

        competency_ratings=[
            repeated_rating,
            repeated_rating,
        ],

        overall_recommendation=
            OverallRecommendation.YES,

    )

    result = submit_scorecard(

        scorecard=scorecard,

        blueprint=blueprint,

        candidate_id="cand_duplicate",

        hiring_group_id="hg_backend",

    )

    assert result.is_valid is False

    assert any(
        "Duplicate rating for competency"
        in error
        for error
        in result.validation_errors
    )

    assert get_scorecard(
        "round_002_duplicate",
        "interviewer_test",
    ) is None

    assert all(
        event.action_type
        !=
        ActionType.SCORECARD_SUBMITTED
        for event
        in query_by_candidate("cand_duplicate")
    )

    print(
        "  [ok] "
        "test_duplicate_competency_submission_blocked"
    )

# ---------------------------------------------------------------------------

def test_invalid_numeric_rating_value_fails():

    setup()

    try:
        CompetencyRating(
            competency="problem_solving",
            rating=6,
            evidence=[
                make_evidence("problem_solving")
            ],
        )

        assert False, "Expected invalid numeric rating to raise"

    except ValueError as exc:
        assert "rating must be an integer between 1 and 5" in str(exc)

    print(
        "  [ok] "
        "test_invalid_numeric_rating_value_fails"
    )

# ---------------------------------------------------------------------------
# Test 3 — Wrong normalized score blocked
# ---------------------------------------------------------------------------

def test_wrong_normalized_score_blocked():

    setup()

    blueprint = make_blueprint(
        must_have=["problem_solving"]
    )

    bad_rating = CompetencyRating(

        competency=
            "problem_solving",

        label=
            ScoreLabel.STRONG_YES,

        normalized_score=
            10,

        evidence=[
            make_evidence(
                "problem_solving"
            )
        ],

    )

    scorecard = InterviewerScorecard(

        round_id="round_003",

        interviewer_id=
            "interviewer_test",

        blueprint_id=
            "bp_backend",

        blueprint_version=
            "v1",

        competency_ratings=[
            bad_rating
        ],

        overall_recommendation=
            OverallRecommendation.YES,

    )

    result = validate_scorecard(
        scorecard,
        blueprint
    )

    assert not result.is_valid

    assert (
        len(
            result.validation_errors
        ) > 0
    )

    print(
        "  [ok] "
        "test_wrong_normalized_score_blocked"
    )

# ---------------------------------------------------------------------------
# Test 4 — Missing recommendation blocked
# ---------------------------------------------------------------------------

def test_missing_recommendation_blocked():

    setup()

    blueprint = make_blueprint(
        must_have=["problem_solving"]
    )

    scorecard = InterviewerScorecard(

        round_id="round_004",

        interviewer_id=
            "interviewer_test",

        blueprint_id=
            "bp_backend",

        blueprint_version=
            "v1",

        competency_ratings=[

            make_rating(
                "problem_solving"
            )

        ],

        overall_recommendation=None,

    )

    result = validate_scorecard(
        scorecard,
        blueprint
    )

    assert not result.is_valid

    assert any(

        "overall_recommendation"
        in error

        for error
        in result.validation_errors

    )

    print(
        "  [ok] "
        "test_missing_recommendation_blocked"
    )

# ---------------------------------------------------------------------------
# Test 5 — Complete scorecard succeeds
# ---------------------------------------------------------------------------

def test_complete_scorecard_succeeds():

    setup()

    blueprint = make_blueprint()

    scorecard = make_complete_scorecard()
    scorecard.notes = "Recruiter notes preserved"

    result = submit_scorecard(

        scorecard=scorecard,

        blueprint=blueprint,

        candidate_id="cand_002",

        hiring_group_id="hg_backend",

    )

    assert result.is_valid

    persisted = get_scorecard(

        "round_001",

        "interviewer_vikas",

    )

    assert persisted is not None

    assert (
        persisted.status.value
        ==
        "SUBMITTED"
    )

    assert (
        persisted.submitted_at
        is not None
    )

    assert persisted.candidate_id == "cand_002"
    assert persisted.notes == "Recruiter notes preserved"
    assert persisted.blueprint_version == "v1"
    assert len(persisted.competency_ratings) == 3
    assert persisted.competency_ratings[0].evidence

    audit_events = query_by_candidate(
        "cand_002"
    )

    submitted_events = [

        event

        for event
        in audit_events

        if event.action_type
        ==
        ActionType.SCORECARD_SUBMITTED

    ]

    assert len(submitted_events) == 1

    print(
        "  [ok] "
        "test_complete_scorecard_succeeds"
    )

# ---------------------------------------------------------------------------
# Test 6 — Score map validation
# ---------------------------------------------------------------------------

def test_numeric_rating_payload_maps_to_label():

    setup()

    blueprint = RoleBlueprint(

        blueprint_id="bp_backend",

        blueprint_version="v1",

        competencies=[
            BlueprintCompetency(
                competency_id="problem_solving",
                required=True,
                weight=0.40,
                evidence_required=True,
                knockout_candidate=False,
            ),
        ],

    )

    scorecard = InterviewerScorecard(

        round_id="round_005",

        interviewer_id="interviewer_numeric_rating",

        blueprint_id="bp_backend",

        blueprint_version="v1",

        competency_ratings=[

            CompetencyRating(
                competency="problem_solving",
                rating=4,
                evidence=[
                    make_evidence("problem_solving")
                ],
            )

        ],

        overall_recommendation=
            OverallRecommendation.YES,

    )

    result = validate_scorecard(
        scorecard,
        blueprint,
    )

    assert result.is_valid

    rating = scorecard.competency_ratings[0]

    assert rating.label == ScoreLabel.LEAN_YES
    assert rating.normalized_score == 75

    print(
        "  [ok] "
        "test_numeric_rating_payload_maps_to_label"
    )


# ---------------------------------------------------------------------------

def test_all_score_labels_map_correctly():

    setup()

    expected = {

        ScoreLabel.STRONG_NO: 10,
        ScoreLabel.LEAN_NO: 30,
        ScoreLabel.NEUTRAL: 55,
        ScoreLabel.LEAN_YES: 75,
        ScoreLabel.STRONG_YES: 95,

    }

    for label, score in expected.items():

        assert (
            SCORE_MAP[label]
            ==
            score
        )

    print(
        "  [ok] "
        "test_all_score_labels_map_correctly"
    )


# ---------------------------------------------------------------------------

def test_feature_flag_off_preserves_legacy_flow():

    setup()

    set_feature_enabled(
        "f16_interviewer_scorecard",
        False,
    )

    blueprint = make_blueprint()

    scorecard = make_complete_scorecard(
        round_id="round_flag_off"
    )

    result = submit_scorecard(

        scorecard=scorecard,

        blueprint=blueprint,

        candidate_id="cand_flag_off",

        hiring_group_id="hg_backend",

    )

    assert result.is_valid
    assert (
        result.blocking_reason
        ==
        "F16 feature flag disabled."
    )

    persisted = get_scorecard(
        "round_flag_off",
        "interviewer_vikas",
    )

    assert persisted is None

    assert (
        query_by_candidate("cand_flag_off")
        == []
    )

    print(
        "  [ok] "
        "test_feature_flag_off_preserves_legacy_flow"
    )


# ---------------------------------------------------------------------------

def test_schema_rejects_invented_competency():

    setup()

    expected = {

        ScoreLabel.STRONG_NO: 10,
        ScoreLabel.LEAN_NO: 30,
        ScoreLabel.NEUTRAL: 55,
        ScoreLabel.LEAN_YES: 75,
        ScoreLabel.STRONG_YES: 95,

    }

    for label, score in expected.items():

        assert (
            SCORE_MAP[label]
            ==
            score
        )

    print(
        "  [ok] "
        "test_all_score_labels_map_correctly"
    )

# ---------------------------------------------------------------------------
# Test 7 — Calibration
# ---------------------------------------------------------------------------

def test_calibration_check_runs_on_10_scorecards():

    setup()

    alice_scorecards = [

        make_complete_scorecard(

            round_id=
                f"round_{i}",

            interviewer_id=
                "alice",

            competencies=[
                "problem_solving"
            ],

            label=
                ScoreLabel.LEAN_YES,

        )

        for i in range(10)

    ]

    org_scorecards = [

        make_complete_scorecard(

            round_id=
                f"org_round_{i}",

            interviewer_id=
                f"other_{i}",

            competencies=[
                "problem_solving"
            ],

            label=
                ScoreLabel.LEAN_NO,

        )

        for i in range(10)

    ]

    snapshot = (
        cal.compute_calibration_snapshot(

            interviewer_scorecards=
                alice_scorecards,

            all_scorecards=
                alice_scorecards
                + org_scorecards,

            interviewer_id=
                "alice",

            snapshot_week=
                "2025-W22",

        )
    )

    assert snapshot is not None

    assert (
        snapshot.drift_pct
        > 30.0
    )

    assert snapshot.flagged

    assert (
        snapshot.drift_direction
        ==
        "lenient"
    )

    print(
        "  [ok] "
        "test_calibration_check_runs_on_10_scorecards"
    )

# ---------------------------------------------------------------------------
# Test 8 — Calibration threshold
# ---------------------------------------------------------------------------

def test_calibration_requires_10_scorecards():

    setup()

    alice_scorecards = [

        make_complete_scorecard(

            round_id=
                f"round_{i}",

            interviewer_id=
                "alice",

        )

        for i in range(9)

    ]

    snapshot = (
        cal.compute_calibration_snapshot(

            interviewer_scorecards=
                alice_scorecards,

            all_scorecards=
                alice_scorecards,

            interviewer_id=
                "alice",

        )
    )

    assert snapshot is None

    print(
        "  [ok] "
        "test_calibration_requires_10_scorecards"
    )

# ---------------------------------------------------------------------------
# Test 9 — Outlier detection
# ---------------------------------------------------------------------------

def test_outlier_detection():

    setup()

    snap1 = CalibrationSnapshot(

        interviewer_id="alice",

        scorecard_count=10,

        interviewer_avg=80.0,

        org_avg=55.0,

        drift_pct=45.5,

        drift_direction="lenient",

        flagged=True,

        snapshot_week="2025-W21",

    )

    snap2 = CalibrationSnapshot(

        interviewer_id="alice",

        scorecard_count=15,

        interviewer_avg=82.0,

        org_avg=55.0,

        drift_pct=49.1,

        drift_direction="lenient",

        flagged=True,

        snapshot_week="2025-W22",

    )

    assert cal.detect_outlier(
        [snap1, snap2]
    )

    print(
        "  [ok] "
        "test_outlier_detection"
    )

# ---------------------------------------------------------------------------
# Test 10 — Audit integration
# ---------------------------------------------------------------------------

def test_submission_creates_audit_event():

    setup()

    blueprint = make_blueprint()

    scorecard = make_complete_scorecard(

        round_id=
            "round_audit_test",

        interviewer_id=
            "interviewer_audit",

    )

    before = len(query_all())

    result = submit_scorecard(

        scorecard=scorecard,

        blueprint=blueprint,

        candidate_id=
            "cand_audit",

        hiring_group_id=
            "hg_backend",

    )

    assert result.is_valid

    after = len(query_all())

    assert after == before + 1

    latest = query_all()[-1]

    assert (
        latest.action_type
        ==
        ActionType.SCORECARD_SUBMITTED
    )

    assert (
        latest.candidate_id
        ==
        "cand_audit"
    )

    print(
        "  [ok] "
        "test_submission_creates_audit_event"
    )

# ---------------------------------------------------------------------------
# Test 11 - Blueprint materializes deterministic schema
# ---------------------------------------------------------------------------

def test_blueprint_materializes_schema_contract():

    setup()

    blueprint = make_contract_blueprint()

    schema = materialize_scorecard_schema(
        blueprint
    )

    assert schema.blueprint_id == "bp_backend"

    assert schema.blueprint_version == "v1"

    assert schema.schema_version == "v1"

    assert [
        competency.competency_id
        for competency
        in schema.competencies
    ] == [
        "problem_solving",
        "system_design",
        "communication",
    ]

    assert (
        schema.score_scale["STRONG_YES"]
        == 95
    )

    assert (
        schema
        .validation_contract
        .evidence_required_per_competency
    )

    print(
        "  [ok] "
        "test_blueprint_materializes_schema_contract"
    )

# ---------------------------------------------------------------------------
# Test 12 - Schema rejects invented competencies
# ---------------------------------------------------------------------------

def test_schema_rejects_invented_competency():

    setup()

    blueprint = make_contract_blueprint()

    scorecard = make_complete_scorecard(
        competencies=[
            "problem_solving",
            "system_design",
            "communication",
            "runtime_invented_skill",
        ]
    )

    result = validate_scorecard(
        scorecard,
        materialize_scorecard_schema(blueprint),
    )

    assert not result.is_valid

    assert any(
        "runtime_invented_skill" in error
        for error
        in result.validation_errors
    )

    print(
        "  [ok] "
        "test_schema_rejects_invented_competency"
    )

# ---------------------------------------------------------------------------
# Test 13 - Replay metadata includes deterministic contract versions
# ---------------------------------------------------------------------------

def test_submission_replay_metadata_includes_schema_contract():

    setup()

    blueprint = make_contract_blueprint()

    scorecard = make_complete_scorecard()

    result = submit_scorecard(

        scorecard=scorecard,

        blueprint=blueprint,

        candidate_id="cand_contract",

        hiring_group_id="hg_backend",

    )

    assert result.is_valid

    latest = query_all()[-1]

    replay_metadata = (
        latest
        .evidence_snapshot["replay_metadata"]
    )

    assert (
        replay_metadata["blueprint_id"]
        == "bp_backend"
    )

    assert (
        replay_metadata["blueprint_version"]
        == "v1"
    )

    assert (
        replay_metadata["schema_version"]
        == "v1"
    )

    assert (
        replay_metadata["threshold_snapshot"]
        ["score_map"]["LEAN_YES"]
        == 75
    )

    print(
        "  [ok] "
        "test_submission_replay_metadata_includes_schema_contract"
    )


def load_scorecard_adapter():

    adapter_path = os.path.join(
        os.path.dirname(
            os.path.dirname(
                os.path.abspath(__file__)
            )
        ),
        "hr-feedback",
        "scorecard.py",
    )

    spec = importlib.util.spec_from_file_location(
        "hr_feedback_scorecard_adapter",
        adapter_path,
    )

    module = importlib.util.module_from_spec(spec)

    sys.modules[spec.name] = module

    spec.loader.exec_module(module)

    return module


def test_scorecard_adapter_maps_valid_submission_to_201():

    setup()

    set_feature_enabled(
        "f16_interviewer_scorecard",
        True,
    )

    adapter = load_scorecard_adapter()

    scorecard = make_complete_scorecard(
        round_id="round_adapter_success"
    )

    response = adapter.post_interview_scorecard(
        round_id="round_adapter_success",
        scorecard=scorecard,
        blueprint=make_contract_blueprint(),
        candidate_id="cand_adapter_success",
        hiring_group_id="hg_adapter",
    )

    assert response.status_code == 201
    assert response.body["is_valid"] is True

    persisted = get_scorecard(
        "round_adapter_success",
        "interviewer_vikas",
    )

    assert persisted is not None

    print(
        "  [ok] "
        "test_scorecard_adapter_maps_valid_submission_to_201"
    )


def test_scorecard_adapter_maps_invalid_submission_to_400():

    setup()

    set_feature_enabled(
        "f16_interviewer_scorecard",
        True,
    )

    adapter = load_scorecard_adapter()

    scorecard = make_complete_scorecard(
        round_id="round_adapter_invalid",
        competencies=[
            "problem_solving",
            "system_design",
        ],
    )

    response = adapter.post_interview_scorecard(
        round_id="round_adapter_invalid",
        scorecard=scorecard,
        blueprint=make_contract_blueprint(),
        candidate_id="cand_adapter_invalid",
        hiring_group_id="hg_adapter",
    )

    assert response.status_code == 400
    assert response.body["is_valid"] is False
    assert "communication" in response.body["missing_competencies"]

    persisted = get_scorecard(
        "round_adapter_invalid",
        "interviewer_vikas",
    )

    assert persisted is None

    print(
        "  [ok] "
        "test_scorecard_adapter_maps_invalid_submission_to_400"
    )

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all_tests():

    print("\n" + "=" * 60)

    print("SCORECARD — TEST SUITE")

    print("=" * 60)

    tests = [

        test_unknown_feature_flag_disabled,
        test_incomplete_scorecard_blocked,
        test_missing_evidence_blocked,
        test_wrong_normalized_score_blocked,
        test_missing_recommendation_blocked,
        test_complete_scorecard_succeeds,
        test_all_score_labels_map_correctly,
        test_calibration_check_runs_on_10_scorecards,
        test_calibration_requires_10_scorecards,
        test_outlier_detection,
        test_submission_creates_audit_event,
        test_blueprint_materializes_schema_contract,
        test_schema_rejects_invented_competency,
        test_submission_replay_metadata_includes_schema_contract,
        test_scorecard_adapter_maps_valid_submission_to_201,
        test_scorecard_adapter_maps_invalid_submission_to_400,

    ]

    passed = 0

    failed = 0

    for test_fn in tests:

        try:

            test_fn()

            passed += 1

        except AssertionError as exc:

            print(
                f"  [fail] "
                f"{test_fn.__name__}: "
                f"{exc}"
            )

            failed += 1

        except Exception as exc:

            import traceback

            print(
                f"  [fail] "
                f"{test_fn.__name__} "
                f"CRASHED: "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

            traceback.print_exc()

            failed += 1

    print("-" * 60)

    print(

        f"Results: "
        f"{passed} passed / "
        f"{failed} failed / "
        f"{len(tests)} total"

    )

    print("=" * 60 + "\n")

    return failed == 0

# ---------------------------------------------------------------------------

if __name__ == "__main__":

    success = run_all_tests()

    sys.exit(
        0 if success else 1
    )
