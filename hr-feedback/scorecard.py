"""
Compatibility adapter for the F16 scorecard submission endpoint.

This module intentionally avoids framework dependencies. It preserves
scorecards.submission.submit_scorecard() as the source of truth and only maps
the endpoint-shaped call to a response-shaped object.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from scorecards.schema import InterviewerScorecard, RoleBlueprint
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
        body=result.model_dump(),
    )

