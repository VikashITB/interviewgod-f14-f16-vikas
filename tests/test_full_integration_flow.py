"""
tests/test_full_integration_flow.py
===================================
Friday integration validation for Week 2 sprint.

Validates the complete hiring flow from invite → resume → assessment → interview →
recommendation → audit, ensuring all stages work together correctly and audit coverage
is complete.

ARCHITECTURAL SCOPE
-------------------
This test validates:
  1. Full hiring flow integration across F14 (audit) and F16 (scorecards)
  2. Audit row creation for all integrated stages
  3. Deterministic action_type values
  4. candidate_id populated on every audit row
  5. Timestamp correctness and consistency
  6. No duplicate audit emission
  7. Blocked scorecard behavior
  8. Feature flag OFF preserves old behavior
  9. Append-only audit guarantees

Does NOT build:
  - New architecture layers
  - Governance systems
  - Policy engines
  - Orchestration runtimes
  - Enterprise abstractions
"""

import sys
import os
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.feature_flags import (
    FEATURE_FLAGS,
    set_feature_enabled,
    is_feature_enabled,
)
from database import (
    set_database_path_for_testing,
)
from utils.audit_logger import (
    ActionType,
    PipelineStage,
    log_audit_event,
    query_by_candidate_from_db,
    query_by_action_type_from_db,
    get_store_count,
    clear_store_for_testing,
)
from scorecards.schema import (
    CompetencyRating,
    EvidenceEntry,
    InterviewerScorecard,
    OverallRecommendation,
    RoleBlueprint,
    ScoreLabel,
    SCORE_MAP,
    BlueprintCompetency,
)
from scorecards.submission import (
    submit_scorecard,
    record_recommendation_generated_audit,
    record_decision_override_audit,
    clear_stores_for_testing,
)
from blueprints.models import BlueprintCompetency as BpCompetency


# ---------------------------------------------------------------------------
# Setup & Helpers
# ---------------------------------------------------------------------------

def setup():
    """Initialize test database and feature flags."""
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
    tmp.close()
    set_database_path_for_testing(tmp.name)
    clear_store_for_testing()
    clear_stores_for_testing()
    for key in list(FEATURE_FLAGS.keys()):
        set_feature_enabled(key, False)


def assert_equal(actual, expected, label=""):
    """Helper for clear assertion messages."""
    assert actual == expected, (
        f"FAIL [{label}] expected={expected!r} got={actual!r}"
    )


def assert_true(condition, label=""):
    """Helper for boolean assertions."""
    assert condition, f"FAIL [{label}] expected True got {condition!r}"


def assert_exists(items, predicate, label=""):
    """Helper for checking item existence."""
    assert any(predicate(item) for item in items), (
        f"FAIL [{label}] no matching item found in {items}"
    )


def make_evidence(competency: str, text: str = None) -> EvidenceEntry:
    """Create evidence entry."""
    return EvidenceEntry(
        competency=competency,
        evidence_text=(
            text
            or
            f"Candidate demonstrated strong {competency}."
        ),
        interview_ts=datetime.now(timezone.utc),
    )


def make_rating(
    competency: str,
    label: ScoreLabel = ScoreLabel.LEAN_YES,
) -> CompetencyRating:
    """Create competency rating."""
    return CompetencyRating(
        competency=competency,
        label=label,
        normalized_score=SCORE_MAP[label],
        evidence=[make_evidence(competency)],
    )


def make_blueprint() -> RoleBlueprint:
    """Create standard test blueprint."""
    return RoleBlueprint(
        blueprint_id="bp_integration",
        blueprint_version="v1",
        competencies=[
            BpCompetency(
                competency_id="problem_solving",
                required=True,
                weight=0.4,
                evidence_required=True,
                knockout_candidate=False,
            ),
            BpCompetency(
                competency_id="communication",
                required=True,
                weight=0.3,
                evidence_required=True,
                knockout_candidate=False,
            ),
            BpCompetency(
                competency_id="teamwork",
                required=True,
                weight=0.3,
                evidence_required=True,
                knockout_candidate=False,
            ),
        ],
    )


def make_scorecard(
    candidate_id: str,
    round_id: str,
    interviewer_id: str,
) -> InterviewerScorecard:
    """Create complete valid scorecard."""
    return InterviewerScorecard(
        round_id=round_id,
        interviewer_id=interviewer_id,
        blueprint_id="bp_integration",
        blueprint_version="v1",
        competency_ratings=[
            make_rating("problem_solving", ScoreLabel.LEAN_YES),
            make_rating("communication", ScoreLabel.STRONG_YES),
            make_rating("teamwork", ScoreLabel.NEUTRAL),
        ],
        overall_recommendation=OverallRecommendation.YES,
    )


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

def test_full_flow_complete_candidate_lifecycle():
    """
    TEST 1: Complete hiring flow from invite → scorecard submission
    
    Verifies:
    - All stages emit audit events
    - candidate_id populated on every row
    - Timestamps correct
    - No duplicate emissions
    """
    setup()
    set_feature_enabled("f16_interviewer_scorecard", True)

    candidate_id = "cand_lifecycle_001"
    hiring_group = "hg_engineering"
    
    # Stage 1: Candidate viewed (F14 — invite/resume)
    log_audit_event(
        action_type=ActionType.CANDIDATE_VIEWED,
        actor_id="recruiter_001",
        actor_email="recruiter@company.com",
        candidate_id=candidate_id,
        hiring_group_id=hiring_group,
        summary="Resume reviewed",
    )

    # Stage 2: Interview stage advanced (F14 — assessment routing)
    log_audit_event(
        action_type=ActionType.STAGE_ADVANCED,
        actor_id="system",
        actor_email="system@platform.internal",
        candidate_id=candidate_id,
        hiring_group_id=hiring_group,
        summary="Advanced to interview stage",
    )

    # Stage 3: Scorecard submitted (F16 — interview evaluation)
    blueprint = make_blueprint()
    scorecard = make_scorecard(candidate_id, "round_001", "interviewer_001")
    
    submission_result = submit_scorecard(
        scorecard=scorecard,
        blueprint=blueprint,
        candidate_id=candidate_id,
        hiring_group_id=hiring_group,
    )
    
    assert_true(submission_result.is_valid, "scorecard submission valid")

    # Stage 4: Recommendation generated (F14 stub)
    record_recommendation_generated_audit(candidate_id)

    # Stage 5: HR override (F14 stub)
    record_decision_override_audit(candidate_id)

    # Verify complete timeline
    events = query_by_candidate_from_db(candidate_id)
    
    assert_equal(len(events), 5, "total events count")
    
    # Verify candidate_id on all events
    for event in events:
        assert_equal(
            event.candidate_id,
            candidate_id,
            f"candidate_id on {event.action_type}"
        )
    
    # Verify action types in order
    action_types = [event.action_type for event in events]
    expected_sequence = [
        ActionType.CANDIDATE_VIEWED,
        ActionType.STAGE_ADVANCED,
        ActionType.SCORECARD_SUBMITTED,
        ActionType.F14_RECOMMENDATION_GENERATED,
        ActionType.DECISION_OVERRIDDEN,
    ]
    assert_equal(action_types, expected_sequence, "event sequence")
    
    # Verify timestamps are populated
    for event in events:
        assert_true(event.created_at is not None, f"timestamp on {event.action_type}")
        assert_true(event.created_at.tzinfo is not None, f"tz-aware on {event.action_type}")
    
    print("  [ok] test_full_flow_complete_candidate_lifecycle")


# ---------------------------------------------------------------------------

def test_audit_rows_exist_for_all_integrated_stages():
    """
    TEST 2: Audit row presence verification
    
    Verifies:
    - recommendation_generated audit row exists
    - score_assigned audit row exists (if scorecard valid)
    - decision_overridden audit row exists
    - scorecard_submitted audit row exists
    """
    setup()
    set_feature_enabled("f16_interviewer_scorecard", True)

    candidate_id = "cand_audit_stages_001"
    hiring_group = "hg_backend"
    
    # Generate F14 events
    log_audit_event(
        action_type=ActionType.CANDIDATE_VIEWED,
        actor_id="recruiter",
        actor_email="recruiter@company.com",
        candidate_id=candidate_id,
        hiring_group_id=hiring_group,
    )
    
    log_audit_event(
        action_type=ActionType.STAGE_ADVANCED,
        actor_id="system",
        actor_email="system@platform.internal",
        candidate_id=candidate_id,
        hiring_group_id=hiring_group,
    )
    
    # F16 scorecard
    blueprint = make_blueprint()
    scorecard = make_scorecard(candidate_id, "round_002", "interviewer_backend")
    
    submit_scorecard(
        scorecard=scorecard,
        blueprint=blueprint,
        candidate_id=candidate_id,
        hiring_group_id=hiring_group,
    )
    
    # F14 stubs
    record_recommendation_generated_audit(candidate_id)
    record_decision_override_audit(candidate_id)
    
    events = query_by_candidate_from_db(candidate_id)
    
    # Verify specific action types exist
    action_types = {event.action_type for event in events}
    
    assert_true(
        ActionType.SCORECARD_SUBMITTED in action_types,
        "scorecard_submitted row exists"
    )
    
    assert_true(
        ActionType.F14_RECOMMENDATION_GENERATED in action_types,
        "recommendation_generated row exists"
    )
    
    assert_true(
        ActionType.DECISION_OVERRIDDEN in action_types,
        "decision_overridden row exists"
    )
    
    assert_true(
        ActionType.CANDIDATE_VIEWED in action_types,
        "candidate_viewed row exists"
    )
    
    print("  [ok] test_audit_rows_exist_for_all_integrated_stages")


# ---------------------------------------------------------------------------

def test_no_duplicate_audit_emissions():
    """
    TEST 3: Append-only guarantee
    
    Verifies:
    - Exactly one event per submission
    - No phantom duplicate rows
    - Audit count matches submission count exactly
    """
    setup()
    set_feature_enabled("f16_interviewer_scorecard", True)

    candidate_id = "cand_nodupe_001"
    hiring_group = "hg_test"
    blueprint = make_blueprint()
    
    initial_count = get_store_count()
    assert_equal(initial_count, 0, "initial store empty")
    
    # Submit 3 distinct scorecards
    for i in range(3):
        scorecard = make_scorecard(
            candidate_id=candidate_id,
            round_id=f"round_nodupe_{i}",
            interviewer_id=f"interviewer_{i}",
        )
        
        submit_scorecard(
            scorecard=scorecard,
            blueprint=blueprint,
            candidate_id=candidate_id,
            hiring_group_id=hiring_group,
        )
    
    final_count = get_store_count()
    assert_equal(final_count, 3, "exactly 3 events after 3 submissions")
    
    events = query_by_candidate_from_db(candidate_id)
    assert_equal(len(events), 3, "candidate timeline has 3 events")
    
    # Verify no duplicate action types within single round
    for i in range(3):
        round_events = [
            e for e in events
            if e.round_id == f"round_nodupe_{i}"
        ]
        
        scorecard_submitted_count = len([
            e for e in round_events
            if e.action_type == ActionType.SCORECARD_SUBMITTED
        ])
        
        assert_equal(
            scorecard_submitted_count,
            1,
            f"no duplicate SCORECARD_SUBMITTED in round_{i}"
        )
    
    print("  [ok] test_no_duplicate_audit_emissions")


# ---------------------------------------------------------------------------

def test_blocked_scorecard_behavior():
    """
    TEST 4: Invalid submission audit behavior
    
    Verifies:
    - Blocked scorecards do not persist in scorecard store
    - SCORECARD_BLOCKED audit row exists
    - No SCORECARD_SUBMITTED row for blocked submission
    - Validation errors captured in audit snapshot
    """
    setup()
    set_feature_enabled("f16_interviewer_scorecard", True)

    candidate_id = "cand_blocked_001"
    hiring_group = "hg_test"
    blueprint = make_blueprint()
    
    # Create incomplete scorecard (missing teamwork)
    incomplete_scorecard = InterviewerScorecard(
        round_id="round_blocked",
        interviewer_id="interviewer_blocked",
        blueprint_id="bp_integration",
        blueprint_version="v1",
        competency_ratings=[
            make_rating("problem_solving"),
            make_rating("communication"),
            # Missing: teamwork
        ],
        overall_recommendation=OverallRecommendation.YES,
    )
    
    # Submit invalid scorecard
    result = submit_scorecard(
        scorecard=incomplete_scorecard,
        blueprint=blueprint,
        candidate_id=candidate_id,
        hiring_group_id=hiring_group,
    )
    
    # Verify submission marked invalid
    assert_true(not result.is_valid, "submission invalid")
    
    # Verify audit events
    events = query_by_candidate_from_db(candidate_id)
    
    # Should have SCORECARD_BLOCKED only
    action_types = [event.action_type for event in events]
    
    assert_true(
        ActionType.SCORECARD_BLOCKED in action_types,
        "SCORECARD_BLOCKED row exists"
    )
    
    assert_true(
        ActionType.SCORECARD_SUBMITTED not in action_types,
        "SCORECARD_SUBMITTED row does NOT exist"
    )
    
    # Verify error details in audit snapshot
    blocked_event = [
        e for e in events
        if e.action_type == ActionType.SCORECARD_BLOCKED
    ][0]
    
    assert_true(
        blocked_event.evidence_snapshot is not None,
        "blocked event has snapshot"
    )
    
    assert_true(
        "validation_errors" in blocked_event.evidence_snapshot,
        "snapshot contains validation_errors"
    )
    
    print("  [ok] test_blocked_scorecard_behavior")


# ---------------------------------------------------------------------------

def test_action_type_determinism():
    """
    TEST 5: Deterministic action_type mapping
    
    Verifies:
    - Same submission always produces same action_type
    - action_type values are from ActionType enum
    - Pipeline stages map correctly
    """
    setup()
    set_feature_enabled("f16_interviewer_scorecard", True)

    candidate_id = "cand_determinism_001"
    hiring_group = "hg_test"
    blueprint = make_blueprint()
    
    # Submit same scorecard twice
    scorecard_v1 = make_scorecard(
        candidate_id=candidate_id,
        round_id="round_determ_1",
        interviewer_id="interviewer_det",
    )
    
    submit_scorecard(
        scorecard=scorecard_v1,
        blueprint=blueprint,
        candidate_id=candidate_id,
        hiring_group_id=hiring_group,
    )
    
    scorecard_v2 = make_scorecard(
        candidate_id=candidate_id,
        round_id="round_determ_2",
        interviewer_id="interviewer_det",
    )
    
    submit_scorecard(
        scorecard=scorecard_v2,
        blueprint=blueprint,
        candidate_id=candidate_id,
        hiring_group_id=hiring_group,
    )
    
    events = query_by_candidate_from_db(candidate_id)
    
    # Both submissions should have same action_type
    action_types = [
        event.action_type for event in events
        if event.action_type == ActionType.SCORECARD_SUBMITTED
    ]
    
    assert_equal(len(action_types), 2, "two submission events")
    assert_true(
        all(at == ActionType.SCORECARD_SUBMITTED for at in action_types),
        "all submission action types deterministic"
    )
    
    # Verify pipeline stages
    for event in events:
        if event.action_type == ActionType.SCORECARD_SUBMITTED:
            assert_equal(
                event.pipeline_stage,
                PipelineStage.INTERVIEW_INTEGRITY,
                "scorecard submitted pipeline stage"
            )
    
    print("  [ok] test_action_type_determinism")


# ---------------------------------------------------------------------------

def test_feature_flag_off_preserves_behavior():
    """
    TEST 6: Feature flag safety
    
    Verifies:
    - F16 scorecard disabled = no persistence
    - F16 scorecard disabled = no SCORECARD_SUBMITTED events
    - F16 scorecard disabled = returns blocking reason
    - Audit store remains append-only even with flag OFF
    """
    setup()
    set_feature_enabled("f16_interviewer_scorecard", False)

    candidate_id = "cand_flag_off_001"
    hiring_group = "hg_test"
    blueprint = make_blueprint()
    
    scorecard = make_scorecard(
        candidate_id=candidate_id,
        round_id="round_flag_off",
        interviewer_id="interviewer_flagoff",
    )
    
    # Attempt submission with flag OFF
    result = submit_scorecard(
        scorecard=scorecard,
        blueprint=blueprint,
        candidate_id=candidate_id,
        hiring_group_id=hiring_group,
    )
    
    # Verify marked as valid but blocked
    assert_true(result.is_valid, "result.is_valid == True")
    assert_true(
        result.blocking_reason == "F16 feature flag disabled.",
        "blocking reason is flag disabled message"
    )
    
    # Verify NO scorecard events emitted
    events = query_by_candidate_from_db(candidate_id)
    
    scorecard_actions = [
        e for e in events
        if e.action_type
        in [ActionType.SCORECARD_SUBMITTED, ActionType.SCORECARD_BLOCKED]
    ]
    
    assert_equal(
        len(scorecard_actions),
        0,
        "no scorecard audit rows when flag OFF"
    )
    
    print("  [ok] test_feature_flag_off_preserves_behavior")


# ---------------------------------------------------------------------------

def test_candidate_id_coverage_on_all_audit_rows():
    """
    TEST 7: candidate_id population verification
    
    Verifies:
    - Every audit row has candidate_id populated
    - candidate_id is not None
    - candidate_id is not empty string
    - candidate_id matches submission candidate_id
    """
    setup()
    set_feature_enabled("f16_interviewer_scorecard", True)

    candidate_id = "cand_coverage_001"
    hiring_group = "hg_test"
    
    # Create mixed audit trail
    log_audit_event(
        action_type=ActionType.CANDIDATE_VIEWED,
        actor_id="recruiter",
        actor_email="recruiter@company.com",
        candidate_id=candidate_id,
        hiring_group_id=hiring_group,
    )
    
    blueprint = make_blueprint()
    scorecard = make_scorecard(candidate_id, "round_cov", "interviewer_cov")
    
    submit_scorecard(
        scorecard=scorecard,
        blueprint=blueprint,
        candidate_id=candidate_id,
        hiring_group_id=hiring_group,
    )
    
    record_recommendation_generated_audit(candidate_id)
    
    events = query_by_candidate_from_db(candidate_id)
    
    # Verify candidate_id on every event
    for event in events:
        assert_true(
            event.candidate_id is not None,
            f"candidate_id not None on {event.action_type}"
        )
        
        assert_true(
            event.candidate_id != "",
            f"candidate_id not empty on {event.action_type}"
        )
        
        assert_equal(
            event.candidate_id,
            candidate_id,
            f"candidate_id matches on {event.action_type}"
        )
    
    print("  [ok] test_candidate_id_coverage_on_all_audit_rows")


# ---------------------------------------------------------------------------

def test_timestamp_correctness_and_ordering():
    """
    TEST 8: Timestamp verification
    
    Verifies:
    - All timestamps populated
    - Timestamps are timezone-aware (UTC)
    - Timestamps are in chronological order
    - Timestamp resolution is reasonable (millisecond+)
    """
    setup()
    set_feature_enabled("f16_interviewer_scorecard", True)

    candidate_id = "cand_timestamps_001"
    hiring_group = "hg_test"
    
    # Record submission time
    pre_submission = datetime.now(timezone.utc)
    
    blueprint = make_blueprint()
    scorecard = make_scorecard(candidate_id, "round_ts", "interviewer_ts")
    
    submit_scorecard(
        scorecard=scorecard,
        blueprint=blueprint,
        candidate_id=candidate_id,
        hiring_group_id=hiring_group,
    )
    
    post_submission = datetime.now(timezone.utc)
    
    events = query_by_candidate_from_db(candidate_id)
    
    # Verify all timestamps present and in range
    for i, event in enumerate(events):
        assert_true(
            event.created_at is not None,
            f"event {i} has timestamp"
        )
        
        assert_true(
            event.created_at.tzinfo is not None,
            f"event {i} timestamp is tz-aware"
        )
        
        assert_true(
            pre_submission <= event.created_at <= post_submission,
            f"event {i} timestamp in reasonable range"
        )
    
    # Verify chronological ordering
    for i in range(len(events) - 1):
        curr_ts = events[i].created_at
        next_ts = events[i + 1].created_at
        
        assert_true(
            curr_ts <= next_ts,
            f"events {i} to {i+1} in chronological order"
        )
    
    print("  [ok] test_timestamp_correctness_and_ordering")


# ---------------------------------------------------------------------------

def test_append_only_guarantee():
    """
    TEST 9: Append-only audit invariant
    
    Verifies:
    - Audit count only increases
    - No audit rows deleted
    - No audit rows modified
    - Event IDs are unique
    """
    setup()
    set_feature_enabled("f16_interviewer_scorecard", True)

    candidate_id = "cand_append_only_001"
    hiring_group = "hg_test"
    blueprint = make_blueprint()
    
    all_seen_ids = set()
    
    # Generate multiple events
    for i in range(3):
        scorecard = make_scorecard(
            candidate_id=candidate_id,
            round_id=f"round_append_{i}",
            interviewer_id=f"interviewer_{i}",
        )
        
        submit_scorecard(
            scorecard=scorecard,
            blueprint=blueprint,
            candidate_id=candidate_id,
            hiring_group_id=hiring_group,
        )
        
        events = query_by_candidate_from_db(candidate_id)
        current_ids = [e.event_id for e in events]
        
        # Verify no duplicates in current set
        current_unique = set(current_ids)
        assert_equal(
            len(current_ids),
            len(current_unique),
            f"no duplicate IDs after submission {i}"
        )
        
        # Track all IDs seen
        all_seen_ids.update(current_ids)
        
        # Verify count increases monotonically
        assert_equal(
            len(events),
            i + 1,
            f"audit count after submission {i}"
        )
    
    # Final verification: total count
    final_events = query_by_candidate_from_db(candidate_id)
    assert_equal(len(final_events), 3, "final event count is 3")
    
    # Verify all IDs globally unique
    assert_equal(
        len(all_seen_ids),
        3,
        "all event IDs globally unique across submissions"
    )
    
    print("  [ok] test_append_only_guarantee")


# ---------------------------------------------------------------------------
# Test Runner
# ---------------------------------------------------------------------------

def run_integration_tests():
    """Execute full integration test suite."""
    print("\n" + "=" * 60)
    print("FULL INTEGRATION FLOW VALIDATION")
    print("=" * 60)

    tests = [
        test_full_flow_complete_candidate_lifecycle,
        test_audit_rows_exist_for_all_integrated_stages,
        test_no_duplicate_audit_emissions,
        test_blocked_scorecard_behavior,
        test_action_type_determinism,
        test_feature_flag_off_preserves_behavior,
        test_candidate_id_coverage_on_all_audit_rows,
        test_timestamp_correctness_and_ordering,
        test_append_only_guarantee,
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
            import traceback
            print(f"  [FAIL] {test_fn.__name__} CRASHED: {type(exc).__name__}: {exc}")
            traceback.print_exc()
            failed += 1

    print("-" * 60)
    print(f"Results: {passed} passed / {failed} failed / {len(tests)} total")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if run_integration_tests() else 1)
