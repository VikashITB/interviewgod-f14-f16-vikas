"""
Week 1 feature flags.

Flags are intentionally off by default so Week 2 integration can opt in to
new infrastructure without changing historical behavior accidentally.
"""

FEATURE_FLAGS: dict[str, bool] = {
    "f14_audit_logger": False,
    "f14_replay_reconstruction": False,
    "f16_interviewer_scorecard": False,
}


def is_feature_enabled(flag_name: str) -> bool:
    """
    Return whether a known feature flag is enabled.

    Unknown flags fail safely as disabled.
    """

    return bool(
        FEATURE_FLAGS.get(
            flag_name,
            False,
        )
    )


def set_feature_enabled(
    flag_name: str,
    enabled: bool,
) -> None:
    """
    Test/demo helper for explicit opt-in.

    Unknown flags are ignored so callers cannot create runtime feature surface
    accidentally.
    """

    if flag_name not in FEATURE_FLAGS:
        return

    FEATURE_FLAGS[flag_name] = bool(enabled)
