"""
F16 — Scorecard Validator (validator.py)
========================================
Pure validation logic.

No DB writes.
No audit logging.
No side effects.

ARCHITECTURAL ROLE
------------------
validate_scorecard() is a pure function:

    (scorecard, blueprint)
            →
    SubmissionValidationResult

Nothing is persisted until submission.py confirms:
    is_valid == True

VALIDATION STAGES
-----------------
1. Required competency coverage
2. Evidence presence
3. Score normalization consistency
4. Overall recommendation presence
"""

from __future__ import annotations

from scorecards.schema import (

    EvaluationSchema,
    InterviewerScorecard,
    RoleBlueprint,
    SubmissionValidationResult,
    materialize_scorecard_schema,

)


def validate_scorecard(
    scorecard: InterviewerScorecard,
    contract: RoleBlueprint | EvaluationSchema,
) -> SubmissionValidationResult:

    """
    Run validation against a materialized schema contract.

    Returns:
        SubmissionValidationResult
    """

    schema = (
        materialize_scorecard_schema(contract)
        if isinstance(contract, RoleBlueprint)
        else contract
    )

    missing_competencies: list[str] = []

    missing_evidence: list[str] = []

    validation_errors: list[str] = []

    # -----------------------------------------------------------------------
    # Build lookup
    # -----------------------------------------------------------------------

    seen_competencies: dict[str, object] = {}

    for rating in scorecard.competency_ratings:

        competency_key = (
            rating.competency.strip().lower()
            if isinstance(rating.competency, str)
            else str(rating.competency)
        )

        if competency_key in seen_competencies:

            validation_errors.append(
                f"Duplicate rating for competency: '{rating.competency}'"
            )

        else:

            seen_competencies[competency_key] = rating

    competency_contracts = {

        competency.competency_id: competency

        for competency
        in schema.competencies

    }

    contract_competency_ids = set(
        competency_contracts.keys()
    )

    if scorecard.blueprint_id != schema.blueprint_id:

        validation_errors.append(
            "scorecard blueprint_id "
            f"'{scorecard.blueprint_id}' does not match "
            f"schema blueprint_id '{schema.blueprint_id}'."
        )

    if scorecard.blueprint_version != schema.blueprint_version:

        validation_errors.append(
            "scorecard blueprint_version "
            f"'{scorecard.blueprint_version}' does not match "
            f"schema blueprint_version '{schema.blueprint_version}'."
        )

    # -----------------------------------------------------------------------
    # Stage 1 — Required competency coverage
    # -----------------------------------------------------------------------

    if (
        schema
        .validation_contract
        .all_required_competencies_must_be_rated
    ):

        for competency in schema.competencies:

            if (
                competency.required
                and competency.competency_id
                not in seen_competencies
            ):

                missing_competencies.append(
                    competency.competency_id
                )

    for rating in scorecard.competency_ratings:

        if rating.competency not in contract_competency_ids:

            validation_errors.append(
                f"Competency '{rating.competency}' "
                "is not defined by the schema contract."
            )

    # -----------------------------------------------------------------------
    # Stage 2 — Evidence presence
    # -----------------------------------------------------------------------

    if (
        schema.interview_features.evidence_required
        and schema.validation_contract.evidence_required_per_competency
    ):

        for rating in scorecard.competency_ratings:

            competency_contract = competency_contracts.get(
                rating.competency
            )

            if (
                competency_contract
                and competency_contract.evidence_required
                and not rating.evidence
            ):

                missing_evidence.append(
                    rating.competency
                )

    # -----------------------------------------------------------------------
    # Stage 3 — Score normalization consistency
    # -----------------------------------------------------------------------

    for rating in scorecard.competency_ratings:

        expected_score = schema.score_scale.get(
            rating.label.value
        )

        if expected_score is None:

            validation_errors.append(
                f"Label {rating.label.value} is not defined "
                "by the schema score_scale."
            )

            continue

        if rating.normalized_score != expected_score:

            validation_errors.append(

                f"Competency '{rating.competency}': "
                f"normalized_score is "
                f"{rating.normalized_score} "
                f"but label {rating.label.value} "
                f"requires {expected_score}."

            )

    # -----------------------------------------------------------------------
    # Stage 4 — Overall recommendation required
    # -----------------------------------------------------------------------

    if (
        schema
        .validation_contract
        .overall_recommendation_required
        and scorecard.overall_recommendation is None
    ):

        validation_errors.append(

            "overall_recommendation is required before submission."

        )

    # -----------------------------------------------------------------------
    # Stage 5 - Knockout contract consistency
    # -----------------------------------------------------------------------

    if schema.interview_features.knockout_enabled:

        for rating in scorecard.competency_ratings:

            competency_contract = competency_contracts.get(
                rating.competency
            )

            if (
                competency_contract
                and competency_contract.knockout_candidate
                and rating.label.value == "STRONG_NO"
                and not rating.evidence
            ):

                validation_errors.append(
                    f"Knockout competency '{rating.competency}' "
                    "requires evidence when rated STRONG_NO."
                )

    # -----------------------------------------------------------------------
    # Final validation result
    # -----------------------------------------------------------------------

    is_valid = (

        not missing_competencies
        and not missing_evidence
        and not validation_errors

    )

    blocking_reason: str | None = None

    if not is_valid:

        parts = []

        if missing_competencies:

            parts.append(

                f"Missing ratings for "
                f"{len(missing_competencies)} "
                f"required competency/competencies: "
                f"{missing_competencies}"

            )

        if missing_evidence:

            parts.append(

                f"Missing evidence for "
                f"{len(missing_evidence)} "
                f"competency/competencies: "
                f"{missing_evidence}"

            )

        if validation_errors:

            parts.append(

                f"{len(validation_errors)} "
                f"validation error(s) found."

            )

        blocking_reason = " | ".join(parts)

    # -----------------------------------------------------------------------
    # Return result
    # -----------------------------------------------------------------------

    return SubmissionValidationResult(

        is_valid=is_valid,

        missing_competencies=missing_competencies,

        missing_evidence=missing_evidence,

        validation_errors=validation_errors,

        blocking_reason=blocking_reason,

    )
