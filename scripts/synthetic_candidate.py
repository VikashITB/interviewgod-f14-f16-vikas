from __future__ import annotations

from typing import Any

from scripts.synthetic_blueprint import generate_backend_engine_blueprint

CANDIDATE_ID = "cand_backend_001"


def create_candidate_shell(candidate_id: str = CANDIDATE_ID) -> dict[str, Any]:
    """Build a deterministic candidate shell aligned to the backend blueprint."""
    blueprint = generate_backend_engine_blueprint()

    resume_signals = [
        {
            "competency": "python",
            "blueprint_weight": 5,
            "blueprint_category": "must_have",
            "found": True,
            "years": 4,
            "evidence": [
                "Built backend APIs using FastAPI and Python typing with observable quality."
            ],
            "signal_score": 95,
            "gap": False,
        },
        {
            "competency": "fastapi",
            "blueprint_weight": 4,
            "blueprint_category": "must_have",
            "found": True,
            "years": 2,
            "evidence": [
                "Implemented REST endpoints, dependency injection, and production-ready routing."
            ],
            "signal_score": 78,
            "gap": False,
        },
        {
            "competency": "docker",
            "blueprint_weight": 3,
            "blueprint_category": "must_have",
            "found": False,
            "years": 0,
            "evidence": [],
            "signal_score": 15,
            "gap": True,
        },
        {
            "competency": "system_design",
            "blueprint_weight": 4,
            "blueprint_category": "must_have",
            "found": True,
            "years": 3,
            "evidence": [
                "Designed horizontally scalable API services with fault tolerance and caching."
            ],
            "signal_score": 82,
            "gap": False,
        },
    ]

    interview_signals = {
        "screening_passed": True,
        "technical_interview_observations": [
            "Candidate demonstrated clear API design thinking.",
            "Candidate articulated service boundaries and failure modes."
        ],
        "behavioral_observations": [
            "Communicated tradeoffs with empathy and precision."
        ],
    }

    return {
        "candidate_id": candidate_id,
        "consent_status": "GRANTED",
        "resume_signals": resume_signals,
        "interview_signals": interview_signals,
        "recommendation": None,
        "blueprint_alignment": {
            "blueprint_id": blueprint.blueprint_id,
            "blueprint_version": blueprint.blueprint_version,
            "required_competencies": [competency.competency_id for competency in blueprint.competencies or []],
        },
    }


def main() -> int:
    candidate_shell = create_candidate_shell()
    print("SYNTHETIC CANDIDATE SHELL")
    print("------------------------")
    for key, value in candidate_shell.items():
        print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
