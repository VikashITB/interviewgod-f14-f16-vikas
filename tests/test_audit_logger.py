"""
tests/test_audit_logger.py
==========================
Audit Logger — EOD test suite.

Covers:
    1. Insert 5 audit rows
    2. Query by candidate_id
    3. Query by hiring_group_id
    4. Query by date range
    5. UPDATE blocked
    6. DELETE blocked
"""

import sys
import os
import sqlite3
import tempfile

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
    timedelta,

)

from utils.audit_logger import (

    ActionType,
    AuditMutationForbidden,
    EVIDENCE_SCHEMA_VERSION,
    PipelineStage,
    log_audit_event,
    query_by_candidate,
    query_by_candidate_from_db,
    query_by_hiring_group,
    query_by_pipeline_stage,
    query_by_date_range,
    query_all,
    get_store_count,
    clear_store_for_testing,
    update_audit_event,
    delete_audit_event,
    get_original_f14_action_category,

)
from database import (
    get_connection,
    set_database_path_for_testing,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def setup():

    """
    Reset store before each test.
    """

    temp_db = tempfile.NamedTemporaryFile(
        suffix=".sqlite3",
        delete=False,
    )

    temp_db.close()

    set_database_path_for_testing(
        temp_db.name
    )

    clear_store_for_testing()

# ---------------------------------------------------------------------------

def assert_equal(
    actual,
    expected,
    label=""
):

    assert actual == expected, (

        f"FAIL [{label}] "
        f"expected={expected!r} "
        f"got={actual!r}"

    )

# ---------------------------------------------------------------------------

def assert_true(
    condition,
    label=""
):

    assert condition, (

        f"FAIL [{label}] "
        f"condition was False"

    )

# ---------------------------------------------------------------------------

def assert_raises(
    exception_class,
    fn,
    label=""
):

    try:

        fn()

        assert False, (

            f"FAIL [{label}] "
            f"expected "
            f"{exception_class.__name__}"

        )

    except exception_class:

        pass

    except Exception as exc:

        assert False, (

            f"FAIL [{label}] "
            f"expected "
            f"{exception_class.__name__} "
            f"but got "
            f"{type(exc).__name__}: {exc}"

        )

# ---------------------------------------------------------------------------
# Test 1 — Insert 5 rows
# ---------------------------------------------------------------------------

def test_insert_five_rows():

    setup()

    events = [

        log_audit_event(

            action_type=
                ActionType.SCORECARD_SUBMITTED,

            actor_id=
                f"interviewer_{i}",

            actor_email=
                f"i{i}@company.com",

            candidate_id=
                f"cand_{i:03d}",

            hiring_group_id=
                "hg_backend",

            summary=
                f"Test event {i}",

        )

        for i in range(5)

    ]

    assert_equal(

        get_store_count(),

        5,

        "store count"

    )

    assert_equal(

        len(events),

        5,

        "event count"

    )

    event_ids = [

        event.event_id

        for event
        in events

    ]

    assert_equal(

        len(set(event_ids)),

        5,

        "unique ids"

    )

    try:

        events[0].action_type = "TAMPERED"

        assert False

    except Exception:

        pass

    print("  [ok] test_insert_five_rows")

# ---------------------------------------------------------------------------
# Test 2 — Query by candidate
# ---------------------------------------------------------------------------

def test_query_by_candidate():

    setup()

    log_audit_event(

        action_type=
            ActionType.SCORECARD_SUBMITTED,

        actor_id="i1",

        actor_email="i1@company.com",

        candidate_id="cand_001",

        hiring_group_id="hg_a",

    )

    log_audit_event(

        action_type=
            ActionType.CONSENT_RECORDED,

        actor_id="cand_001",

        actor_email="cand@email.com",

        candidate_id="cand_001",

        hiring_group_id="hg_a",

    )

    log_audit_event(

        action_type=
            ActionType.CANDIDATE_KNOCKED_OUT,

        actor_id="system",

        actor_email="sys@company.com",

        candidate_id="cand_002",

        hiring_group_id="hg_a",

    )

    results = query_by_candidate(
        "cand_001"
    )

    assert_equal(

        len(results),

        2,

        "cand_001 count"

    )

    assert_true(

        all(
            event.candidate_id == "cand_001"
            for event in results
        ),

        "correct candidate ids"

    )

    results_002 = query_by_candidate(
        "cand_002"
    )

    assert_equal(

        len(results_002),

        1,

        "cand_002 count"

    )

    print("  [ok] test_query_by_candidate")

# ---------------------------------------------------------------------------
# Test 3 — Query by hiring group
# ---------------------------------------------------------------------------

def test_query_by_hiring_group():

    setup()

    log_audit_event(

        action_type=
            ActionType.SCORECARD_SUBMITTED,

        actor_id="i1",

        actor_email="i1@company.com",

        hiring_group_id="hg_backend",

    )

    log_audit_event(

        action_type=
            ActionType.RECOMMENDATION_GENERATED,

        actor_id="system",

        actor_email="sys@company.com",

        hiring_group_id="hg_backend",

    )

    log_audit_event(

        action_type=
            ActionType.HR_OVERRIDE_APPLIED,

        actor_id="hr_u01",

        actor_email="hr@company.com",

        hiring_group_id="hg_design",

    )

    backend_events = query_by_hiring_group(
        "hg_backend"
    )

    assert_equal(

        len(backend_events),

        2,

        "backend count"

    )

    design_events = query_by_hiring_group(
        "hg_design"
    )

    assert_equal(

        len(design_events),

        1,

        "design count"

    )

    print("  [ok] test_query_by_hiring_group")

# ---------------------------------------------------------------------------
# Test 4 — Query by date range
# ---------------------------------------------------------------------------

def test_query_by_date_range():

    setup()

    now = datetime.now(
        timezone.utc
    )

    log_audit_event(

        action_type=
            ActionType.SCORECARD_SUBMITTED,

        actor_id="i1",

        actor_email="i1@company.com",

    )

    log_audit_event(

        action_type=
            ActionType.CONSENT_RECORDED,

        actor_id="a",

        actor_email="a@company.com",

    )

    log_audit_event(

        action_type=
            ActionType.CANDIDATE_KNOCKED_OUT,

        actor_id="b",

        actor_email="b@company.com",

    )

    start = now - timedelta(minutes=5)

    end = now + timedelta(minutes=5)

    results = query_by_date_range(
        start,
        end
    )

    assert_equal(

        len(results),

        3,

        "date range count"

    )

    future_results = query_by_date_range(

        now + timedelta(hours=1),

        now + timedelta(hours=2),

    )

    assert_equal(

        len(future_results),

        0,

        "future count"

    )

    print("  [ok] test_query_by_date_range")

# ---------------------------------------------------------------------------
# Test 5 — UPDATE blocked
# ---------------------------------------------------------------------------

def test_update_blocked():

    setup()

    assert_raises(

        AuditMutationForbidden,

        lambda: update_audit_event(

            event_id="any",

            summary="tampered"

        ),

        "update blocked"

    )

    print("  [ok] test_update_blocked")

# ---------------------------------------------------------------------------
# Test 6 — DELETE blocked
# ---------------------------------------------------------------------------

def test_delete_blocked():

    setup()

    assert_raises(

        AuditMutationForbidden,

        lambda: delete_audit_event(

            event_id="any"

        ),

        "delete blocked"

    )

    print("  [ok] test_delete_blocked")

# ---------------------------------------------------------------------------
# Test 7 — evidence snapshot preserved
# ---------------------------------------------------------------------------

def test_evidence_snapshot_preserved():

    setup()

    payload = {

        "scorecard_id":
            "sc_001",

        "normalized_scores": {

            "problem_solving": 75,

            "communication": 95,

        },

        "blocking_reason":
            None,

    }

    log_audit_event(

        action_type=
            ActionType.SCORECARD_SUBMITTED,

        actor_id="i1",

        actor_email="i1@company.com",

        evidence_snapshot=payload,

    )

    retrieved = query_all()[0]

    assert_equal(

        retrieved.evidence_snapshot,

        payload,

        "payload preserved"

    )

    print("  [ok] test_evidence_snapshot_preserved")

# ---------------------------------------------------------------------------
# Test 8 - pipeline stage preserved
# ---------------------------------------------------------------------------

def test_pipeline_stage_preserved():

    setup()

    log_audit_event(

        action_type=
            ActionType.RECOMMENDATION_GENERATED,

        pipeline_stage=
            PipelineStage.RECOMMENDATION,

        actor_id="worker",

        actor_email="system@company.com",

        candidate_id="cand_stage",

    )

    retrieved = query_all()[0]

    assert_equal(

        retrieved.pipeline_stage,

        PipelineStage.RECOMMENDATION,

        "pipeline stage preserved"

    )

    stage_results = query_by_pipeline_stage(
        PipelineStage.RECOMMENDATION
    )

    assert_equal(

        len(stage_results),

        1,

        "pipeline stage query"

    )

    print("  [ok] test_pipeline_stage_preserved")


# ---------------------------------------------------------------------------
# Test 9 - recommendation payload replayability
# ---------------------------------------------------------------------------

def test_recommendation_payload_replayability():

    setup()

    recommendation_payload = {

        "evidence_schema_version":
            EVIDENCE_SCHEMA_VERSION,

        "replay_metadata": {

            "blueprint_version":
                "v1",

            "evaluator_version":
                "recommendation_worker_v1",

            "feature_flags": {
                "recommendation_explainability": True,
            },

            "threshold_snapshot": {
                "minimum_recommendation_confidence": 0.7,
            },

        },

        "recommendation_inputs": [
            "competency_scores",
            "integrity_flags",
            "screening_results",
        ],

        "competency_scores": {
            "System Design": 75,
            "Distributed Systems": 82,
        },

        "integrity_flags": {
            "tab_switch_count": 2,
            "copy_paste_detected": False,
            "voice_mismatch_detected": False,
            "response_latency_seconds": 14,
            "suspicious_behavior_score": 0.18,
        },

        "screening_results": {
            "resume_screen_passed": True,
            "knockout_passed": True,
        },

        "recommendation_reasoning": (
            "Advance because validated competency evidence is positive "
            "and integrity risk is low."
        ),

        "recommendation_confidence": 0.82,

        "recommendation_source": "recommendation_worker.py",

    }

    log_audit_event(

        action_type=
            ActionType.RECOMMENDATION_GENERATED,

        pipeline_stage=
            PipelineStage.RECOMMENDATION,

        actor_id="worker::recommendation_engine",

        actor_email="system@platform.internal",

        candidate_id="cand_replay",

        evidence_snapshot=recommendation_payload,

    )

    stored_evidence = query_all()[0].evidence_snapshot

    replayed_payload = {

        "evidence_schema_version":
            stored_evidence["evidence_schema_version"],

        "recommendation_inputs":
            stored_evidence["recommendation_inputs"],

        "replay_metadata":
            stored_evidence["replay_metadata"],

        "competency_scores":
            stored_evidence["competency_scores"],

        "integrity_flags":
            stored_evidence["integrity_flags"],

        "screening_results":
            stored_evidence["screening_results"],

        "recommendation_reasoning":
            stored_evidence["recommendation_reasoning"],

        "recommendation_confidence":
            stored_evidence["recommendation_confidence"],

        "recommendation_source":
            stored_evidence["recommendation_source"],

    }

    assert_equal(

        replayed_payload,

        recommendation_payload,

        "recommendation payload replayability"

    )

    print("  [ok] test_recommendation_payload_replayability")


# ---------------------------------------------------------------------------
# Test 10 - persisted candidate timeline replayability
# ---------------------------------------------------------------------------

def test_candidate_timeline_replayability_from_db():

    setup()

    candidate_id = (
        "cand_db_replay_"
        f"{datetime.now(timezone.utc).timestamp()}"
    )

    payload = {

        "evidence_schema_version":
            EVIDENCE_SCHEMA_VERSION,

        "replay_metadata": {

            "blueprint_version":
                "v1",

            "evaluator_version":
                "scorecard_validator_v1",

            "feature_flags": {
                "f16_interviewer_scorecard": True,
            },

            "threshold_snapshot": {
                "required_competencies": [
                    "System Design",
                ],
                "evidence_required_per_competency": True,
            },

        },

        "competency":
            "System Design",

        "score":
            75,

        "reasoning_quality":
            "partial",

        "confidence_score":
            0.61,

    }

    event = log_audit_event(

        action_type=
            ActionType.SCORECARD_SUBMITTED,

        pipeline_stage=
            PipelineStage.CALL_SCREENING,

        actor_id="interviewer_db_replay",

        actor_email="interviewer@platform.internal",

        candidate_id=candidate_id,

        hiring_group_id="hg_backend",

        evidence_snapshot=payload,

        summary="Persisted event for timeline replay",

    )

    clear_store_for_testing()

    replayed_events = query_by_candidate_from_db(
        candidate_id
    )

    assert_equal(

        len(replayed_events),

        1,

        "persisted timeline event count"

    )

    replayed = replayed_events[0]

    assert_equal(

        replayed.event_id,

        event.event_id,

        "persisted timeline event id"

    )

    assert_equal(

        replayed.pipeline_stage,

        PipelineStage.CALL_SCREENING,

        "persisted timeline stage"

    )

    assert_equal(

        replayed.evidence_snapshot,

        payload,

        "persisted timeline evidence"

    )

    assert_equal(

        replayed.evidence_snapshot["replay_metadata"],

        payload["replay_metadata"],

        "persisted replay metadata"

    )

    print("  [ok] test_candidate_timeline_replayability_from_db")


# ---------------------------------------------------------------------------
# Test 11 - SQLite UPDATE trigger blocks direct mutation
# ---------------------------------------------------------------------------

def test_db_update_trigger_blocks_mutation():

    setup()

    event = log_audit_event(

        action_type=
            ActionType.CANDIDATE_VIEWED,

        actor_id="recruiter_trigger",

        actor_email="recruiter@platform.internal",

        candidate_id="cand_trigger_update",

        summary="Original summary",

    )

    conn = get_connection()

    cursor = conn.cursor()

    assert_raises(

        sqlite3.IntegrityError,

        lambda: cursor.execute(
            """
            UPDATE audit_trail
            SET summary = ?
            WHERE event_id = ?
            """,
            (
                "Tampered summary",
                event.event_id,
            ),
        ),

        "db update trigger",

    )

    conn.rollback()

    cursor.execute(
        """
        SELECT summary
        FROM audit_trail
        WHERE event_id = ?
        """,
        (event.event_id,),
    )

    row = cursor.fetchone()

    conn.close()

    assert_equal(

        row[0],

        "Original summary",

        "summary remains unchanged after blocked update",

    )

    print("  [ok] test_db_update_trigger_blocks_mutation")


# ---------------------------------------------------------------------------
# Test 12 - SQLite DELETE trigger blocks direct mutation
# ---------------------------------------------------------------------------

def test_db_delete_trigger_blocks_mutation():

    setup()

    event = log_audit_event(

        action_type=
            ActionType.CONSENT_GRANTED,

        actor_id="candidate_trigger",

        actor_email="candidate@demo.local",

        candidate_id="cand_trigger_delete",

        summary="Consent granted",

    )

    conn = get_connection()

    cursor = conn.cursor()

    assert_raises(

        sqlite3.IntegrityError,

        lambda: cursor.execute(
            """
            DELETE FROM audit_trail
            WHERE event_id = ?
            """,
            (event.event_id,),
        ),

        "db delete trigger",

    )

    conn.rollback()

    cursor.execute(
        """
        SELECT COUNT(*)
        FROM audit_trail
        WHERE event_id = ?
        """,
        (event.event_id,),
    )

    row = cursor.fetchone()

    conn.close()

    assert_equal(

        row[0],

        1,

        "row remains after blocked delete",

    )

    print("  [ok] test_db_delete_trigger_blocks_mutation")


# ---------------------------------------------------------------------------
# Test 13 - semantic action taxonomy maps to original F14 category
# ---------------------------------------------------------------------------

def test_semantic_action_taxonomy_alignment():

    setup()

    assert_equal(

        get_original_f14_action_category(
            ActionType.SCORECARD_SUBMITTED
        ),

        "score_assigned",

        "scorecard submitted category",

    )

    assert_equal(

        get_original_f14_action_category(
            ActionType.SCORECARD_BLOCKED
        ),

        "ai_processing_blocked",

        "scorecard blocked category",

    )

    assert_equal(

        get_original_f14_action_category(
            "decision_overridden"
        ),

        "decision_overridden",

        "original string category",

    )

    print("  [ok] test_semantic_action_taxonomy_alignment")

def test_first_class_blueprint_and_actor_metadata_round_trip():

    setup()

    log_audit_event(
        action_type=ActionType.SCORECARD_SUBMITTED,
        actor_id="interviewer_metadata",
        actor_email="interviewer_metadata@platform.internal",
        actor_type="INTERVIEWER",
        candidate_id="cand_metadata",
        round_id="round_metadata",
        hiring_group_id="hg_metadata",
        blueprint_id="bp_metadata",
        blueprint_version="v3",
        evidence_snapshot={
            "blueprint_id": "bp_metadata",
            "blueprint_version": "v3",
        },
        summary="Metadata round trip",
    )

    memory_event = query_all()[0]

    assert_equal(
        memory_event.actor_type,
        "INTERVIEWER",
        "actor_type first-class in memory",
    )

    assert_equal(
        memory_event.blueprint_id,
        "bp_metadata",
        "blueprint_id first-class in memory",
    )

    assert_equal(
        memory_event.blueprint_version,
        "v3",
        "blueprint_version first-class in memory",
    )

    db_event = query_by_candidate_from_db(
        "cand_metadata"
    )[0]

    assert_equal(
        db_event.actor_type,
        "INTERVIEWER",
        "actor_type reconstructed from db",
    )

    assert_equal(
        db_event.blueprint_id,
        "bp_metadata",
        "blueprint_id reconstructed from db",
    )

    assert_equal(
        db_event.blueprint_version,
        "v3",
        "blueprint_version reconstructed from db",
    )

    assert_equal(
        db_event.evidence_snapshot["blueprint_id"],
        "bp_metadata",
        "evidence blueprint_id preserved",
    )

    print(
        "  [ok] "
        "test_first_class_blueprint_and_actor_metadata_round_trip"
    )

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all_tests():

    print("\n" + "=" * 60)

    print("AUDIT LOGGER — TEST SUITE")

    print("=" * 60)

    tests = [

        test_insert_five_rows,
        test_query_by_candidate,
        test_query_by_hiring_group,
        test_query_by_date_range,
        test_update_blocked,
        test_delete_blocked,
        test_evidence_snapshot_preserved,
        test_pipeline_stage_preserved,
        test_recommendation_payload_replayability,
        test_candidate_timeline_replayability_from_db,
        test_db_update_trigger_blocks_mutation,
        test_db_delete_trigger_blocks_mutation,
        test_semantic_action_taxonomy_alignment,
        test_first_class_blueprint_and_actor_metadata_round_trip,

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

            print(
                f"  [fail] "
                f"{test_fn.__name__} "
                f"CRASHED: "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

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
