"""
Recruiter-friendly formatting helpers for synthetic pipeline output.

Converts internal models and audit events into clean, human-readable terminal
output and deterministic JSON snapshots.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from blueprints.models import RoleBlueprint
from scorecards.schema import InterviewerScorecard, CompetencyRating
from utils.audit_logger import AuditEvent


def format_blueprint_human(blueprint: RoleBlueprint) -> str:
    """
    Human-readable blueprint summary (no raw dicts/enums).
    """
    lines = [
        "Blueprint Details",
        "-" * 40,
        f"ID: {blueprint.blueprint_id}",
        f"Version: {blueprint.blueprint_version}",
        f"Competencies: {len(blueprint.competencies or [])}",
    ]

    if blueprint.competencies:
        for comp in blueprint.competencies:
            req = "REQUIRED" if comp.required else "OPTIONAL"
            lines.append(f"  - {comp.competency_id:<20} {req:<10} weight={comp.weight}")

    return "\n".join(lines)


def format_candidate_human(candidate_shell: dict[str, Any]) -> str:
    """
    Human-readable candidate shell (no raw dicts).
    """
    lines = [
        "Candidate Shell",
        "-" * 40,
        f"ID: {candidate_shell['candidate_id']}",
        f"Consent: {candidate_shell['consent_status']}",
        f"Blueprint: {candidate_shell['blueprint_alignment']['blueprint_id']}",
        "",
        "Resume Signals:",
    ]

    for signal in candidate_shell.get("resume_signals", []):
        competency = signal["competency"]
        found = "FOUND" if signal.get("found") else "NOT FOUND"
        years = signal.get("years", 0)
        score = signal.get("signal_score", 0)
        lines.append(
            f"  - {competency:<20} {found:<12} {years} yrs  score={score}"
        )

    return "\n".join(lines)


def format_scorecard_human(scorecard: InterviewerScorecard) -> str:
    """
    Human-readable scorecard with clean competency ratings (no raw enums).
    """
    lines = [
        "F16 Scorecard",
        "-" * 40,
        f"Round: {scorecard.round_id}",
        f"Interviewer: {scorecard.interviewer_id}",
        f"Candidate: {scorecard.candidate_id}",
        f"Recommendation: {scorecard.overall_recommendation.value if scorecard.overall_recommendation else 'PENDING'}",
        "",
        "Competency Ratings:",
    ]

    for rating in scorecard.competency_ratings:
        label = rating.label.value if hasattr(rating.label, "value") else str(rating.label)
        score = rating.normalized_score
        evidence_count = len(rating.evidence) if rating.evidence else 0
        lines.append(
            f"  - {rating.competency:<20} {label:<12} ({score:>3})  evidence={evidence_count}"
        )

    if scorecard.notes:
        lines.append(f"\nNotes: {scorecard.notes}")

    return "\n".join(lines)


def format_audit_timeline_human(events: list[AuditEvent]) -> str:
    """
    Human-readable audit timeline (clean timestamps and action types).
    """
    lines = [
        "Audit Timeline",
        "-" * 40,
        f"Total Events: {len(events)}",
        "",
    ]

    for index, event in enumerate(events, start=1):
        action = event.action_type.value
        stage = event.pipeline_stage.value if event.pipeline_stage else "UNKNOWN"
        timestamp = event.created_at.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"{index}. {action:<25} | {stage:<20} | {timestamp}")
        if event.summary:
            lines.append(f"   -> {event.summary}")

    return "\n".join(lines)


def format_replay_validation_human(report: dict[str, Any]) -> str:
    """
    Human-readable replay validation report.
    """
    lines = [
        "Replay Validation",
        "-" * 40,
        f"Audit Rows: {report.get('total_audit_rows', 0)}",
        f"Unique Event IDs: {report.get('unique_event_ids', 0)}",
        f"Duplicates Detected: {'YES' if report.get('duplicate_event_ids') else 'NO'}",
        f"Candidate Coverage: {'YES' if report.get('candidate_id_coverage') else 'NO'}",
        f"Count Consistency: {'YES' if report.get('audit_count_consistency') else 'NO'}",
    ]

    action_types = report.get("action_type_set", [])
    if action_types:
        lines.append(f"Action Types: {', '.join(sorted(action_types))}")

    return "\n".join(lines)


def export_scorecard_json(scorecard: InterviewerScorecard) -> dict[str, Any]:
    """
    Export scorecard as deterministic JSON-serializable dict (no enums).
    """
    return {
        "round_id": scorecard.round_id,
        "interviewer_id": scorecard.interviewer_id,
        "blueprint_id": scorecard.blueprint_id,
        "blueprint_version": scorecard.blueprint_version,
        "candidate_id": scorecard.candidate_id,
        "overall_recommendation": (
            scorecard.overall_recommendation.value
            if scorecard.overall_recommendation
            else None
        ),
        "status": scorecard.status.value if scorecard.status else None,
        "submitted_at": (
            scorecard.submitted_at.isoformat() if scorecard.submitted_at else None
        ),
        "competency_ratings": [
            {
                "competency": rating.competency,
                "label": rating.label.value if hasattr(rating.label, "value") else str(rating.label),
                "normalized_score": rating.normalized_score,
                "evidence_count": len(rating.evidence) if rating.evidence else 0,
                "evidence": [
                    {
                        "competency": ev.competency,
                        "evidence_text": ev.evidence_text,
                        "interview_ts": (
                            ev.interview_ts.isoformat() if ev.interview_ts else None
                        ),
                    }
                    for ev in (rating.evidence or [])
                ],
            }
            for rating in scorecard.competency_ratings
        ],
        "notes": scorecard.notes,
    }


def export_timeline_json(events: list[AuditEvent]) -> list[dict[str, Any]]:
    """
    Export audit timeline as deterministic JSON-serializable list (no enums).
    """
    return [
        {
            "event_id": event.event_id,
            "created_at": event.created_at.isoformat(),
            "action_type": event.action_type.value,
            "pipeline_stage": event.pipeline_stage.value if event.pipeline_stage else None,
            "candidate_id": event.candidate_id,
            "round_id": event.round_id,
            "hiring_group_id": event.hiring_group_id,
            "actor_id": event.actor_id,
            "actor_email": event.actor_email,
            "summary": event.summary,
            "evidence_snapshot": event.evidence_snapshot,
        }
        for event in events
    ]


def pretty_json(data: Any, indent: int = 2) -> str:
    """
    Deterministic pretty JSON output (no raw enums/datetime).
    """
    return json.dumps(data, indent=indent, sort_keys=True)
