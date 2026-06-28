"""
Feature freshness: age calculation and SLA enforcement.

Core formula
------------
    feature_age = serving_time - feature_timestamp

Usage
-----
    from feature_freshness.freshness import feature_age_seconds, check_freshness

    age = feature_age_seconds(feature_timestamp)
    check_freshness("transaction_count", feature_timestamp, policy)
"""

import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _utc(dt: datetime) -> datetime:
    """Coerce naive datetime to UTC-aware; return aware datetime unchanged."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def feature_age_seconds(
    feature_timestamp: datetime,
    now: Optional[datetime] = None,
) -> float:
    """
    Return how old a feature value is, in seconds.

    Parameters
    ----------
    feature_timestamp : datetime
        When the feature value was last computed or written.
    now : datetime, optional
        Reference point for age calculation.  Defaults to UTC now.
        Pass an explicit value in tests to avoid depending on wall-clock time.

    Returns
    -------
    float
        Age in seconds.  Always >= 0 for well-formed inputs.
    """
    effective_now = _utc(now) if now is not None else datetime.now(timezone.utc)
    delta = effective_now - _utc(feature_timestamp)
    return max(0.0, delta.total_seconds())


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeatureFreshnessPolicy:
    """
    Per-feature freshness contract.

    Attributes
    ----------
    feature_name : str
        Identifies the feature this policy applies to.
    warn_after_seconds : float
        Age at which a warning is issued but the request is not blocked.
    fail_after_seconds : float
        Age at which a FreshnessViolation is raised and the request is blocked.
    """

    feature_name: str
    warn_after_seconds: float
    fail_after_seconds: float

    def __post_init__(self) -> None:
        if self.warn_after_seconds < 0:
            raise ValueError("warn_after_seconds must be >= 0")
        if self.fail_after_seconds <= 0:
            raise ValueError("fail_after_seconds must be > 0")
        if self.warn_after_seconds > self.fail_after_seconds:
            raise ValueError(
                "warn_after_seconds must be <= fail_after_seconds"
            )


# ---------------------------------------------------------------------------
# Exceptions / warnings
# ---------------------------------------------------------------------------


class FreshnessViolation(Exception):
    """Raised when a feature exceeds its fail_after_seconds threshold."""

    def __init__(self, feature_name: str, age: float, limit: float) -> None:
        self.feature_name = feature_name
        self.age = age
        self.limit = limit
        super().__init__(
            f"[FRESHNESS FAIL] '{feature_name}' is {age:.1f}s old "
            f"(limit: {limit:.1f}s)"
        )


class FreshnessWarning(UserWarning):
    """Issued when a feature exceeds its warn_after_seconds threshold."""


# ---------------------------------------------------------------------------
# Check
# ---------------------------------------------------------------------------


def check_freshness(
    feature_name: str,
    feature_timestamp: datetime,
    policy: FeatureFreshnessPolicy,
    now: Optional[datetime] = None,
    on_warn: Optional[Callable[[str, float], None]] = None,
    on_fail: Optional[Callable[[str, float], None]] = None,
) -> float:
    """
    Enforce a freshness policy for a single feature.

    Parameters
    ----------
    feature_name : str
        Name used in error/warning messages (need not match policy.feature_name).
    feature_timestamp : datetime
        When the feature value was last computed.
    policy : FeatureFreshnessPolicy
        Thresholds to enforce.
    now : datetime, optional
        Override the current time (for deterministic testing).
    on_warn : callable, optional
        Called with (feature_name, age_seconds) when warn threshold is crossed.
        Useful for emitting metrics.
    on_fail : callable, optional
        Called with (feature_name, age_seconds) before raising FreshnessViolation.
        Useful for emitting metrics.

    Returns
    -------
    float
        Feature age in seconds.

    Raises
    ------
    FreshnessViolation
        If age > policy.fail_after_seconds.
    """
    age = feature_age_seconds(feature_timestamp, now=now)

    if age >= policy.fail_after_seconds:
        if on_fail is not None:
            on_fail(feature_name, age)
        raise FreshnessViolation(feature_name, age, policy.fail_after_seconds)

    if age >= policy.warn_after_seconds:
        if on_warn is not None:
            on_warn(feature_name, age)
        warnings.warn(
            f"[FRESHNESS WARN] '{feature_name}' is {age:.1f}s old "
            f"(warn threshold: {policy.warn_after_seconds:.1f}s)",
            FreshnessWarning,
            stacklevel=2,
        )

    return age
