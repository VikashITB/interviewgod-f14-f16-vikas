from __future__ import annotations

from blueprints.models import BlueprintCompetency, RoleBlueprint

BLUEPRINT_ID = "bp_backend_engineer"
BLUEPRINT_VERSION = "v1"


def generate_backend_engine_blueprint() -> RoleBlueprint:
    """Create a deterministic backend engineer blueprint contract."""
    return RoleBlueprint(
        blueprint_id=BLUEPRINT_ID,
        blueprint_version=BLUEPRINT_VERSION,
        competencies=[
            BlueprintCompetency(
                competency_id="python",
                required=True,
                weight=1.0,
                evidence_required=True,
            ),
            BlueprintCompetency(
                competency_id="fastapi",
                required=True,
                weight=1.0,
                evidence_required=True,
            ),
            BlueprintCompetency(
                competency_id="docker",
                required=True,
                weight=1.0,
                evidence_required=True,
            ),
            BlueprintCompetency(
                competency_id="system_design",
                required=True,
                weight=1.0,
                evidence_required=True,
            ),
        ],
    )


def blueprint_summary(blueprint: RoleBlueprint) -> dict:
    """Return the blueprint contract in a replay-friendly payload."""
    return {
        "blueprint_id": blueprint.blueprint_id,
        "blueprint_version": blueprint.blueprint_version,
        "competencies": [competency.model_dump() for competency in blueprint.competencies or []],
        "validation_rules": blueprint.validation_rules.model_dump(),
        "interview_features": blueprint.interview_features.model_dump(),
        "score_scale": blueprint.score_scale,
    }


def main() -> int:
    blueprint = generate_backend_engine_blueprint()
    print("SYNTHETIC BLUEPRINT")
    print("-------------------")
    print("Role: Backend Engineer")
    print("Blueprint ID:", blueprint.blueprint_id)
    print("Blueprint Version:", blueprint.blueprint_version)
    print("Competencies:")
    for competency in blueprint.competencies or []:
        print(
            f"  - {competency.competency_id}: required={competency.required}, "
            f"weight={competency.weight}, evidence_required={competency.evidence_required}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
