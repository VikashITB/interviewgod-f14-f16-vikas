import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from utils.audit_logger import (
    ActionType,
    PipelineStage,
    log_audit_event,
    query_by_action_type_from_db,
    query_by_candidate_from_db,
    query_by_hiring_group_from_db,
)


BENCH_CANDIDATE_ID = "cand_benchmark"
BENCH_HIRING_GROUP_ID = "hg_benchmark"
BENCH_ROUND_ID = "round_benchmark"


def timed(label: str, fn):
    started = time.perf_counter()
    result = fn()
    elapsed_ms = (time.perf_counter() - started) * 1000
    return label, elapsed_ms, result


def seed_benchmark_events(total: int = 25) -> None:
    for index in range(total):
        log_audit_event(
            action_type=ActionType.CANDIDATE_VIEWED,
            pipeline_stage=PipelineStage.RESUME_SCREENING,
            actor_id=f"bench_recruiter_{index}",
            actor_email=f"bench_recruiter_{index}@demo.local",
            candidate_id=BENCH_CANDIDATE_ID,
            round_id=BENCH_ROUND_ID,
            hiring_group_id=BENCH_HIRING_GROUP_ID,
            evidence_snapshot={
                "benchmark_seed": True,
                "sequence": index,
            },
            summary="Benchmark candidate view event",
        )

    log_audit_event(
        action_type=ActionType.DECISION_OVERRIDDEN,
        pipeline_stage=PipelineStage.HR_OVERRIDE,
        actor_id="bench_hr",
        actor_email="bench_hr@demo.local",
        candidate_id=BENCH_CANDIDATE_ID,
        round_id=BENCH_ROUND_ID,
        hiring_group_id=BENCH_HIRING_GROUP_ID,
        evidence_snapshot={
            "benchmark_seed": True,
            "original_decision": "REJECT",
            "override_decision": "ADVANCE",
        },
        summary="Benchmark override event",
    )


def insert_one_concurrent(index: int):
    return log_audit_event(
        action_type=ActionType.STAGE_ADVANCED,
        pipeline_stage=PipelineStage.CALL_SCREENING,
        actor_id=f"bench_worker_{index}",
        actor_email=f"bench_worker_{index}@demo.local",
        candidate_id=f"{BENCH_CANDIDATE_ID}_{index}",
        round_id=BENCH_ROUND_ID,
        hiring_group_id=BENCH_HIRING_GROUP_ID,
        evidence_snapshot={
            "benchmark_concurrent_insert": True,
            "sequence": index,
        },
        summary="Benchmark concurrent stage advancement",
    )


def run_concurrent_insert_simulation(total: int = 20) -> int:
    inserted = 0

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(insert_one_concurrent, index)
            for index
            in range(total)
        ]

        for future in as_completed(futures):
            future.result()
            inserted += 1

    return inserted


def print_result(label: str, elapsed_ms: float, count: int) -> None:
    print(f"{label:<35} {elapsed_ms:>9.2f} ms   rows={count}")


def main() -> int:
    print("\n")
    print("=" * 72)
    print("F14 SQLITE AUDIT BENCHMARK")
    print("=" * 72)
    print("SQLite only; append-only inserts; local deterministic read checks.")
    print("-" * 72)

    seed_benchmark_events()

    benchmarks = [
        timed(
            "candidate timeline query",
            lambda: query_by_candidate_from_db(BENCH_CANDIDATE_ID),
        ),
        timed(
            "hiring group query",
            lambda: query_by_hiring_group_from_db(BENCH_HIRING_GROUP_ID),
        ),
        timed(
            "override event query",
            lambda: query_by_action_type_from_db(
                ActionType.DECISION_OVERRIDDEN
            ),
        ),
        timed(
            "concurrent insert simulation",
            run_concurrent_insert_simulation,
        ),
    ]

    for label, elapsed_ms, result in benchmarks:
        count = result if isinstance(result, int) else len(result)
        print_result(label, elapsed_ms, count)

    print("-" * 72)
    print("Benchmark completed successfully.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
