"""
F16 — Calibration (calibration.py)
==================================
Detects interviewer scoring drift against organization averages.

ARCHITECTURAL ROLE
------------------
Calibration is a read-only analytics layer.

Responsibilities:
    - Detect scoring drift
    - Detect lenient / harsh interviewers
    - Flag calibration outliers
    - Halt interviewer assignments if needed

No DB writes occur here.
"""

from __future__ import annotations

from scorecards.schema import (

    CalibrationSnapshot,
    InterviewerScorecard,

)

# ---------------------------------------------------------------------------
# Core calibration logic
# ---------------------------------------------------------------------------

def compute_calibration_snapshot(

    interviewer_scorecards: list[InterviewerScorecard],

    all_scorecards: list[InterviewerScorecard],

    interviewer_id: str,

    snapshot_week: str | None = None,

) -> CalibrationSnapshot | None:

    """
    Compute calibration snapshot.
    """

    # -----------------------------------------------------------------------
    # Minimum threshold
    # -----------------------------------------------------------------------

    if len(interviewer_scorecards) < 10:

        return None

    # -----------------------------------------------------------------------
    # Average calculations
    # -----------------------------------------------------------------------

    interviewer_avg = _compute_average_score(
        interviewer_scorecards
    )

    org_avg = _compute_average_score(
        all_scorecards
    )

    # -----------------------------------------------------------------------
    # Safety guard
    # -----------------------------------------------------------------------

    if org_avg == 0:

        return None

    # -----------------------------------------------------------------------
    # Drift logic
    # -----------------------------------------------------------------------

    drift_pct = (

        abs(interviewer_avg - org_avg)
        / org_avg
        * 100

    )

    flagged = drift_pct > 30.0

    drift_direction = _compute_direction(

        interviewer_avg,

        org_avg,

        drift_pct,

    )

    # -----------------------------------------------------------------------
    # Build snapshot
    # -----------------------------------------------------------------------

    return CalibrationSnapshot(

        interviewer_id=interviewer_id,

        scorecard_count=len(
            interviewer_scorecards
        ),

        interviewer_avg=round(
            interviewer_avg,
            2
        ),

        org_avg=round(
            org_avg,
            2
        ),

        drift_pct=round(
            drift_pct,
            2
        ),

        drift_direction=drift_direction,

        flagged=flagged,

        snapshot_week=snapshot_week,

    )

# ---------------------------------------------------------------------------
# Outlier detection
# ---------------------------------------------------------------------------

def detect_outlier(

    snapshots: list[CalibrationSnapshot]

) -> bool:

    """
    Detect interviewer calibration outlier.

    Requirements:
        - At least 2 snapshots
        - Both flagged
        - Same drift direction
        - Consecutive weeks
    """

    if len(snapshots) < 2:

        return False

    # -------------------------------------------------------------------
    # Sort snapshots by week
    # -------------------------------------------------------------------

    ordered = sorted(

        snapshots,

        key=lambda s: s.snapshot_week

    )

    last_two = ordered[-2:]

    first = last_two[0]
    second = last_two[1]

    # -------------------------------------------------------------------
    # Both must be flagged
    # -------------------------------------------------------------------

    if not (

        first.flagged
        and second.flagged

    ):

        return False

    # -------------------------------------------------------------------
    # Same direction
    # -------------------------------------------------------------------

    if (

        first.drift_direction
        != second.drift_direction

    ):

        return False

    # -------------------------------------------------------------------
    # Consecutive week enforcement
    # -------------------------------------------------------------------

    try:

        first_year, first_week = (
            first.snapshot_week
            .replace("W", "")
            .split("-")
        )

        second_year, second_week = (
            second.snapshot_week
            .replace("W", "")
            .split("-")
        )

        first_week = int(first_week)
        second_week = int(second_week)

        first_year = int(first_year)
        second_year = int(second_year)

    except Exception:

        return False

    # Must be same year and consecutive weeks

    same_year = (
        first_year == second_year
    )

    consecutive = (
        second_week - first_week == 1
    )

    return (

        same_year
        and consecutive

    )

# ---------------------------------------------------------------------------
# Outlier action payload
# ---------------------------------------------------------------------------

def get_outlier_action(
    snapshot: CalibrationSnapshot
) -> dict:

    """
    Action payload for calibration outlier.
    """

    return {

        "interviewer_id":
            snapshot.interviewer_id,

        "action":
            "HALT_ASSIGNMENTS",

        "reason": (

            f"Calibration outlier detected: "
            f"{snapshot.drift_direction} "
            f"drift of "
            f"{snapshot.drift_pct:.1f}%."

        ),

        "drift_pct":
            snapshot.drift_pct,

        "drift_direction":
            snapshot.drift_direction,

        "snapshot_week":
            snapshot.snapshot_week,

    }

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _compute_average_score(

    scorecards: list[InterviewerScorecard]

) -> float:

    """
    Compute average normalized score.
    """

    all_scores: list[int] = []

    for scorecard in scorecards:

        for rating in scorecard.competency_ratings:

            all_scores.append(
                rating.normalized_score
            )

    if not all_scores:

        return 0.0

    return (

        sum(all_scores)
        / len(all_scores)

    )

# ---------------------------------------------------------------------------

def _compute_direction(

    interviewer_avg: float,

    org_avg: float,

    drift_pct: float,

) -> str:

    """
    Determine drift direction.
    """

    if drift_pct < 5.0:

        return "aligned"

    if interviewer_avg > org_avg:

        return "lenient"

    return "harsh"