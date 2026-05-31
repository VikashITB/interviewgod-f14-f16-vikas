import argparse
import os
import sys
from typing import Any

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from utils.audit_logger import (
    query_by_candidate_from_db,
)

LEGACY_STAGE_FALLBACK = "UNKNOWN_LEGACY_STAGE"
SUMMARY_FALLBACK = "No summary provided"
LEGACY_EVIDENCE_FALLBACK_LINES = [
    "Legacy or minimal audit event detected.",
    "This event has no rich evidence snapshot to replay.",
    "Replay metadata unavailable for this event generation.",
]
DEFAULT_CANDIDATE_ID = "cand_001"
DEFAULT_RENDER_LIMIT = 10

PIPELINE_STAGE_ORDER = {
    "RESUME_SCREENING": 10,
    "KNOCKOUT_CHECK": 20,
    "CALL_SCREENING": 30,
    "INTERVIEW_INTEGRITY": 40,
    "RECOMMENDATION": 50,
    "HR_OVERRIDE": 60,
    "FINAL_DECISION": 70,
    LEGACY_STAGE_FALLBACK: 999,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reconstruct a recruiter-readable candidate audit timeline."
    )

    parser.add_argument(
        "--candidate-id",
        default=DEFAULT_CANDIDATE_ID,
        help=f"Candidate id to reconstruct. Default: {DEFAULT_CANDIDATE_ID}",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_RENDER_LIMIT,
        help=f"Show latest N events. Default: {DEFAULT_RENDER_LIMIT}",
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Render all persisted events for the candidate.",
    )

    parser.add_argument(
        "--latest-only",
        action="store_true",
        help="Render only the latest persisted event for the candidate.",
    )

    parser.add_argument(
        "--latest-semantic-event",
        action="store_true",
        help=(
            "Render only the latest event that contains a replayable "
            "evidence snapshot."
        ),
    )

    parser.add_argument(
        "--dedupe-action",
        action="store_true",
        help="Render only the latest event per action type.",
    )

    parser.add_argument(
        "--stage-order",
        action="store_true",
        help="Render by logical pipeline stage, then timestamp.",
    )

    return parser.parse_args()


def stage_value(event) -> str:
    if event.pipeline_stage:
        return event.pipeline_stage.value

    return LEGACY_STAGE_FALLBACK


def action_value(event) -> str:
    if event.action_type:
        return event.action_type.value

    return "UNKNOWN_ACTION"


def summary_value(event) -> str:
    return event.summary or SUMMARY_FALLBACK


def has_replayable_evidence(event) -> bool:
    return bool(event.evidence_snapshot)


def apply_render_filters(events: list, args: argparse.Namespace) -> list:
    filtered_events = list(events)

    if args.latest_semantic_event:
        semantic_events = [
            event
            for event
            in filtered_events
            if has_replayable_evidence(event)
        ]

        if not semantic_events:
            return []

        return [
            max(
                semantic_events,
                key=lambda event: event.created_at,
            )
        ]

    if args.dedupe_action:
        latest_by_action = {}

        for event in filtered_events:
            action = action_value(event)
            current_latest = latest_by_action.get(action)

            if (
                current_latest is None
                or event.created_at > current_latest.created_at
            ):
                latest_by_action[action] = event

        filtered_events = sorted(
            latest_by_action.values(),
            key=lambda event: event.created_at,
        )

    if args.latest_only:
        if not filtered_events:
            return []

        return [
            max(
                filtered_events,
                key=lambda event: event.created_at,
            )
        ]

    if args.stage_order:
        filtered_events.sort(
            key=lambda event: (
                PIPELINE_STAGE_ORDER.get(
                    stage_value(event),
                    PIPELINE_STAGE_ORDER[LEGACY_STAGE_FALLBACK],
                ),
                event.created_at,
            )
        )

    if args.all:
        return filtered_events

    if args.limit <= 0:
        return filtered_events

    return filtered_events[-args.limit:]


def replay_mode(args: argparse.Namespace) -> str:
    modes = []

    if args.latest_only:
        modes.append("latest-only")
    elif args.latest_semantic_event:
        modes.append("latest-semantic-event")
    elif args.all:
        modes.append("all-events")
    elif args.limit > 0:
        modes.append(f"latest-{args.limit}")
    else:
        modes.append("all-events")

    if args.dedupe_action:
        modes.append("dedupe-action")

    if args.stage_order:
        modes.append("stage-order")

    return " + ".join(modes)


def print_evidence_value(
    key: str,
    value: Any,
    indent: int = 2,
) -> None:
    prefix = " " * indent

    if isinstance(value, dict):
        print(f"{prefix}{key:<25}:")

        for nested_key, nested_value in value.items():
            print_evidence_value(
                str(nested_key),
                nested_value,
                indent + 2,
            )

        return

    print(f"{prefix}{key:<25}: {value}")


def print_timeline(
    candidate_id: str,
    events: list,
    rendered_events: list,
    mode: str,
) -> None:
    print("\n")
    print("=" * 80)
    print("CANDIDATE TIMELINE RECONSTRUCTION")
    print("=" * 80)

    print(f"\nCandidate ID : {candidate_id}")
    print(f"Replay mode : {mode}")
    print(f"Persisted events found : {len(events)}")
    print(f"Rendered events shown  : {len(rendered_events)}")

    print("\n")
    print("=" * 80)
    print("PIPELINE HISTORY")
    print("=" * 80)

    if not rendered_events:
        print("\nNo audit events found for this candidate.")

    for index, event in enumerate(rendered_events, start=1):
        print(f"\nStage #{index}")
        print("-" * 80)
        print(f"ACTION TYPE     : {action_value(event)}")
        print(f"PIPELINE STAGE  : {stage_value(event)}")
        print(f"TIMESTAMP       : {event.created_at}")
        print(f"HIRING GROUP    : {event.hiring_group_id or 'N/A'}")
        print(f"ACTOR EMAIL     : {event.actor_email or 'N/A'}")
        print(f"SUMMARY         : {summary_value(event)}")

        print("\nEVIDENCE SNAPSHOT")

        evidence_snapshot = event.evidence_snapshot or {}

        if not evidence_snapshot:
            for line in LEGACY_EVIDENCE_FALLBACK_LINES:
                print(f"  {line}")
            continue

        for key, value in evidence_snapshot.items():
            print_evidence_value(
                str(key),
                value,
            )

    print("\n")
    print("=" * 80)
    print("Timeline reconstruction completed successfully.")
    print("=" * 80)


def main() -> int:
    args = parse_args()

    events = query_by_candidate_from_db(
        args.candidate_id
    )

    rendered_events = apply_render_filters(
        events,
        args,
    )

    print_timeline(
        candidate_id=args.candidate_id,
        events=events,
        rendered_events=rendered_events,
        mode=replay_mode(args),
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
