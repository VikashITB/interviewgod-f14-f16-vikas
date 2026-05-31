import json
import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from database import get_connection

conn = get_connection()

cursor = conn.cursor()

cursor.execute("""

SELECT
    event_id,
    created_at,
    action_type,
    pipeline_stage,
    candidate_id,
    hiring_group_id,
    evidence_snapshot,
    summary

FROM audit_trail

ORDER BY created_at DESC

""")

rows = cursor.fetchall()

print("\n" + "=" * 80)
print("REAL AUDIT LOGS FROM SQLITE DATABASE")
print("=" * 80)


def parse_evidence(raw):

    if not raw:
        return {}

    if isinstance(raw, dict):
        return raw

    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}

    return data if isinstance(data, dict) else {}


for row in rows:

    evidence = parse_evidence(row[6])
    integrity = evidence.get("integrity_signals") or {}

    print("\n----------------------------------------")

    print(f"EVENT ID       : {row[0]}")
    print(f"CREATED AT     : {row[1]}")
    print(f"ACTION TYPE    : {row[2]}")
    print(f"PIPELINE STAGE : {row[3]}")
    print(f"CANDIDATE ID   : {row[4]}")
    print(f"HIRING GROUP   : {row[5]}")
    print(f"SUMMARY        : {row[7]}")

    reasoning_quality = evidence.get("reasoning_quality")
    confidence_score = (
        evidence.get("confidence_score")
        or evidence.get("recommendation_confidence")
    )

    if reasoning_quality is not None:
        print(f"REASONING      : {reasoning_quality}")

    if confidence_score is not None:
        print(f"CONFIDENCE     : {confidence_score}")

    if evidence.get("recommendation_reasoning"):
        print(
            "REC REASONING  : "
            f"{evidence.get('recommendation_reasoning')}"
        )

    if integrity:
        print(
            "INTEGRITY      : "
            f"tabs={integrity.get('tab_switch_count')} | "
            f"copy_paste={integrity.get('copy_paste_detected')} | "
            f"latency={integrity.get('response_latency_seconds')}s | "
            f"suspicion={integrity.get('suspicious_behavior_score')}"
        )

print("\n" + "=" * 80)

conn.close()
