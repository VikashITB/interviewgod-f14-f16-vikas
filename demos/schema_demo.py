import os
import random
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from scorecards.schema import (
    CompetencyRating,
    EvidenceEntry,
    InterviewerScorecard,
    OverallRecommendation,
    ScoreLabel,
    ScorecardStatus,
)


BLUEPRINT = {
    "must_have_skills": [
        "System Design",
        "Distributed Systems",
        "Communication",
        "Debugging",
    ],
}

SCORE_MAP = {
    ScoreLabel.STRONG_NO: 10,
    ScoreLabel.LEAN_NO: 30,
    ScoreLabel.NEUTRAL: 55,
    ScoreLabel.LEAN_YES: 75,
    ScoreLabel.STRONG_YES: 95,
}

EVIDENCE_TEXT = {
    "System Design": (
        "Candidate explained scalable microservice architecture "
        "with load balancing strategy."
    ),
    "Distributed Systems": (
        "Candidate described partition tolerance, retries, and "
        "backpressure in distributed services."
    ),
    "Communication": (
        "Candidate communicated debugging process clearly with "
        "structured reasoning."
    ),
    "Debugging": (
        "Candidate isolated the failure path methodically and "
        "validated each hypothesis with logs."
    ),
}


def build_scorecard() -> InterviewerScorecard:
    competency_ratings = []

    for competency in BLUEPRINT["must_have_skills"]:
        label = random.choice([
            ScoreLabel.LEAN_NO,
            ScoreLabel.NEUTRAL,
            ScoreLabel.LEAN_YES,
            ScoreLabel.STRONG_YES,
        ])

        evidence = EvidenceEntry(
            competency=competency,
            evidence_text=EVIDENCE_TEXT[competency],
        )

        rating = CompetencyRating(
            competency=competency,
            label=label,
            normalized_score=SCORE_MAP[label],
            evidence=[evidence],
        )

        competency_ratings.append(rating)

    return InterviewerScorecard(
        round_id=f"round_{random.randint(1, 5)}",
        interviewer_id=f"interviewer_{random.randint(100, 999)}",
        blueprint_id="backend_blueprint",
        blueprint_version="v1",
        competency_ratings=competency_ratings,
        overall_recommendation=random.choice([
            OverallRecommendation.NO,
            OverallRecommendation.NEUTRAL,
            OverallRecommendation.YES,
            OverallRecommendation.STRONG_YES,
        ]),
        status=ScorecardStatus.SUBMITTED,
    )


def main() -> None:
    scorecard = build_scorecard()

    print("\n")
    print("=" * 75)
    print("SYNTHETIC INTERVIEW SCORECARD SCHEMA DEMO")
    print("=" * 75)

    print("\n")
    print("SCORECARD METADATA")
    print("-" * 75)

    print(f"{'Round ID':<30}: {scorecard.round_id}")
    print(f"{'Interviewer ID':<30}: {scorecard.interviewer_id}")
    print(f"{'Blueprint ID':<30}: {scorecard.blueprint_id}")
    print(f"{'Blueprint Version':<30}: {scorecard.blueprint_version}")
    print(f"{'Recommendation':<30}: {scorecard.overall_recommendation.value}")
    print(f"{'Status':<30}: {scorecard.status.value}")

    print("\n")
    print("=" * 75)
    print("COMPETENCY RATINGS")
    print("=" * 75)

    print(
        f"{'Competency':<25}"
        f"{'Label':<20}"
        f"{'Normalized Score':<20}"
    )

    print("-" * 75)

    for rating in scorecard.competency_ratings:
        print(
            f"{rating.competency:<25}"
            f"{rating.label.value:<20}"
            f"{rating.normalized_score:<20}"
        )

    print("\n")
    print("=" * 75)
    print("EVIDENCE ENTRIES")
    print("=" * 75)

    for rating in scorecard.competency_ratings:
        for evidence in rating.evidence:
            print(f"\nCompetency : {evidence.competency}")
            print(f"Evidence   : {evidence.evidence_text}")

    print("\n")
    print("=" * 75)
    print("Schema generation completed successfully.")
    print("Synthetic runtime data + blueprint-driven schema working.")
    print("=" * 75)


if __name__ == "__main__":
    main()
