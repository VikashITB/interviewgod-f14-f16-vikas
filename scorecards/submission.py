"""
F16 — Scorecard Submission (submission.py)
==========================================
Handles the complete scorecard submission flow.

ARCHITECTURAL ROLE
------------------
submission.py is the transaction boundary for F16.

Responsibilities:
    1. Run validation
    2. Persist scorecard
    3. Emit audit events
    4. Trigger calibration

Nothing is persisted unless validation passes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from scorecards.schema import (

    InterviewerScorecard,
    RoleBlueprint,
    ScorecardStatus,
    SubmissionValidationResult,
    materialize_scorecard_schema,

)

from scorecards.validator import (
    validate_scorecard
)

from scorecards import calibration as calibration_module

from config.feature_flags import (

    FEATURE_FLAGS,
    is_feature_enabled,

)

from database import (

    clear_scorecard_store_for_testing,
    get_all_persisted_scorecards,
    get_persisted_scorecard,
    get_persisted_scorecards_by_interviewer,
    persist_scorecard,

)

from utils.audit_logger import (

    ActionType,
    EVIDENCE_SCHEMA_VERSION,
    PipelineStage,
    log_audit_event,

)

# ---------------------------------------------------------------------------
# Submission-local observability logs
# ---------------------------------------------------------------------------

AUDIT_LOG: list[dict] = []

CALIBRATION_LOG: list[str] = []

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def submit_scorecard(

    scorecard: InterviewerScorecard,

    blueprint: RoleBlueprint,

    candidate_id: Optional[str] = None,

    hiring_group_id: Optional[str] = None,

) -> SubmissionValidationResult:

    """
    Full scorecard submission flow.
    """

    # -----------------------------------------------------------------------
    # Feature flag
    # -----------------------------------------------------------------------

    if not is_feature_enabled(
        "f16_interviewer_scorecard"
    ):

        return SubmissionValidationResult(

            is_valid=True,

            blocking_reason=(
                "F16 feature flag disabled."
            )

        )

    # -----------------------------------------------------------------------
    # Validation
    # -----------------------------------------------------------------------

    schema = materialize_scorecard_schema(
        blueprint
    )

    result = validate_scorecard(
        scorecard,
        schema
    )

    # -----------------------------------------------------------------------
    # Blocked path
    # -----------------------------------------------------------------------

    if not result.is_valid:

        _emit_audit_blocked(

            scorecard=scorecard,

            blueprint=blueprint,

            result=result,

            candidate_id=candidate_id,

            hiring_group_id=hiring_group_id,

        )

        return result

    # -----------------------------------------------------------------------
    # Success path
    # -----------------------------------------------------------------------

    submitted_scorecard = _mark_submitted(
        scorecard,
        candidate_id=candidate_id,
    )

    _persist_scorecard(
        submitted_scorecard
    )

    _emit_audit_submitted(

        scorecard=submitted_scorecard,

        blueprint=blueprint,

        candidate_id=candidate_id,

        hiring_group_id=hiring_group_id,

    )

    _trigger_calibration_check(

        interviewer_id=submitted_scorecard.interviewer_id,

        hiring_group_id=hiring_group_id,

    )

    return result


def record_recommendation_generated_audit(
    candidate_id: str,
) -> None:
    """
    F11 audit stub for recommendation generation.
    """

    log_audit_event(
        action_type=ActionType.F14_RECOMMENDATION_GENERATED,
        actor_id="system::recommendation_engine",
        actor_email="system@platform.internal",
        candidate_id=str(candidate_id),
        evidence_snapshot={"module": "F11"},
        summary="Recommendation generated"
    )


def record_decision_override_audit(
    candidate_id: str,
) -> None:
    """
    HR override audit stub for manual decision override.
    """

    log_audit_event(
        action_type=ActionType.DECISION_OVERRIDDEN,
        actor_id="system::hr_override",
        actor_email="system@platform.internal",
        candidate_id=str(candidate_id),
        evidence_snapshot={"module": "HR_OVERRIDE"},
        summary="Decision overridden"
    )

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _mark_submitted(
    scorecard: InterviewerScorecard,
    candidate_id: Optional[str] = None,
) -> InterviewerScorecard:

    """
    Return scorecard with submitted state.
    """

    update_fields = {

        "status": ScorecardStatus.SUBMITTED,

        "submitted_at": datetime.now(
            timezone.utc
        ),

    }

    if candidate_id is not None:
        update_fields["candidate_id"] = candidate_id

    return scorecard.model_copy(

        update=update_fields

    )

# ---------------------------------------------------------------------------

def _persist_scorecard(
    scorecard: InterviewerScorecard
) -> None:

    """
    Persist scorecard into storage.
    """

    key = persist_scorecard(
        scorecard
    )

    AUDIT_LOG.append({

        "event": "persisted",

        "key": key,

        "submitted_at": (
            scorecard.submitted_at.isoformat()
            if scorecard.submitted_at
            else None
        )

    })

# ---------------------------------------------------------------------------

def _build_replay_metadata(

    scorecard: InterviewerScorecard,

    blueprint: RoleBlueprint,

    evaluator_version: str,

) -> dict:

    schema = materialize_scorecard_schema(
        blueprint
    )

    required_competencies = [
        competency.competency_id
        for competency
        in schema.competencies
        if competency.required
    ]

    return {

        "blueprint_id":
            schema.blueprint_id,

        "blueprint_version":
            schema.blueprint_version,

        "schema_version":
            schema.schema_version,

        "scorecard_blueprint_version":
            scorecard.blueprint_version,

        "evaluator_version":
            evaluator_version,

        "feature_flags":
            dict(FEATURE_FLAGS),

        "threshold_snapshot": {

            "required_competencies":
                required_competencies,

            "score_map":
                dict(schema.score_scale),

            "overall_recommendation_required":
                (
                    schema
                    .validation_contract
                    .overall_recommendation_required
                ),

            "evidence_required_per_competency":
                (
                    schema
                    .validation_contract
                    .evidence_required_per_competency
                ),

            "all_required_competencies_must_be_rated":
                (
                    schema
                    .validation_contract
                    .all_required_competencies_must_be_rated
                ),

            "knockout_enabled":
                schema.interview_features.knockout_enabled,

        },

    }

# ---------------------------------------------------------------------------

def _emit_audit_blocked(

    scorecard: InterviewerScorecard,

    blueprint: RoleBlueprint,

    result: SubmissionValidationResult,

    candidate_id: Optional[str],

    hiring_group_id: Optional[str],

) -> None:

    """
    Emit blocked audit event.
    """

    schema = materialize_scorecard_schema(
        blueprint
    )

    audit_validation_errors = (
        result.validation_errors
        or (
            [result.blocking_reason]
            if result.blocking_reason
            else []
        )
    )

    event = log_audit_event(

        action_type=ActionType.SCORECARD_BLOCKED,
        pipeline_stage=PipelineStage.INTERVIEW_INTEGRITY,

        actor_id=scorecard.interviewer_id,

        actor_email=(
            f"{scorecard.interviewer_id}"
            f"@platform.internal"
        ),

        candidate_id=candidate_id,

        round_id=scorecard.round_id,

        hiring_group_id=hiring_group_id,

        evidence_snapshot={

            "evidence_schema_version":
                EVIDENCE_SCHEMA_VERSION,

            "replay_metadata":
                _build_replay_metadata(
                    scorecard=scorecard,
                    blueprint=blueprint,
                    evaluator_version="scorecard_validator_v1",
                ),

            "blueprint_id":
                schema.blueprint_id,

            "blueprint_version":
                schema.blueprint_version,

            "schema_version":
                schema.schema_version,

            "must_have_competencies":
                result.missing_competencies
                + [
                    rating.competency
                    for rating
                    in scorecard.competency_ratings
                ],

            "missing_competencies":
                result.missing_competencies,

            "missing_evidence":
                result.missing_evidence,

            "validation_errors":
                audit_validation_errors,

            "schema_validation_errors":
                result.validation_errors,

            "blocking_reason":
                result.blocking_reason,

        },

        summary=(

            f"Scorecard blocked for "
            f"{scorecard.interviewer_id} "
            f"on round {scorecard.round_id}"

        ),

    )

    AUDIT_LOG.append({

        "event": "audit_blocked",

        "event_id": event.event_id,

    })

# ---------------------------------------------------------------------------

def _emit_audit_submitted(

    scorecard: InterviewerScorecard,

    blueprint: RoleBlueprint,

    candidate_id: Optional[str],

    hiring_group_id: Optional[str],

) -> None:

    """
    Emit successful submission audit event.
    """

    schema = materialize_scorecard_schema(
        blueprint
    )

    scores_snapshot = {

        rating.competency: {

            "label":
                rating.label.value,

            "normalized_score":
                rating.normalized_score,

        }

        for rating
        in scorecard.competency_ratings

    }

    evidence_trail = [

        {
            "evidence_schema_version":
                EVIDENCE_SCHEMA_VERSION,

            "competency":
                rating.competency,

            "score":
                rating.normalized_score,

            "candidate_answer":
                (
                    rating.evidence[0].evidence_text
                    if rating.evidence
                    else None
                ),

            "expected_concepts": [],

            "detected_concepts": [],

            "missing_concepts": [],

            "reasoning_quality":
                "recorded",

            "confidence_score":
                None,

            "evidence_text":
                (
                    rating.evidence[0].evidence_text
                    if rating.evidence
                    else None
                ),
        }

        for rating
        in scorecard.competency_ratings

    ]

    event = log_audit_event(

        action_type=ActionType.SCORECARD_SUBMITTED,
        pipeline_stage=PipelineStage.INTERVIEW_INTEGRITY,

        actor_id=scorecard.interviewer_id,

        actor_email=(
            f"{scorecard.interviewer_id}"
            f"@platform.internal"
        ),

        candidate_id=candidate_id,

        round_id=scorecard.round_id,

        hiring_group_id=hiring_group_id,

        evidence_snapshot={

            "evidence_schema_version":
                EVIDENCE_SCHEMA_VERSION,

            "replay_metadata":
                _build_replay_metadata(
                    scorecard=scorecard,
                    blueprint=blueprint,
                    evaluator_version="scorecard_validator_v1",
                ),

            "blueprint_id":
                schema.blueprint_id,

            "blueprint_version":
                schema.blueprint_version,

            "schema_version":
                schema.schema_version,

            "must_have_competencies":
                [
                    rating.competency
                    for rating
                    in scorecard.competency_ratings
                ],

            "overall_recommendation":
                (
                    scorecard
                    .overall_recommendation
                    .value
                    if scorecard
                    .overall_recommendation
                    else None
                ),

            "competency_scores":
                scores_snapshot,

            "evidence_trail":
                evidence_trail,

            "submitted_at":
                (
                    scorecard
                    .submitted_at
                    .isoformat()
                    if scorecard
                    .submitted_at
                    else None
                ),

        },

        summary=(

            f"Scorecard submitted by "
            f"{scorecard.interviewer_id}"

        ),

    )

    AUDIT_LOG.append({

        "event": "audit_submitted",

        "event_id": event.event_id,

    })

# ---------------------------------------------------------------------------

def _trigger_calibration_check(

    interviewer_id: str,

    hiring_group_id: Optional[str],

) -> None:

    """
    Trigger calibration logic.
    """

    CALIBRATION_LOG.append(

        f"[CALIBRATION] "
        f"interviewer={interviewer_id} "
        f"group={hiring_group_id}"

    )

# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def get_scorecard(

    round_id: str,

    interviewer_id: str,

) -> Optional[InterviewerScorecard]:

    return get_persisted_scorecard(

        round_id,

        interviewer_id,

    )

# ---------------------------------------------------------------------------

def get_all_scorecards() -> list[InterviewerScorecard]:

    return get_all_persisted_scorecards(
    )

# ---------------------------------------------------------------------------

def get_scorecards_by_interviewer(
    interviewer_id: str
) -> list[InterviewerScorecard]:

    return get_persisted_scorecards_by_interviewer(
        interviewer_id
    )

# ---------------------------------------------------------------------------

def clear_stores_for_testing() -> None:

    """
    Test-only cleanup helper.
    """

    clear_scorecard_store_for_testing()

    AUDIT_LOG.clear()

    CALIBRATION_LOG.clear()
