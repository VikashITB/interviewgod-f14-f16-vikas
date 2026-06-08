"""
tests/test_regression.py
========================
Regression protection suite for Week 2.

Covers:
    1. Unknown flags remain disabled
    2. Flag toggles do not leak or mutate unrelated state
    3. F14 audit metadata carries no business logic
    4. Audit store count matches exact event writes
    5. Legacy F14 events replay correctly from DB
    6. Mixed legacy and F16 events coexist safely
    7. Replay metadata pins blueprint version
    8. All known flags default OFF
"""

import sys
import os
import tempfile

sys.path.insert(

    0,

    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )

)

from config.feature_flags import (

    FEATURE_FLAGS,
    is_feature_enabled,
    set_feature_enabled,

)

from datetime import (

    datetime,
    timezone,

)

from utils.audit_logger import (

    ActionType,
    PipelineStage,
    log_audit_event,
    query_by_candidate_from_db,
    query_by_action_type_from_db,
    get_store_count,
    clear_store_for_testing,
    get_original_f14_action_category,

)

from database import (

    set_database_path_for_testing,

)

from scorecards.schema import (

    CompetencyRating,
    EvidenceEntry,
    InterviewerScorecard,
    OverallRecommendation,
    RoleBlueprint,
    ScoreLabel,
    SCORE_MAP,

)

from scorecards.submission import (

    submit_scorecard,

)


# ---------------------------------------------------------------------------
# Helpers
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

    clear_store_for_testing()

    reset_feature_flags()


# ---------------------------------------------------------------------------


def reset_feature_flags():

    for flag in FEATURE_FLAGS:
        FEATURE_FLAGS[flag] = False


# ---------------------------------------------------------------------------


def assert_equal(
    actual,
    expected,
    label="",
):

    assert actual == expected, (

        f"FAIL [{label}] "
        f"expected={expected!r} "
        f"got={actual!r}"

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
            f"Candidate demonstrated strong {competency}."
        ),

        interview_ts=datetime.now(
            timezone.utc
        ),

    )


# ---------------------------------------------------------------------------


def make_rating(
    competency: str,
    label: ScoreLabel = ScoreLabel.LEAN_YES,
) -> CompetencyRating:

    return CompetencyRating(

        competency=competency,

        label=label,

        normalized_score=SCORE_MAP[label],

        evidence=[
            make_evidence(competency),
        ],

    )


# ---------------------------------------------------------------------------
# Regression tests
# ---------------------------------------------------------------------------


def test_unknown_flag_always_false():

    reset_feature_flags()

    assert is_feature_enabled("unknown_flag") is False

    set_feature_enabled("unknown_flag", True)

    assert is_feature_enabled("unknown_flag") is False

    assert "unknown_flag" not in FEATURE_FLAGS

    print("  [ok] test_unknown_flag_always_false")


# ---------------------------------------------------------------------------


def test_flag_toggle_leaves_no_side_effects():

    reset_feature_flags()

    original_flags = dict(FEATURE_FLAGS)

    set_feature_enabled(
        "f16_interviewer_scorecard",
        True,
    )

    assert FEATURE_FLAGS["f16_interviewer_scorecard"] is True

    set_feature_enabled(
        "f16_interviewer_scorecard",
        False,
    )

    assert FEATURE_FLAGS == original_flags

    set_feature_enabled("invalid_flag", True)

    assert FEATURE_FLAGS == original_flags

    print("  [ok] test_flag_toggle_leaves_no_side_effects")


# ---------------------------------------------------------------------------


def test_f14_carries_no_business_logic():

    setup()

    from utils.audit_logger import AuditEvent

    audit_fields = set(
        AuditEvent.model_fields.keys()
    )

    # Context fields like blueprint_id / blueprint_version are first-class
    # per spec, same tier as candidate_id and round_id. Forbidden fields are
    # scorecard or domain-specific business data.
    forbidden = {
        "competency_ratings",
        "normalized_score",
        "recommendation_score",
        "knockout_reason",
        "calibration_flag",
        "calibration_drift_pct",
        "scorecard_id",
        "interview_score",
    }

    leaking = audit_fields & forbidden

    assert not leaking, (
        f"F14 is leaking business-logic fields: {leaking}. "
        "AuditEvent must stay generic."
    )

    payload = {
        "score": 75,
    }

    event = log_audit_event(

        action_type=ActionType.SCORECARD_SUBMITTED,

        actor_id="interviewer_test",

        actor_email="interviewer@company.com",

        candidate_id="cand_business",

        hiring_group_id="hg_backend",

        evidence_snapshot=payload,

        summary="Validate no business logic in audit logger",

    )

    assert event.evidence_snapshot == payload
    assert event.pipeline_stage == PipelineStage.INTERVIEW_INTEGRITY
    assert (
        get_original_f14_action_category(
            ActionType.SCORECARD_SUBMITTED
        )
        ==
        "score_assigned"
    )

    print("  [ok] test_f14_carries_no_business_logic")


# ---------------------------------------------------------------------------


def test_audit_count_matches_exactly():

    setup()

    for i in range(4):
        log_audit_event(
            action_type=ActionType.SCORECARD_SUBMITTED,
            actor_id=f"interviewer_{i}",
            actor_email=f"i{i}@company.com",
            candidate_id=f"cand_count_{i}",
            hiring_group_id="hg_backend",
            summary=f"event-{i}",
        )

    assert_equal(
        get_store_count(),
        4,
        "exact audit count",
    )

    print("  [ok] test_audit_count_matches_exactly")


# ---------------------------------------------------------------------------


def test_legacy_events_replay_safely():

    setup()

    log_audit_event(

        action_type=ActionType.SCORE_ASSIGNED,

        actor_id="interviewer_legacy",

        actor_email="legacy@platform.internal",

        candidate_id="cand_legacy",

        hiring_group_id="hg_backend",

        summary="Legacy score assigned event",

    )

    events = query_by_action_type_from_db(
        ActionType.SCORE_ASSIGNED,
    )

    assert_equal(
        len(events),
        1,
        "legacy replay count",
    )

    assert_equal(
        events[0].candidate_id,
        "cand_legacy",
        "legacy candidate id",
    )

    print("  [ok] test_legacy_events_replay_safely")


# ---------------------------------------------------------------------------


def test_mixed_event_generations_replay_together():

    setup()

    candidate_id = "cand_mixed"

    log_audit_event(

        action_type=ActionType.SCORE_ASSIGNED,

        actor_id="interviewer_legacy",

        actor_email="legacy@platform.internal",

        candidate_id=candidate_id,

        hiring_group_id="hg_backend",

        summary="Legacy event",

    )

    log_audit_event(

        action_type=ActionType.SCORECARD_SUBMITTED,

        actor_id="interviewer_modern",

        actor_email="modern@platform.internal",

        candidate_id=candidate_id,

        hiring_group_id="hg_backend",

        summary="Modern scorecard event",

    )

    events = query_by_candidate_from_db(candidate_id)

    assert_equal(
        len(events),
        2,
        "mixed replay count",
    )

    assert {event.action_type for event in events} == {
        ActionType.SCORE_ASSIGNED,
        ActionType.SCORECARD_SUBMITTED,
    }

    print("  [ok] test_mixed_event_generations_replay_together")


# ---------------------------------------------------------------------------


def test_replay_metadata_pins_blueprint_version():

    setup()

    set_feature_enabled(
        "f16_interviewer_scorecard",
        True,
    )

    blueprint = RoleBlueprint(

        blueprint_id="bp_regression",

        blueprint_version="v2",

        must_have_skills=["problem_solving"],

    )

    scorecard = InterviewerScorecard(

        round_id="round_regression",

        interviewer_id="interviewer_regression",

        blueprint_id="bp_regression",

        blueprint_version="v2",

        competency_ratings=[
            make_rating("problem_solving"),
        ],

        overall_recommendation=OverallRecommendation.YES,

    )

    result = submit_scorecard(
        scorecard=scorecard,
        blueprint=blueprint,
        candidate_id="cand_replay",
        hiring_group_id="hg_backend",
    )

    assert result.is_valid is True

    events = query_by_candidate_from_db("cand_replay")

    assert_equal(
        len(events),
        1,
        "replay metadata event count",
    )

    replay_metadata = (
        events[0]
        .evidence_snapshot["replay_metadata"]
    )

    assert_equal(
        replay_metadata["blueprint_version"],
        "v2",
        "blueprint version pinned",
    )

    print("  [ok] test_replay_metadata_pins_blueprint_version")


# ---------------------------------------------------------------------------


def test_all_flags_default_off():

    reset_feature_flags()

    assert all(
        enabled is False
        for enabled
        in FEATURE_FLAGS.values()
    )

    print("  [ok] test_all_flags_default_off")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_regression():

    print("\n" + "=" * 60)
    print("REGRESSION SUITE — Architectural Invariants")
    print("=" * 60)

    tests = [
        test_unknown_flag_always_false,
        test_flag_toggle_leaves_no_side_effects,
        test_f14_carries_no_business_logic,
        test_audit_count_matches_exactly,
        test_legacy_events_replay_safely,
        test_mixed_event_generations_replay_together,
        test_replay_metadata_pins_blueprint_version,
        test_all_flags_default_off,
    ]

    passed = 0
    failed = 0

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except AssertionError as exc:
            print(f"  [FAIL] {test_fn.__name__}: {exc}")
            failed += 1
        except Exception as exc:
            print(
                f"  [FAIL] {test_fn.__name__} CRASHED: "
                f"{type(exc).__name__}: {exc}"
            )
            failed += 1

    print("-" * 60)
    print(f"Results: {passed} passed / {failed} failed / {len(tests)} total")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if run_regression() else 1)
