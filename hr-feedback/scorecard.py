"""
Compatibility adapter for the F16 scorecard submission endpoint.

This module intentionally avoids framework dependencies. It preserves
scorecards.submission.submit_scorecard() as the source of truth and only maps
the endpoint-shaped call to a response-shaped object.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from blueprints.models import BlueprintCompetency
from config.feature_flags import is_feature_enabled
from scorecards.schema import (
    CompetencyRating,
    EvidenceEntry,
    InterviewerScorecard,
    OverallRecommendation,
    RoleBlueprint,
    SCORE_MAP,
    ScoreLabel,
)
from scorecards.submission import submit_scorecard


POST_SCORECARD_ROUTE = "/interview/{round_id}/scorecard"


@dataclass(frozen=True)
class ScorecardResponse:
    status_code: int
    body: dict[str, Any]


def post_interview_scorecard(
    round_id: str,
    scorecard: InterviewerScorecard,
    blueprint: RoleBlueprint,
    candidate_id: Optional[str] = None,
    hiring_group_id: Optional[str] = None,
) -> ScorecardResponse:
    """
    Handle POST /interview/{round_id}/scorecard compatibility behavior.
    """

    if scorecard.round_id != round_id:
        return ScorecardResponse(
            status_code=400,
            body={
                "is_valid": False,
                "blocking_reason": (
                    "scorecard round_id does not match request path round_id."
                ),
                "validation_errors": [
                    (
                        f"scorecard round_id '{scorecard.round_id}' does not "
                        f"match path round_id '{round_id}'."
                    )
                ],
            },
        )

    result = submit_scorecard(
        scorecard=scorecard,
        blueprint=blueprint,
        candidate_id=candidate_id,
        hiring_group_id=hiring_group_id,
    )

    if not result.is_valid:
        return ScorecardResponse(
            status_code=400,
            body=result.model_dump(),
        )

    return ScorecardResponse(
        status_code=201,
        body={
            **result.model_dump(),
            "status": "submitted",
            "ref_id": f"{scorecard.round_id}:{scorecard.interviewer_id}",
            "round_id": scorecard.round_id,
            "interviewer": scorecard.interviewer_id,
        },
    )


def handle_scorecard_submission(round_id: str, payload: dict) -> tuple[int, dict]:
    """
    Payload-shaped compatibility entry point for POST /interview/{round_id}/scorecard.
    """

    if not is_feature_enabled("f16_interviewer_scorecard"):
        return 404, {
            "error": "Feature not available",
        }

    blueprint_data = payload.get("blueprint")

    if not blueprint_data:
        return 400, {
            "error": "blueprint is required",
        }

    try:
        blueprint = _build_blueprint(blueprint_data)
        scorecard = _build_scorecard(
            round_id=round_id,
            payload=payload,
            blueprint=blueprint,
        )
    except (KeyError, TypeError, ValueError) as exc:
        return 400, {
            "error": str(exc),
        }

    result = submit_scorecard(
        scorecard=scorecard,
        blueprint=blueprint,
        candidate_id=payload.get("candidate_id"),
        hiring_group_id=payload.get("hiring_group_id"),
    )

    if result.is_valid:
        return 201, {
            "status": "submitted",
            "ref_id": f"{scorecard.round_id}:{scorecard.interviewer_id}",
            "round_id": scorecard.round_id,
            "interviewer": scorecard.interviewer_id,
        }

    body = {
        "error": "Incomplete scorecard",
    }

    if result.missing_competencies:
        body["missing_competencies"] = result.missing_competencies

    if result.missing_evidence:
        body["error"] = "Evidence required"
        body["missing_evidence"] = result.missing_evidence

    if (
        result.validation_errors
        and not result.missing_competencies
        and not result.missing_evidence
    ):
        body["error"] = result.validation_errors[0]

    return 400, body


def _build_blueprint(blueprint_data: dict) -> RoleBlueprint:
    competencies = [
        BlueprintCompetency(
            competency_id=competency["competency_id"],
            required=competency.get("required", True),
            weight=competency.get("weight", 1.0),
            evidence_required=competency.get("evidence_required", True),
        )
        for competency
        in blueprint_data.get("competencies", [])
    ]

    return RoleBlueprint(
        blueprint_id=blueprint_data["blueprint_id"],
        blueprint_version=blueprint_data["blueprint_version"],
        competencies=competencies,
    )


def _build_scorecard(
    round_id: str,
    payload: dict,
    blueprint: RoleBlueprint,
) -> InterviewerScorecard:
    ratings = [
        _build_rating(rating)
        for rating
        in payload.get("competency_ratings", [])
    ]

    recommendation = payload.get(
        "overall_recommendation",
        "YES",
    )

    return InterviewerScorecard(
        round_id=round_id,
        candidate_id=payload.get("candidate_id"),
        interviewer_id=payload.get("interviewer_id", "unknown"),
        blueprint_id=blueprint.blueprint_id,
        blueprint_version=blueprint.blueprint_version,
        competency_ratings=ratings,
        overall_recommendation=OverallRecommendation(recommendation),
        notes=payload.get("notes"),
    )


def _build_rating(rating: dict) -> CompetencyRating:
    label = ScoreLabel(
        rating.get("label")
        or _int_to_label(
            rating.get("rating", 3)
        )
    )

    evidence = []

    if rating.get("evidence_text"):
        evidence = [
            EvidenceEntry(
                competency=rating["competency"],
                evidence_text=rating["evidence_text"],
            )
        ]

    return CompetencyRating(
        competency=rating["competency"],
        label=label,
        normalized_score=SCORE_MAP[label],
        evidence=evidence,
        category=rating.get("category"),
    )


def _int_to_label(rating: int) -> str:
    mapping = {
        1: "STRONG_NO",
        2: "LEAN_NO",
        3: "NEUTRAL",
        4: "LEAN_YES",
        5: "STRONG_YES",
    }

    return mapping.get(
        rating,
        "NEUTRAL",
    )
