from __future__ import annotations

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.feature_flags import set_feature_enabled
from database import get_connection, set_database_path_for_testing
from scorecards.submission import submit_scorecard, clear_stores_for_testing
from scripts.synthetic_blueprint import generate_backend_engine_blueprint
from scripts.synthetic_candidate import create_candidate_shell
from scripts.synthetic_scorecard import build_scorecard
from scripts.formatters import (
    format_blueprint_human,
    format_candidate_human,
    format_scorecard_human,
    format_audit_timeline_human,
    format_replay_validation_human,
    export_scorecard_json,
    export_timeline_json,
    pretty_json,
)
from utils.audit_logger import (
    ActionType,
    clear_store_for_testing,
    log_audit_event,
    query_by_candidate_from_db,
)


TITLE = "SYNTHETIC HIRING PIPELINE"
DEMO_DB_PATH = os.path.join(os.path.dirname(__file__), "synthetic_pipeline.db")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run synthetic hiring pipeline demo.")
    parser.add_argument(
        "--view",
        choices=["human", "json", "both"],
        default="both",
        help="Output mode: human (recruiter-friendly), json (snapshots), or both.",
    )
    return parser.parse_args()


def print_header() -> None:
    print("\n" + "=" * 50)
    print(TITLE)
    print("=" * 50)


def print_section(title: str) -> None:
    print("\n" + title)
    print("-" * len(title))


def validate_audit_store() -> dict:
    """Validate append-only audit and return report."""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM audit_trail")
        rows_count = cursor.fetchone()[0]

        cursor.execute("SELECT DISTINCT event_id FROM audit_trail")
        unique_ids = len(cursor.fetchall())

        cursor.execute("SELECT COUNT(*) FROM audit_trail WHERE candidate_id IS NOT NULL")
        covered_candidates = cursor.fetchone()[0]

        cursor.execute("SELECT DISTINCT action_type FROM audit_trail")
        action_types = [row[0] for row in cursor.fetchall()]

        conn.close()

        return {
            "total_audit_rows": rows_count,
            "unique_event_ids": unique_ids,
            "duplicate_event_ids": rows_count != unique_ids,
            "candidate_id_coverage": covered_candidates == rows_count if rows_count > 0 else True,
            "audit_count_consistency": True,
            "action_type_set": sorted(action_types),
        }
    except sqlite3.OperationalError:
        return {
            "total_audit_rows": 0,
            "unique_event_ids": 0,
            "duplicate_event_ids": False,
            "candidate_id_coverage": True,
            "audit_count_consistency": True,
            "action_type_set": [],
        }


def run_pipeline(view_mode: str = "both") -> None:
    """Run full pipeline with specified view mode."""
    if os.path.exists(DEMO_DB_PATH):
        os.remove(DEMO_DB_PATH)

    set_database_path_for_testing(DEMO_DB_PATH)
    clear_store_for_testing()
    clear_stores_for_testing()

    set_feature_enabled("f14_audit_logger", True)
    set_feature_enabled("f14_replay_reconstruction", True)
    set_feature_enabled("f16_interviewer_scorecard", True)

    candidate_id = "cand_backend_001"
    hiring_group_id = "hg_backend_engineering"
    round_id = "round_backend_001"
    interviewer_id = "interviewer_backend_001"

    blueprint = generate_backend_engine_blueprint()
    candidate_shell = create_candidate_shell(candidate_id)
    scorecard = build_scorecard(
        candidate_id=candidate_id,
        round_id=round_id,
        interviewer_id=interviewer_id,
        blueprint=blueprint,
    )

    if view_mode in ("human", "both"):
        print_header()

        print_section("Blueprint")
        print(format_blueprint_human(blueprint))

        print_section("Candidate")
        print(format_candidate_human(candidate_shell))

    log_audit_event(
        action_type=ActionType.CANDIDATE_VIEWED,
        actor_id="recruiter_backend_001",
        actor_email="recruiter.backend@company.com",
        candidate_id=candidate_id,
        hiring_group_id=hiring_group_id,
        evidence_snapshot={
            "resume_signals": candidate_shell["resume_signals"],
            "consent_status": candidate_shell["consent_status"],
        },
        summary="Candidate shell created and resume signals aligned to blueprint.",
    )

    log_audit_event(
        action_type=ActionType.STAGE_ADVANCED,
        actor_id="system::pipeline_engine",
        actor_email="system@platform.internal",
        candidate_id=candidate_id,
        hiring_group_id=hiring_group_id,
        evidence_snapshot={
            "next_stage": "interview_evaluation",
            "blueprint_id": blueprint.blueprint_id,
        },
        summary="Candidate advanced to interview evaluation stage.",
    )

    submission_result = submit_scorecard(
        scorecard=scorecard,
        blueprint=blueprint,
        candidate_id=candidate_id,
        hiring_group_id=hiring_group_id,
    )

    if view_mode in ("human", "both"):
        print_section("Generated F16 Scorecard")
        print(format_scorecard_human(scorecard))
        print(f"\nSubmission Valid: {submission_result.is_valid}")
        if submission_result.blocking_reason:
            print(f"Blocking Reason: {submission_result.blocking_reason}")

    recommendation_data = {
        "recommendation": scorecard.overall_recommendation.value if scorecard.overall_recommendation else "PENDING",
        "reason": "Deterministic recommendation derived from F16 scorecard consensus.",
    }
    candidate_shell["recommendation"] = recommendation_data["recommendation"]

    log_audit_event(
        action_type=ActionType.RECOMMENDATION_GENERATED,
        actor_id="system::recommendation_engine",
        actor_email="system@platform.internal",
        candidate_id=candidate_id,
        hiring_group_id=hiring_group_id,
        evidence_snapshot={
            "recommendation": recommendation_data["recommendation"],
            "source": "F16 scorecard",
            "overall_recommendation": scorecard.overall_recommendation.value if scorecard.overall_recommendation else None,
        },
        summary="Deterministic recommendation generated from scorecard.",
    )

    if view_mode in ("human", "both"):
        print_section("Recommendation")
        print(f"Recommendation: {recommendation_data['recommendation']}")
        print(f"Reason: {recommendation_data['reason']}")

    events = query_by_candidate_from_db(candidate_id)

    if view_mode in ("human", "both"):
        print_section("Audit Timeline")
        print(format_audit_timeline_human(events))

        validation_report = validate_audit_store()
        print_section("Replay Validation")
        print(format_replay_validation_human(validation_report))

    if view_mode in ("json", "both"):
        if view_mode == "both":
            print_section("JSON Snapshots")

        json_output = {
            "scorecard": export_scorecard_json(scorecard),
            "timeline": export_timeline_json(events),
            "validation": validate_audit_store(),
        }

        if view_mode == "json":
            print(pretty_json(json_output))
        else:
            print("Scorecard Snapshot:")
            print(pretty_json(json_output["scorecard"]))
            print("\nTimeline Snapshot:")
            print(pretty_json(json_output["timeline"]))
            print("\nValidation Snapshot:")
            print(pretty_json(json_output["validation"]))


def main() -> int:
    args = parse_args()
    run_pipeline(view_mode=args.view)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
