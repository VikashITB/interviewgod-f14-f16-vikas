"""
Deterministic blueprint contract models.

This module owns the lightweight Week 1 evaluation contract. It contains no ORM
logic, no framework dependency, and no runtime schema inference.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


DEFAULT_SCORE_SCALE: dict[str, int] = {
    "STRONG_NO": 10,
    "LEAN_NO": 30,
    "NEUTRAL": 55,
    "LEAN_YES": 75,
    "STRONG_YES": 95,
}


@dataclass
class BlueprintCompetency:
    """
    One competency defined by a versioned blueprint contract.
    """

    competency_id: str
    required: bool = True
    weight: float = 1.0
    evidence_required: bool = True
    knockout_candidate: bool = False

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass
class ValidationRules:
    """
    Validation behavior owned by the blueprint contract.
    """

    all_required_competencies_must_be_rated: bool = True
    evidence_required_per_competency: bool = True
    overall_recommendation_required: bool = True

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass
class InterviewFeatures:
    """
    Interview feature switches recorded as part of the blueprint contract.
    """

    evidence_required: bool = True
    calibration_enabled: bool = True
    knockout_enabled: bool = True
    integrity_checks_enabled: bool = True

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass
class RoleBlueprint:
    """
    Source-of-truth contract for deterministic evaluation schema generation.
    """

    blueprint_id: str
    blueprint_version: str
    competencies: list[BlueprintCompetency] | None = None
    validation_rules: ValidationRules = field(
        default_factory=ValidationRules
    )
    score_scale: dict[str, int] = field(
        default_factory=lambda: dict(DEFAULT_SCORE_SCALE)
    )
    interview_features: InterviewFeatures = field(
        default_factory=InterviewFeatures
    )
    must_have_skills: list[str] = field(
        default_factory=list
    )
    dimension_weights: dict[str, float] | None = None

    def model_dump(self) -> dict:
        return asdict(self)

    def __post_init__(self) -> None:
        """
        Preserve Week 1 callers while making competencies explicit.
        """

        if self.competencies:
            if not self.must_have_skills:
                self.must_have_skills = [
                    competency.competency_id
                    for competency
                    in self.competencies
                    if competency.required
                ]
            return

        self.competencies = [
            BlueprintCompetency(
                competency_id=skill,
                required=True,
                weight=(
                    self.dimension_weights.get(skill, 1.0)
                    if self.dimension_weights
                    else 1.0
                ),
                evidence_required=True,
                knockout_candidate=False,
            )
            for skill
            in self.must_have_skills
        ]
