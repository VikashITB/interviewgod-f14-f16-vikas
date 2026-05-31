import sqlite3
from pathlib import Path
from typing import Optional

from scorecards.schema import InterviewerScorecard


DEFAULT_DB_PATH = Path(__file__).resolve().parent / "hiring_platform.db"
DB_PATH = DEFAULT_DB_PATH
SCORECARD_STORE: dict[str, InterviewerScorecard] = {}


def get_connection():
    """
    Return a SQLite connection for the local sprint persistence layer.

    The public API intentionally stays stable so callers remain isolated from
    the database implementation.
    """
    return sqlite3.connect(
        DB_PATH,
        timeout=30,
    )


def set_database_path_for_testing(
    db_path: str | Path,
) -> None:
    """
    Point database helpers at an isolated test SQLite file.

    Production callers use DEFAULT_DB_PATH. Tests use this to avoid shared
    SQLite writer locks and hidden state coupling.
    """

    global DB_PATH

    DB_PATH = Path(db_path)


def reset_database_path() -> None:
    """
    Restore the default local sprint database path.
    """

    global DB_PATH

    DB_PATH = DEFAULT_DB_PATH


def scorecard_key(
    round_id: str,
    interviewer_id: str,
) -> str:
    return f"{round_id}::{interviewer_id}"


def persist_scorecard(
    scorecard: InterviewerScorecard,
) -> str:
    """
    Persist a submitted scorecard in the Week 1 scorecard store.
    """

    key = scorecard_key(
        scorecard.round_id,
        scorecard.interviewer_id,
    )

    SCORECARD_STORE[key] = scorecard

    return key


def get_persisted_scorecard(
    round_id: str,
    interviewer_id: str,
) -> Optional[InterviewerScorecard]:
    return SCORECARD_STORE.get(
        scorecard_key(
            round_id,
            interviewer_id,
        )
    )


def get_all_persisted_scorecards() -> list[InterviewerScorecard]:
    return list(
        SCORECARD_STORE.values()
    )


def get_persisted_scorecards_by_interviewer(
    interviewer_id: str,
) -> list[InterviewerScorecard]:
    return [
        scorecard
        for scorecard
        in SCORECARD_STORE.values()
        if scorecard.interviewer_id == interviewer_id
    ]


def clear_scorecard_store_for_testing() -> None:
    SCORECARD_STORE.clear()
