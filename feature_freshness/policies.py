"""
Per-feature freshness policies and metric emission hooks.

In production, swap the print-based hooks for your real metrics client
(Prometheus, Datadog, StatsD, …).
"""

from datetime import datetime
from typing import Callable, Dict, Optional

from feature_freshness.freshness import (
    FeatureFreshnessPolicy,
    check_freshness,
)


# ---------------------------------------------------------------------------
# Policy registry
#
# warn_after_seconds  — emit a metric; request continues.
# fail_after_seconds  — raise FreshnessViolation; request is blocked.
# ---------------------------------------------------------------------------

FRESHNESS_POLICIES: Dict[str, FeatureFreshnessPolicy] = {
    # High-velocity streaming features
    "transaction_amount": FeatureFreshnessPolicy(
        feature_name="transaction_amount",
        warn_after_seconds=60,
        fail_after_seconds=300,
    ),
    "spending_velocity": FeatureFreshnessPolicy(
        feature_name="spending_velocity",
        warn_after_seconds=30,
        fail_after_seconds=120,
    ),
    "login_count": FeatureFreshnessPolicy(
        feature_name="login_count",
        warn_after_seconds=120,
        fail_after_seconds=600,
    ),
    # Slower-moving batch features
    "account_age_days": FeatureFreshnessPolicy(
        feature_name="account_age_days",
        warn_after_seconds=43_200,   # 12 h
        fail_after_seconds=86_400,   # 24 h
    ),
    "daily_spending_avg": FeatureFreshnessPolicy(
        feature_name="daily_spending_avg",
        warn_after_seconds=3_600,    # 1 h
        fail_after_seconds=7_200,    # 2 h
    ),
    "risk_score": FeatureFreshnessPolicy(
        feature_name="risk_score",
        warn_after_seconds=1_800,    # 30 min
        fail_after_seconds=3_600,    # 1 h
    ),
}


# ---------------------------------------------------------------------------
# Default metric hooks (replace in production)
# ---------------------------------------------------------------------------


def default_warn_hook(feature_name: str, age: float) -> None:
    print(
        f"[METRIC] feature_freshness_warn "
        f"feature={feature_name} age={age:.1f}s"
    )


def default_fail_hook(feature_name: str, age: float) -> None:
    print(
        f"[METRIC] feature_freshness_fail "
        f"feature={feature_name} age={age:.1f}s"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_feature_freshness(
    feature_name: str,
    feature_timestamp: datetime,
    now: Optional[datetime] = None,
    on_warn: Optional[Callable[[str, float], None]] = default_warn_hook,
    on_fail: Optional[Callable[[str, float], None]] = default_fail_hook,
) -> float:
    """
    Look up the policy for `feature_name` and enforce it.

    Parameters
    ----------
    feature_name : str
        Must match a key in FRESHNESS_POLICIES; no-op if not found.
    feature_timestamp : datetime
        When the feature was last computed.
    now : datetime, optional
        Override for deterministic testing.
    on_warn : callable, optional
        Metric hook called on warn threshold breach.
    on_fail : callable, optional
        Metric hook called on fail threshold breach (before raising).

    Returns
    -------
    float
        Feature age in seconds.  Returns 0.0 if no policy is registered.

    Raises
    ------
    FreshnessViolation
        When age exceeds the registered fail_after_seconds.
    """
    policy = FRESHNESS_POLICIES.get(feature_name)
    if policy is None:
        return 0.0  # Unknown feature — no policy enforced.

    return check_freshness(
        feature_name=feature_name,
        feature_timestamp=feature_timestamp,
        policy=policy,
        now=now,
        on_warn=on_warn,
        on_fail=on_fail,
    )


def register_policy(policy: FeatureFreshnessPolicy) -> None:
    """Register or replace a freshness policy at runtime."""
    FRESHNESS_POLICIES[policy.feature_name] = policy


def get_policy(feature_name: str) -> Optional[FeatureFreshnessPolicy]:
    """Return the registered policy or None."""
    return FRESHNESS_POLICIES.get(feature_name)
