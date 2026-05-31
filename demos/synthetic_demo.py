from datetime import datetime, timezone
import os
import random
import sys
import uuid

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from scorecards.schema import (
    BlueprintCompetency,
    CompetencyRating,
    EvidenceEntry,
    InterviewerScorecard,
    OverallRecommendation,
    RoleBlueprint,
    ScoreLabel,
    materialize_scorecard_schema,
)
from scorecards.submission import submit_scorecard
from config.feature_flags import set_feature_enabled
from utils.audit_logger import (
    ActionType,
    EVIDENCE_SCHEMA_VERSION,
    PipelineStage,
    get_original_f14_action_category,
    log_audit_event,
)

# Feature switches stay off by default. The demo builds richer caller payloads
# without changing the append-only logger contract.
DEMO_FEATURE_FLAGS: dict[str, bool] = {
    "f2_blueprint_runtime_fetch": False,
    "strict_semantic_evidence_validation": False,
}

BLUEPRINT = RoleBlueprint(
    blueprint_id="backend_blueprint",
    blueprint_version="v1",
    competencies=[
        BlueprintCompetency(
            competency_id="System Design",
            required=True,
            weight=0.30,
            evidence_required=True,
            knockout_candidate=True,
        ),
        BlueprintCompetency(
            competency_id="Distributed Systems",
            required=True,
            weight=0.25,
            evidence_required=True,
            knockout_candidate=True,
        ),
        BlueprintCompetency(
            competency_id="Communication",
            required=True,
            weight=0.20,
            evidence_required=True,
            knockout_candidate=False,
        ),
        BlueprintCompetency(
            competency_id="Debugging",
            required=True,
            weight=0.25,
            evidence_required=True,
            knockout_candidate=False,
        ),
    ],
)

GENERATED_SCHEMA = materialize_scorecard_schema(
    BLUEPRINT
)


def build_replay_metadata(
    evaluator_version: str,
) -> dict:
    return {
        "blueprint_id": BLUEPRINT.blueprint_id,
        "blueprint_version": BLUEPRINT.blueprint_version,
        "schema_version": GENERATED_SCHEMA.schema_version,
        "evaluator_version": evaluator_version,
        "feature_flags": dict(DEMO_FEATURE_FLAGS),
        "threshold_snapshot": {
            "required_competencies": [
                competency.competency_id
                for competency
                in GENERATED_SCHEMA.competencies
                if competency.required
            ],
            "score_map": dict(GENERATED_SCHEMA.score_scale),
            "validation_contract": (
                GENERATED_SCHEMA
                .validation_contract
                .model_dump()
            ),
            "minimum_detected_concepts": 1,
            "recommendation_confidence_scale": "0_to_1",
        },
    }

CONCEPTS_BY_COMPETENCY = {
    "System Design": [
        "load balancing",
        "horizontal scaling",
        "cache invalidation",
    ],
    "Distributed Systems": [
        "eventual consistency",
        "replication",
        "failure recovery",
    ],
    "Communication": [
        "tradeoff explanation",
        "clarifying questions",
        "structured summary",
    ],
    "Debugging": [
        "hypothesis testing",
        "logs and metrics",
        "root cause isolation",
    ],
}


def build_semantic_evidence(competency: str) -> dict:
    expected = CONCEPTS_BY_COMPETENCY[competency]
    detected_count = random.randint(1, len(expected))
    detected = expected[:detected_count]
    missing = [
        concept
        for concept
        in expected
        if concept not in detected
    ]
    score = min(95, 35 + detected_count * 20)
    confidence = round(random.uniform(0.56, 0.91), 2)

    return {
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "replay_metadata": build_replay_metadata(
            evaluator_version="synthetic_semantic_evaluator_v1",
        ),
        "competency": competency,
        "score": score,
        "candidate_answer": (
            "Candidate explained "
            f"{', '.join(detected)} "
            "while walking through the interview prompt."
        ),
        "expected_concepts": expected,
        "detected_concepts": detected,
        "missing_concepts": missing,
        "reasoning_quality": (
            "strong"
            if not missing
            else "partial"
        ),
        "confidence_score": confidence,
        "evidence_text": (
            "Candidate covered "
            f"{len(detected)} of {len(expected)} expected concepts; "
            f"missing: {', '.join(missing) if missing else 'none'}."
        ),
        "blueprint_id": BLUEPRINT.blueprint_id,
        "blueprint_version": BLUEPRINT.blueprint_version,
        "schema_version": GENERATED_SCHEMA.schema_version,
        "must_have_competencies": [
            competency.competency_id
            for competency
            in GENERATED_SCHEMA.competencies
            if competency.required
        ],
    }


def build_integrity_signals() -> dict:
    return {
        "tab_switch_count": random.randint(0, 3),
        "copy_paste_detected": random.choice([False, False, False, True]),
        "voice_mismatch_detected": random.choice([False, False, False, True]),
        "response_latency_seconds": random.randint(8, 32),
        "suspicious_behavior_score": round(random.uniform(0.04, 0.34), 2),
    }


def build_recommendation_evidence(competency_scores: dict) -> dict:
    average_score = round(
        sum(competency_scores.values()) / len(competency_scores),
        1,
    )

    return {
        "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
        "replay_metadata": build_replay_metadata(
            evaluator_version="synthetic_recommendation_worker_v1",
        ),
        "recommendation_inputs": [
            "competency_scores",
            "integrity_flags",
            "screening_results",
        ],
        "competency_scores": competency_scores,
        "integrity_flags": build_integrity_signals(),
        "screening_results": {
            "resume_screen_passed": True,
            "knockout_passed": True,
        },
        "recommendation_reasoning": (
            "Generated from validated competency evidence, low integrity risk, "
            "and passed screening checks."
        ),
        "recommendation_confidence": round(min(0.95, average_score / 100), 2),
        "recommendation_source": "recommendation_worker.py",
        "blueprint_id": BLUEPRINT.blueprint_id,
        "blueprint_version": BLUEPRINT.blueprint_version,
        "schema_version": GENERATED_SCHEMA.schema_version,
        "must_have_competencies": [
            competency.competency_id
            for competency
            in GENERATED_SCHEMA.competencies
            if competency.required
        ],
    }


def with_taxonomy_evidence(
    action_type: ActionType,
    payload: dict,
) -> dict:
    return {
        **payload,
        "original_f14_action_category":
            get_original_f14_action_category(action_type),
        "semantic_action_type":
            action_type.value,
    }


def emit_original_f14_action_coverage() -> None:
    candidate_id = "cand_f14_coverage"
    hiring_group = "hg_backend"

    coverage_events = [
        (
            ActionType.CANDIDATE_VIEWED,
            PipelineStage.RESUME_SCREENING,
            "recruiter_demo",
            "recruiter@demo.local",
            {"view_context": "candidate profile opened"},
            "Candidate profile viewed by recruiter",
        ),
        (
            ActionType.STAGE_ADVANCED,
            PipelineStage.CALL_SCREENING,
            "recruiter_demo",
            "recruiter@demo.local",
            {
                "from_stage": "RESUME_SCREENING",
                "to_stage": "CALL_SCREENING",
            },
            "Candidate advanced to call screening",
        ),
        (
            ActionType.SCORE_ASSIGNED,
            PipelineStage.CALL_SCREENING,
            "interviewer_demo",
            "interviewer@demo.local",
            {
                "competency": "System Design",
                "score": 75,
                "score_label": "LEAN_YES",
            },
            "Interview score assigned from validated evidence",
        ),
        (
            ActionType.F14_RECOMMENDATION_GENERATED,
            PipelineStage.RECOMMENDATION,
            "worker::recommendation_engine",
            "system@platform.internal",
            build_recommendation_evidence(
                {
                    "System Design": 75,
                    "Distributed Systems": 82,
                }
            ),
            "Recommendation generated for recruiter review",
        ),
        (
            ActionType.DECISION_MADE,
            PipelineStage.FINAL_DECISION,
            "recruiter_demo",
            "recruiter@demo.local",
            {
                "decision": "ADVANCE",
                "decision_basis": "scorecard and recommendation reviewed",
            },
            "Hiring decision recorded",
        ),
        (
            ActionType.DECISION_OVERRIDDEN,
            PipelineStage.HR_OVERRIDE,
            "hr_demo",
            "hr@demo.local",
            {
                "original_decision": "REJECT",
                "override_decision": "ADVANCE",
                "override_reason": "Late-arriving evidence reviewed",
            },
            "Decision overridden with HR justification",
        ),
        (
            ActionType.CONSENT_GRANTED,
            PipelineStage.RESUME_SCREENING,
            "candidate_demo",
            "candidate@demo.local",
            {
                "consent_scope": "assessment_processing",
                "consent_status": "granted",
            },
            "Candidate consent granted",
        ),
        (
            ActionType.CONSENT_WITHDRAWN,
            PipelineStage.RESUME_SCREENING,
            "candidate_demo",
            "candidate@demo.local",
            {
                "consent_scope": "assessment_processing",
                "consent_status": "withdrawn",
            },
            "Candidate consent withdrawn",
        ),
        (
            ActionType.AI_PROCESSING_BLOCKED,
            PipelineStage.INTERVIEW_INTEGRITY,
            "system::policy_guard",
            "system@platform.internal",
            {
                "block_reason": "consent_withdrawn",
                "blocked_processor": "semantic_score_evaluator",
            },
            "AI processing blocked by consent policy",
        ),
        (
            ActionType.F4_FALLBACK_USED,
            PipelineStage.INTERVIEW_INTEGRITY,
            "system::fallback",
            "system@platform.internal",
            {
                "fallback_source": "F4",
                "fallback_reason": "primary evaluator unavailable",
            },
            "F4 fallback used for continuity",
        ),
    ]

    print("\nORIGINAL F14 ACTION COVERAGE")
    print("-" * 70)

    for action, stage, actor_id, actor_email, payload, summary in coverage_events:
        event = log_audit_event(
            action_type=action,
            pipeline_stage=stage,
            actor_id=actor_id,
            actor_email=actor_email,
            candidate_id=candidate_id,
            round_id="round_f14_coverage",
            hiring_group_id=hiring_group,
            evidence_snapshot=with_taxonomy_evidence(
                action,
                {
                    **payload,
                    "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
                    "replay_metadata": build_replay_metadata(
                        evaluator_version="synthetic_f14_coverage_v1",
                    ),
                },
            ),
            summary=summary,
        )

        print(
            f"[COVERED] {event.action_type.value:<28} | "
            f"{event.pipeline_stage.value:<18} | "
            f"{candidate_id:<17} | {hiring_group}"
        )


def submit_validated_scorecard(candidate_id: str, hiring_group: str) -> None:
    ratings = []

    for competency_contract in GENERATED_SCHEMA.competencies:
        competency = competency_contract.competency_id
        semantic_evidence = build_semantic_evidence(competency)
        label = (
            ScoreLabel.LEAN_YES
            if semantic_evidence["score"] >= 70
            else ScoreLabel.NEUTRAL
        )

        ratings.append(
            CompetencyRating(
                competency=competency,
                label=label,
                normalized_score=GENERATED_SCHEMA.score_scale[label.value],
                evidence=[
                    EvidenceEntry(
                        competency=competency,
                        evidence_text=semantic_evidence["evidence_text"],
                        interview_ts=datetime.now(timezone.utc),
                    )
                ],
            )
        )

    scorecard = InterviewerScorecard(
        round_id=f"round_{random.randint(1, 5)}",
        interviewer_id=f"interviewer_{random.randint(100, 999)}",
        blueprint_id=BLUEPRINT.blueprint_id,
        blueprint_version=BLUEPRINT.blueprint_version,
        competency_ratings=ratings,
        overall_recommendation=OverallRecommendation.YES,
    )

    submit_scorecard(
        scorecard=scorecard,
        blueprint=BLUEPRINT,
        candidate_id=candidate_id,
        hiring_group_id=hiring_group,
    )


def main() -> None:
    set_feature_enabled(
        "f16_interviewer_scorecard",
        True,
    )

    print("\n")
    print("=" * 70)
    print("SYNTHETIC RUNTIME AUDIT EVENT GENERATION")
    print("=" * 70)

    emit_original_f14_action_coverage()

    print("\nSEMANTIC REPLAY EXTENSION EVENTS")
    print("-" * 70)

    for _ in range(10):
        candidate_id = f"cand_{random.randint(100, 999)}"
        hiring_group = random.choice([
            "hg_backend",
            "hg_frontend",
            "hg_ml",
        ])
        action = random.choice([
            ActionType.SCORECARD_SUBMITTED,
            ActionType.RECOMMENDATION_GENERATED,
            ActionType.CANDIDATE_KNOCKED_OUT,
        ])

        if action == ActionType.SCORECARD_SUBMITTED:
            submit_validated_scorecard(candidate_id, hiring_group)
            print(
                f"[VALIDATED] {action.value:<30} | "
                f"{candidate_id:<10} | {hiring_group:<12} | "
                f"{BLUEPRINT.blueprint_id}"
            )
            continue

        competency = random.choice([
            competency_contract.competency_id
            for competency_contract
            in GENERATED_SCHEMA.competencies
        ])
        semantic_evidence = build_semantic_evidence(competency)

        if action == ActionType.RECOMMENDATION_GENERATED:
            competency_scores = {
                competency: semantic_evidence["score"],
                random.choice([
                    competency_contract.competency_id
                    for competency_contract
                    in GENERATED_SCHEMA.competencies
                ]): random.randint(
                    55,
                    95,
                ),
            }
            evidence_snapshot = build_recommendation_evidence(
                competency_scores,
            )
            pipeline_stage = PipelineStage.RECOMMENDATION
            summary = (
                "Recommendation generated with recruiter-reviewable reasoning"
            )
        else:
            evidence_snapshot = {
                **semantic_evidence,
                "knockout_reason": "missing_required_concept",
                "integrity_signals": build_integrity_signals(),
            }
            pipeline_stage = PipelineStage.KNOCKOUT_CHECK
            summary = f"Candidate knockout evaluated for {competency}"

        event = log_audit_event(
            action_type=action,
            pipeline_stage=pipeline_stage,
            actor_id=str(uuid.uuid4()),
            actor_email=f"synthetic_{random.randint(1000, 9999)}@demo.local",
            candidate_id=candidate_id,
            round_id=f"round_{random.randint(1, 5)}",
            hiring_group_id=hiring_group,
            evidence_snapshot=evidence_snapshot,
            summary=summary,
        )

        print(
            f"[INSERTED] {event.action_type.value:<30} | "
            f"{event.pipeline_stage.value:<18} | "
            f"{candidate_id:<10} | {hiring_group:<12}"
        )

    print("\n")
    print("=" * 70)
    print("Synthetic audit event generation completed.")
    print("Persisted to SQLite -> audit_trail")
    print("=" * 70)


if __name__ == "__main__":
    main()
