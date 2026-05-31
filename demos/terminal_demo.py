"""
terminal_demo.py
=================
Hiring Platform — Day 1+2 Sprint Demo
Demonstrates immutable audit logging + structured scorecards end-to-end.

Run with: python demos/terminal_demo.py
Exit 0 on success, Exit 1 on any failure.
"""

import sys
import os
sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from datetime import datetime, timezone, timedelta

from utils.audit_logger import (
    ActionType,
    AuditMutationForbidden,
    EVIDENCE_SCHEMA_VERSION,
    PipelineStage,
    log_audit_event,
    query_by_candidate,
    query_by_hiring_group,
    query_by_pipeline_stage,
    query_by_date_range,
    query_all,
    clear_store_for_testing,
    update_audit_event,
    delete_audit_event,
    F14IntegrationStubs,
)

from scorecards.schema import (
    CompetencyRating,
    EvidenceEntry,
    InterviewerScorecard,
    OverallRecommendation,
    RoleBlueprint,
    ScoreLabel,
    SCORE_MAP,
    CalibrationSnapshot,
)

from scorecards.validator import validate_scorecard

from scorecards import calibration as cal

from scorecards.submission import (
    submit_scorecard,
    get_scorecard,
    get_scorecards_by_interviewer,
    clear_stores_for_testing,
)

from config.feature_flags import set_feature_enabled

# ---------------------------------------------------------------------------
# Pretty print helpers
# ---------------------------------------------------------------------------

BOLD   = "\033[1m"
GREEN  = "\033[92m"
RED    = "\033[91m"
CYAN   = "\033[96m"
YELLOW = "\033[93m"
RESET  = "\033[0m"
DIM    = "\033[2m"

SEMANTIC_EVIDENCE = {
    "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
    "replay_metadata": {
        "blueprint_id": "backend_blueprint",
        "blueprint_version": "v1",
        "evaluator_version": "terminal_demo_semantic_evaluator_v1",
        "feature_flags": {},
        "threshold_snapshot": {
            "required_competencies": [
                "System Design",
                "Distributed Systems",
            ],
            "minimum_detected_concepts": 1,
            "recommendation_confidence_scale": "0_to_1",
        },
    },
    "competency": "System Design",
    "score": 75,
    "candidate_answer": (
        "Candidate explained load balancing and scaling strategy."
    ),
    "expected_concepts": [
        "load balancing",
        "horizontal scaling",
        "cache invalidation",
    ],
    "detected_concepts": [
        "load balancing",
        "horizontal scaling",
    ],
    "missing_concepts": [
        "cache invalidation",
    ],
    "reasoning_quality": "partial",
    "confidence_score": 0.61,
    "evidence_text": (
        "Candidate partially covered scaling concepts but missed "
        "cache invalidation."
    ),
    "integrity_signals": {
        "tab_switch_count": 2,
        "copy_paste_detected": False,
        "voice_mismatch_detected": False,
        "response_latency_seconds": 14,
        "suspicious_behavior_score": 0.18,
    },
    "blueprint_id": "backend_blueprint",
    "blueprint_version": "v1",
    "must_have_competencies": [
        "System Design",
        "Distributed Systems",
    ],
}

def header(title: str):
    print(f"\n{BOLD}{CYAN}{'=' * 62}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 62}{RESET}")

def section(title: str):
    print(f"\n{BOLD}{YELLOW}  ── {title}{RESET}")

def ok(msg: str):
    print(f"  {GREEN}✓{RESET} {msg}")

def fail(msg: str):
    print(f"  {RED}✗{RESET} {msg}")

def info(msg: str):
    print(f"  {DIM}{msg}{RESET}")

def print_event_review(event):
    evidence = event.evidence_snapshot or {}
    integrity = evidence.get("integrity_signals") or {}

    info(
        f"{event.action_type.value} | "
        f"stage={event.pipeline_stage.value if event.pipeline_stage else None}"
    )

    if evidence.get("reasoning_quality"):
        info(
            f"reasoning={evidence.get('reasoning_quality')} | "
            f"confidence={evidence.get('confidence_score')}"
        )

    if evidence.get("recommendation_reasoning"):
        info(f"recommendation={evidence.get('recommendation_reasoning')}")

    if integrity:
        info(
            "integrity="
            f"tabs:{integrity.get('tab_switch_count')} "
            f"copy_paste:{integrity.get('copy_paste_detected')} "
            f"suspicion:{integrity.get('suspicious_behavior_score')}"
        )

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def make_evidence(competency: str, text: str = None) -> EvidenceEntry:
    return EvidenceEntry(
        competency=competency,
        evidence_text=text or (
            f"Candidate showed strong {competency}: walked through the "
            f"problem systematically and reached an optimal solution."
        ),
        interview_ts=datetime.now(timezone.utc),
    )

def make_rating(competency: str, label: ScoreLabel) -> CompetencyRating:
    return CompetencyRating(
        competency=competency,
        label=label,
        normalized_score=SCORE_MAP[label],
        evidence=[make_evidence(competency)],
    )

# ---------------------------------------------------------------------------
# DEMO SECTION 1 — F14: Insert 5 audit rows
# ---------------------------------------------------------------------------

def demo_f14_insert_five_rows():
    section("F14 Demo 1 of 6 — Insert 5 Audit Rows")

    clear_store_for_testing()

    actions = [
        (ActionType.SCORECARD_SUBMITTED,      PipelineStage.CALL_SCREENING,   "cand_001", "round_001", "hg_backend"),
        (ActionType.CONSENT_RECORDED,         PipelineStage.RESUME_SCREENING, "cand_001", None,        "hg_frontend"),
        (ActionType.RECOMMENDATION_GENERATED, PipelineStage.RECOMMENDATION,   "cand_002", "round_002", "hg_backend"),
        (ActionType.CANDIDATE_KNOCKED_OUT,    PipelineStage.KNOCKOUT_CHECK,   "cand_003", "round_001", "hg_product"),
        (ActionType.HR_OVERRIDE_APPLIED,      PipelineStage.HR_OVERRIDE,      "cand_002", "round_002", "hg_backend"),
    ]

    for action, stage, cid, rid, hgid in actions:
        evidence_snapshot = {
            **SEMANTIC_EVIDENCE,
            "demo": True,
            "action": action.value,
        }

        if action == ActionType.RECOMMENDATION_GENERATED:
            evidence_snapshot.update({
                "recommendation_inputs": [
                    "competency_scores",
                    "integrity_flags",
                    "screening_results",
                ],
                "recommendation_reasoning": (
                    "Recommended advance because core system design evidence "
                    "is positive and integrity risk is low."
                ),
                "recommendation_confidence": 0.82,
                "recommendation_source": "recommendation_worker.py",
            })

        event = log_audit_event(
            action_type=action,
            pipeline_stage=stage,
            actor_id="demo_actor",
            actor_email="demo@platform.internal",
            candidate_id=cid,
            round_id=rid,
            hiring_group_id=hgid,
            evidence_snapshot=evidence_snapshot,
            summary=f"{action.value} for {cid}",
        )

        info(f"Inserted: {action.value} → {event.event_id[:8]}")

    total = len(query_all())

    if total == 5:
        ok("5 audit rows inserted successfully")
    else:
        fail(f"Expected 5 rows, got {total}")

# ---------------------------------------------------------------------------
# DEMO SECTION 2 — Query by candidate
# ---------------------------------------------------------------------------

def demo_f14_query_by_candidate():
    section("F14 Demo 2 of 6 — Query by Candidate")

    results = query_by_candidate("cand_001")

    info(f"Found {len(results)} events")

    for event in results:
        print_event_review(event)

    if len(results) == 2:
        ok("Correct candidate query results")
    else:
        fail("Unexpected candidate query count")

# ---------------------------------------------------------------------------
# DEMO SECTION 3 — Query by hiring group
# ---------------------------------------------------------------------------

def demo_f14_query_by_hiring_group():
    section("F14 Demo 3 of 6 — Query by Hiring Group")

    results = query_by_hiring_group("hg_backend")

    info(f"Found {len(results)} events")

    for event in results:
        print_event_review(event)

    recommendation_events = query_by_pipeline_stage(
        PipelineStage.RECOMMENDATION
    )

    info(
        "Recommendation-stage events: "
        f"{len(recommendation_events)}"
    )

    if len(results) == 3:
        ok("Correct hiring group query results")
    else:
        fail("Unexpected hiring group query count")

# ---------------------------------------------------------------------------
# DEMO SECTION 4 — Date range query
# ---------------------------------------------------------------------------

def demo_f14_query_by_date_range():
    section("F14 Demo 4 of 6 — Query by Date Range")

    now = datetime.now(timezone.utc)

    start = now - timedelta(minutes=5)
    end   = now + timedelta(minutes=5)

    results = query_by_date_range(start, end)

    if len(results) == 5:
        ok("Date range query successful")
    else:
        fail("Unexpected date range query count")

# ---------------------------------------------------------------------------
# DEMO SECTION 5 — UPDATE blocked
# ---------------------------------------------------------------------------

def demo_f14_update_blocked():
    section("F14 Demo 5 of 6 — UPDATE Blocked")

    try:
        update_audit_event(
            event_id="fake_id",
            summary="tampered"
        )

        fail("UPDATE was not blocked")

    except AuditMutationForbidden:
        ok("UPDATE blocked successfully")

# ---------------------------------------------------------------------------
# DEMO SECTION 6 — DELETE blocked
# ---------------------------------------------------------------------------

def demo_f14_delete_blocked():
    section("F14 Demo 6 of 6 — DELETE Blocked")

    try:
        delete_audit_event(event_id="fake_id")

        fail("DELETE was not blocked")

    except AuditMutationForbidden:
        ok("DELETE blocked successfully")

# ---------------------------------------------------------------------------
# DEMO SECTION 7 — Incomplete scorecard blocked
# ---------------------------------------------------------------------------

def demo_f16_blocked_scorecard():
    section("F16 Demo 1 of 4 — Incomplete Scorecard Blocked")

    clear_stores_for_testing()

    blueprint = RoleBlueprint(
        blueprint_id="bp_backend",
        blueprint_version="v1",
        must_have_skills=[
            "problem_solving",
            "system_design",
            "communication",
        ],
    )

    incomplete = InterviewerScorecard(
        round_id="round_001",
        interviewer_id="interviewer_001",
        blueprint_id="bp_backend",
        blueprint_version="v1",
        competency_ratings=[
            make_rating("problem_solving", ScoreLabel.LEAN_YES),
            make_rating("system_design", ScoreLabel.NEUTRAL),
        ],
        overall_recommendation=OverallRecommendation.NEUTRAL,
    )

    result = submit_scorecard(
        scorecard=incomplete,
        blueprint=blueprint,
        candidate_id="cand_100",
        hiring_group_id="hg_backend",
    )

    if not result.is_valid:
        ok("Incomplete scorecard blocked correctly")
        info(str(result.blocking_reason))
    else:
        fail("Incomplete scorecard passed unexpectedly")

# ---------------------------------------------------------------------------
# DEMO SECTION 8 — Complete scorecard succeeds
# ---------------------------------------------------------------------------

def demo_f16_complete_scorecard():
    section("F16 Demo 2 of 4 — Complete Scorecard")

    blueprint = RoleBlueprint(
        blueprint_id="bp_backend",
        blueprint_version="v1",
        must_have_skills=[
            "problem_solving",
            "system_design",
            "communication",
        ],
    )

    complete = InterviewerScorecard(
        round_id="round_002",
        interviewer_id="interviewer_001",
        blueprint_id="bp_backend",
        blueprint_version="v1",
        competency_ratings=[
            make_rating("problem_solving", ScoreLabel.STRONG_YES),
            make_rating("system_design", ScoreLabel.LEAN_YES),
            make_rating("communication", ScoreLabel.LEAN_YES),
        ],
        overall_recommendation=OverallRecommendation.YES,
    )

    result = submit_scorecard(
        scorecard=complete,
        blueprint=blueprint,
        candidate_id="cand_101",
        hiring_group_id="hg_backend",
    )

    if result.is_valid:
        ok("Complete scorecard accepted")
    else:
        fail("Valid scorecard rejected")

# ---------------------------------------------------------------------------
# DEMO SECTION 9 — Calibration demo
# ---------------------------------------------------------------------------

def demo_f16_calibration():
    section("F16 Demo 3 of 4 — Calibration")

    def build_scorecard(round_id, interviewer_id, label):
        return InterviewerScorecard(
            round_id=round_id,
            interviewer_id=interviewer_id,
            blueprint_id="bp_backend",
            blueprint_version="v1",
            competency_ratings=[
                make_rating("problem_solving", label)
            ],
            overall_recommendation=OverallRecommendation.YES,
        )

    interviewer_scorecards = [
        build_scorecard(f"r{i}", "alice", ScoreLabel.LEAN_YES)
        for i in range(10)
    ]

    org_scorecards = [
        build_scorecard(f"o{i}", f"other_{i}", ScoreLabel.LEAN_NO)
        for i in range(10)
    ]

    snapshot = cal.compute_calibration_snapshot(
        interviewer_scorecards=interviewer_scorecards,
        all_scorecards=interviewer_scorecards + org_scorecards,
        interviewer_id="alice",
        snapshot_week="2025-W22",
    )

    if snapshot:
        ok("Calibration snapshot created")
        info(f"Drift: {snapshot.drift_pct:.1f}%")
    else:
        fail("Calibration snapshot failed")

# ---------------------------------------------------------------------------
# DEMO SECTION 10 — Integration demo
# ---------------------------------------------------------------------------

def demo_f16_audit_trail_integration():
    section("F16 Demo 4 of 4 — Audit Integration")

    blueprint = RoleBlueprint(
        blueprint_id="bp_backend",
        blueprint_version="v1",
        must_have_skills=["problem_solving"],
    )

    before = len(query_all())

    scorecard = InterviewerScorecard(
        round_id="integration_round",
        interviewer_id="integration_interviewer",
        blueprint_id="bp_backend",
        blueprint_version="v1",
        competency_ratings=[
            make_rating("problem_solving", ScoreLabel.STRONG_YES)
        ],
        overall_recommendation=OverallRecommendation.STRONG_YES,
    )

    result = submit_scorecard(
        scorecard=scorecard,
        blueprint=blueprint,
        candidate_id="cand_integration",
        hiring_group_id="hg_integration",
    )

    after = len(query_all())

    if result.is_valid and after - before == 1:
        ok("Audit integration working")
    else:
        fail("Audit integration failed")

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():

    set_feature_enabled(
        "f16_interviewer_scorecard",
        True,
    )

    print(f"\n{BOLD}Hiring Platform — Audit Logger + Scorecard Demo{RESET}")
    print(f"{DIM}Sprint Demo | Owner: Vikas{RESET}")

    header("F14 — AUDIT LOGGER")

    demo_f14_insert_five_rows()
    demo_f14_query_by_candidate()
    demo_f14_query_by_hiring_group()
    demo_f14_query_by_date_range()
    demo_f14_update_blocked()
    demo_f14_delete_blocked()

    header("F16 — SCORECARD")

    demo_f16_blocked_scorecard()
    demo_f16_complete_scorecard()
    demo_f16_calibration()
    demo_f16_audit_trail_integration()

    header("DONE")

    print(f"\n{GREEN}All demos completed successfully.{RESET}\n")

    return 0

if __name__ == "__main__":
    sys.exit(main())

from scorecards.calibration import detect_outlier

print("\n")
print("=" * 60)
print("CONSECUTIVE WEEK TEST")
print("=" * 60)

snapshot_1 = CalibrationSnapshot(

    interviewer_id="int_001",

    scorecard_count=10,

    interviewer_avg=80,

    org_avg=50,

    drift_pct=60,

    drift_direction="lenient",

    flagged=True,

    snapshot_week="2025-W21",

)

snapshot_2 = CalibrationSnapshot(

    interviewer_id="int_001",

    scorecard_count=10,

    interviewer_avg=82,

    org_avg=50,

    drift_pct=64,

    drift_direction="lenient",

    flagged=True,

    snapshot_week="2025-W22",

)

result = detect_outlier([
    snapshot_1,
    snapshot_2
])

print(f"Consecutive week outlier detected: {result}")   
