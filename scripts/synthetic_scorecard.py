from __future__ import annotations

from datetime import datetime, timezone

from scorecards.schema import (
    CompetencyRating,
    EvidenceEntry,
    InterviewerScorecard,
    OverallRecommendation,
    ScoreLabel,
    SCORE_MAP,
    RoleBlueprint,
)

from scripts.synthetic_blueprint import generate_backend_engine_blueprint


def build_scorecard(
    candidate_id: str,
    round_id: str,
    interviewer_id: str,
    blueprint: RoleBlueprint,
) -> InterviewerScorecard:
    """Build a deterministic scorecard that matches the backend blueprint contract."""
    ratings = [
        CompetencyRating(
            competency="python",
            label=ScoreLabel.STRONG_YES,
            normalized_score=SCORE_MAP[ScoreLabel.STRONG_YES],
            evidence=[
                EvidenceEntry(
                    competency="python",
                    evidence_text=(
                        "Candidate demonstrated expert Python design and "
                        "implementation discipline across multiple services."
                    ),
                    interview_ts=datetime(2025, 8, 7, 15, 0, tzinfo=timezone.utc),
                )
            ],
            rating=5,
        ),
        CompetencyRating(
            competency="fastapi",
            label=ScoreLabel.LEAN_YES,
            normalized_score=SCORE_MAP[ScoreLabel.LEAN_YES],
            evidence=[
                EvidenceEntry(
                    competency="fastapi",
                    evidence_text=(
                        "Candidate built and validated FastAPI endpoints with security "
                        "and dependency injection."
                    ),
                    interview_ts=datetime(2025, 8, 7, 15, 5, tzinfo=timezone.utc),
                )
            ],
            rating=4,
        ),
        CompetencyRating(
            competency="docker",
            label=ScoreLabel.LEAN_NO,
            normalized_score=SCORE_MAP[ScoreLabel.LEAN_NO],
            evidence=[
                EvidenceEntry(
                    competency="docker",
                    evidence_text=(
                        "Candidate has limited Docker experience and did not show "
                        "a strong containerization workflow in interview."
                    ),
                    interview_ts=datetime(2025, 8, 7, 15, 10, tzinfo=timezone.utc),
                )
            ],
            rating=2,
        ),
        CompetencyRating(
            competency="system_design",
            label=ScoreLabel.LEAN_YES,
            normalized_score=SCORE_MAP[ScoreLabel.LEAN_YES],
            evidence=[
                EvidenceEntry(
                    competency="system_design",
                    evidence_text=(
                        "Candidate proposed a reliable service architecture with clear "
                        "scaling and ownership boundaries."
                    ),
                    interview_ts=datetime(2025, 8, 7, 15, 15, tzinfo=timezone.utc),
                )
            ],
            rating=4,
        ),
    ]

    return InterviewerScorecard(
        round_id=round_id,
        interviewer_id=interviewer_id,
        blueprint_id=blueprint.blueprint_id,
        blueprint_version=blueprint.blueprint_version,
        candidate_id=candidate_id,
        competency_ratings=ratings,
        overall_recommendation=OverallRecommendation.YES,
        notes=(
            "Evidence supports recommendation with strong backend and design "
            "signals despite a Docker gap."
        ),
    )


def main() -> int:
    blueprint = generate_backend_engine_blueprint()
    scorecard = build_scorecard(
        candidate_id="cand_backend_001",
        round_id="round_backend_001",
        interviewer_id="interviewer_backend_001",
        blueprint=blueprint,
    )
    print("SYNTHETIC F16 SCORECARD")
    print("-----------------------")
    print(scorecard.model_dump())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
