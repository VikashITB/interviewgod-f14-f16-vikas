"""
F16 — Scorecard Schema (schema.py)
==================================
All Pydantic data models for the Interviewer Scorecard system.

ARCHITECTURAL ROLE
------------------
Single source of truth for scorecard data contracts.
Validator, submission, and calibration all import from here.

No business logic lives in this file.
Only data contracts and schema definitions.

SCORE DESIGN
------------
Interviewers choose a LABEL.
The system derives the NORMALIZED SCORE.

Label → Score mapping:
    STRONG_NO  → 10
    LEAN_NO    → 30
    NEUTRAL    → 55
    LEAN_YES   → 75
    STRONG_YES → 95
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from blueprints.models import (
    BlueprintCompetency,
    InterviewFeatures,
    RoleBlueprint,
    ValidationRules,
)


# ---------------------------------------------------------------------------
# Score labels
# ---------------------------------------------------------------------------

class ScoreLabel(str, Enum):

    STRONG_NO  = "STRONG_NO"
    LEAN_NO    = "LEAN_NO"
    NEUTRAL    = "NEUTRAL"
    LEAN_YES   = "LEAN_YES"
    STRONG_YES = "STRONG_YES"


# ---------------------------------------------------------------------------
# Label → normalized score mapping
# ---------------------------------------------------------------------------

SCORE_MAP: dict[ScoreLabel, int] = {

    ScoreLabel.STRONG_NO:  10,
    ScoreLabel.LEAN_NO:    30,
    ScoreLabel.NEUTRAL:    55,
    ScoreLabel.LEAN_YES:   75,
    ScoreLabel.STRONG_YES: 95,

}

SCHEMA_VERSION = "v1"

DEFAULT_SCORE_SCALE: dict[str, int] = {

    label.value: score

    for label, score
    in SCORE_MAP.items()

}


# ---------------------------------------------------------------------------
# Evidence entry
# ---------------------------------------------------------------------------

class EvidenceEntry(BaseModel):
    """
    Supporting evidence for a competency rating.
    """

    competency:    str

    evidence_text: str = Field(
        min_length=20
    )

    interview_ts: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Competency rating
# ---------------------------------------------------------------------------

class CompetencyRating(BaseModel):
    """
    Rating for one competency.
    """

    competency: str

    label: ScoreLabel

    normalized_score: int

    evidence: list[EvidenceEntry]

    dimension_scores: Optional[dict[str, float]] = None

    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Scorecard lifecycle
# ---------------------------------------------------------------------------

class ScorecardStatus(str, Enum):

    DRAFT     = "DRAFT"
    SUBMITTED = "SUBMITTED"
    BLOCKED   = "BLOCKED"


# ---------------------------------------------------------------------------
# Final recommendation
# ---------------------------------------------------------------------------

class OverallRecommendation(str, Enum):

    STRONG_NO  = "STRONG_NO"
    NO         = "NO"
    NEUTRAL    = "NEUTRAL"
    YES        = "YES"
    STRONG_YES = "STRONG_YES"


# ---------------------------------------------------------------------------
# Main scorecard
# ---------------------------------------------------------------------------

class InterviewerScorecard(BaseModel):
    """
    One interviewer scorecard for one interview round.
    """

    round_id: str

    interviewer_id: str

    blueprint_id: str

    blueprint_version: str

    competency_ratings: list[CompetencyRating]

    overall_recommendation: Optional[
        OverallRecommendation
    ] = None

    status: ScorecardStatus = ScorecardStatus.DRAFT

    submitted_at: Optional[datetime] = None


class EvaluationSchema(BaseModel):
    """
    Deterministic scorecard schema materialized from a blueprint contract.
    """

    blueprint_id: str

    blueprint_version: str

    competencies: list[BlueprintCompetency]

    score_scale: dict[str, int]

    validation_contract: ValidationRules

    interview_features: InterviewFeatures

    schema_version: str = SCHEMA_VERSION


def materialize_scorecard_schema(
    blueprint: RoleBlueprint,
) -> EvaluationSchema:
    """
    Materialize a deterministic scorecard schema from a blueprint contract.
    """

    competencies = list(
        blueprint.competencies
        or []
    )

    competency_ids = [
        competency.competency_id
        for competency
        in competencies
    ]

    duplicate_ids = sorted({
        competency_id
        for competency_id
        in competency_ids
        if competency_ids.count(competency_id) > 1
    })

    if duplicate_ids:

        raise ValueError(
            "Blueprint contains duplicate competency_id values: "
            f"{duplicate_ids}"
        )

    return EvaluationSchema(

        blueprint_id=blueprint.blueprint_id,

        blueprint_version=blueprint.blueprint_version,

        competencies=competencies,

        score_scale=dict(blueprint.score_scale),

        validation_contract=blueprint.validation_rules,

        interview_features=blueprint.interview_features,

        schema_version=SCHEMA_VERSION,

    )


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

class SubmissionValidationResult(BaseModel):
    """
    Output returned by validate_scorecard().
    """

    is_valid: bool

    missing_competencies: list[str] = Field(
        default_factory=list
    )

    missing_evidence: list[str] = Field(
        default_factory=list
    )

    validation_errors: list[str] = Field(
        default_factory=list
    )

    blocking_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Calibration snapshot
# ---------------------------------------------------------------------------

class CalibrationSnapshot(BaseModel):
    """
    Calibration snapshot for one interviewer.
    """

    interviewer_id: str

    scorecard_count: int

    interviewer_avg: float

    org_avg: float

    drift_pct: float

    drift_direction: str

    flagged: bool

    snapshot_week: Optional[str] = None
