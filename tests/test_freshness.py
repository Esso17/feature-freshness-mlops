"""
Tests for feature_freshness.freshness:
  - feature_age_seconds
  - FeatureFreshnessPolicy
  - check_freshness / FreshnessViolation / FreshnessWarning
"""

import warnings
import pytest
from datetime import datetime, timezone, timedelta

from feature_freshness.freshness import (
    feature_age_seconds,
    FeatureFreshnessPolicy,
    FreshnessViolation,
    FreshnessWarning,
    check_freshness,
)


BASE = datetime(2026, 6, 28, 12, 0, 0, tzinfo=timezone.utc)


def ts(offset_seconds: float) -> datetime:
    return BASE + timedelta(seconds=offset_seconds)


# ---------------------------------------------------------------------------
# feature_age_seconds
# ---------------------------------------------------------------------------


class TestFeatureAgeSeconds:
    def test_zero_age_when_now_equals_ts(self):
        age = feature_age_seconds(BASE, now=BASE)
        assert age == pytest.approx(0.0)

    def test_positive_age(self):
        feature_ts = BASE
        now = ts(120)
        age = feature_age_seconds(feature_ts, now=now)
        assert age == pytest.approx(120.0)

    def test_returns_float(self):
        age = feature_age_seconds(BASE, now=ts(1))
        assert isinstance(age, float)

    def test_naive_feature_timestamp_treated_as_utc(self):
        naive = datetime(2026, 6, 28, 12, 0, 0)  # no tzinfo
        now = datetime(2026, 6, 28, 12, 2, 0, tzinfo=timezone.utc)
        age = feature_age_seconds(naive, now=now)
        assert age == pytest.approx(120.0)

    def test_future_timestamp_returns_zero(self):
        # A feature timestamped in the future — age is clamped to 0.
        future_ts = ts(100)
        age = feature_age_seconds(future_ts, now=BASE)
        assert age == 0.0

    def test_large_age(self):
        old_ts = BASE - timedelta(days=30)
        age = feature_age_seconds(old_ts, now=BASE)
        assert age == pytest.approx(30 * 86400, rel=1e-6)


# ---------------------------------------------------------------------------
# FeatureFreshnessPolicy construction
# ---------------------------------------------------------------------------


class TestFeatureFreshnessPolicyConstruction:
    def test_valid_policy(self):
        p = FeatureFreshnessPolicy("f", warn_after_seconds=60, fail_after_seconds=300)
        assert p.feature_name == "f"
        assert p.warn_after_seconds == 60
        assert p.fail_after_seconds == 300

    def test_warn_equals_fail_is_valid(self):
        p = FeatureFreshnessPolicy("f", warn_after_seconds=60, fail_after_seconds=60)
        assert p.warn_after_seconds == p.fail_after_seconds

    def test_warn_zero_is_valid(self):
        p = FeatureFreshnessPolicy("f", warn_after_seconds=0, fail_after_seconds=60)
        assert p.warn_after_seconds == 0

    def test_negative_warn_raises(self):
        with pytest.raises(ValueError):
            FeatureFreshnessPolicy("f", warn_after_seconds=-1, fail_after_seconds=60)

    def test_zero_fail_raises(self):
        with pytest.raises(ValueError):
            FeatureFreshnessPolicy("f", warn_after_seconds=0, fail_after_seconds=0)

    def test_warn_greater_than_fail_raises(self):
        with pytest.raises(ValueError):
            FeatureFreshnessPolicy("f", warn_after_seconds=300, fail_after_seconds=60)

    def test_policy_is_immutable(self):
        p = FeatureFreshnessPolicy("f", warn_after_seconds=60, fail_after_seconds=300)
        with pytest.raises(Exception):
            p.fail_after_seconds = 999  # frozen dataclass


# ---------------------------------------------------------------------------
# check_freshness — happy path (feature is fresh)
# ---------------------------------------------------------------------------


class TestCheckFreshnessOk:
    def setup_method(self):
        self.policy = FeatureFreshnessPolicy(
            "tx_count", warn_after_seconds=60, fail_after_seconds=300
        )

    def test_fresh_feature_returns_age(self):
        feature_ts = ts(-10)  # 10s old
        age = check_freshness("tx_count", feature_ts, self.policy, now=BASE)
        assert age == pytest.approx(10.0)

    def test_no_warning_below_warn_threshold(self):
        feature_ts = ts(-30)  # 30s old, warn threshold is 60s
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            age = check_freshness("tx_count", feature_ts, self.policy, now=BASE)
        assert age == pytest.approx(30.0)

    def test_hooks_not_called_below_warn(self):
        called = []
        feature_ts = ts(-10)
        check_freshness(
            "tx_count",
            feature_ts,
            self.policy,
            now=BASE,
            on_warn=lambda n, a: called.append(("warn", n, a)),
            on_fail=lambda n, a: called.append(("fail", n, a)),
        )
        assert called == []


# ---------------------------------------------------------------------------
# check_freshness — warning zone
# ---------------------------------------------------------------------------


class TestCheckFreshnessWarn:
    def setup_method(self):
        self.policy = FeatureFreshnessPolicy(
            "tx_count", warn_after_seconds=60, fail_after_seconds=300
        )

    def test_emits_freshness_warning(self):
        feature_ts = ts(-90)  # 90s old, crosses warn but not fail
        with pytest.warns(FreshnessWarning):
            check_freshness("tx_count", feature_ts, self.policy, now=BASE)

    def test_warn_hook_called(self):
        warned = []
        feature_ts = ts(-90)
        check_freshness(
            "tx_count",
            feature_ts,
            self.policy,
            now=BASE,
            on_warn=lambda n, a: warned.append((n, a)),
        )
        assert len(warned) == 1
        name, age = warned[0]
        assert name == "tx_count"
        assert age == pytest.approx(90.0)

    def test_fail_hook_not_called_in_warn_zone(self):
        failed = []
        feature_ts = ts(-90)
        with pytest.warns(FreshnessWarning):
            check_freshness(
                "tx_count",
                feature_ts,
                self.policy,
                now=BASE,
                on_fail=lambda n, a: failed.append((n, a)),
            )
        assert failed == []

    def test_age_at_warn_boundary_warns(self):
        # Exactly at warn threshold (>=) should warn
        feature_ts = ts(-60)
        with pytest.warns(FreshnessWarning):
            check_freshness("tx_count", feature_ts, self.policy, now=ts(0))


# ---------------------------------------------------------------------------
# check_freshness — fail zone
# ---------------------------------------------------------------------------


class TestCheckFreshnessFail:
    def setup_method(self):
        self.policy = FeatureFreshnessPolicy(
            "tx_count", warn_after_seconds=60, fail_after_seconds=300
        )

    def test_raises_freshness_violation(self):
        feature_ts = ts(-400)  # 400s old, exceeds 300s fail threshold
        with pytest.raises(FreshnessViolation) as exc_info:
            check_freshness("tx_count", feature_ts, self.policy, now=BASE)
        assert "tx_count" in str(exc_info.value)

    def test_violation_carries_metadata(self):
        feature_ts = ts(-500)
        with pytest.raises(FreshnessViolation) as exc_info:
            check_freshness("tx_count", feature_ts, self.policy, now=BASE)
        exc = exc_info.value
        assert exc.feature_name == "tx_count"
        assert exc.age == pytest.approx(500.0)
        assert exc.limit == pytest.approx(300.0)

    def test_fail_hook_called_before_raise(self):
        failed = []
        feature_ts = ts(-400)
        with pytest.raises(FreshnessViolation):
            check_freshness(
                "tx_count",
                feature_ts,
                self.policy,
                now=BASE,
                on_fail=lambda n, a: failed.append((n, a)),
            )
        assert len(failed) == 1

    def test_warn_hook_not_called_in_fail_zone(self):
        warned = []
        feature_ts = ts(-400)
        with pytest.raises(FreshnessViolation):
            check_freshness(
                "tx_count",
                feature_ts,
                self.policy,
                now=BASE,
                on_warn=lambda n, a: warned.append((n, a)),
            )
        assert warned == []

    def test_age_at_fail_boundary_raises(self):
        # Exactly at fail threshold (>= 300s) should raise
        feature_ts = ts(-300)
        with pytest.raises(FreshnessViolation):
            check_freshness("tx_count", feature_ts, self.policy, now=ts(0))

    def test_age_one_second_before_fail_is_ok(self):
        feature_ts = ts(-299)
        with pytest.warns(FreshnessWarning):  # is in warn zone (>= 60s)
            age = check_freshness("tx_count", feature_ts, self.policy, now=ts(0))
        assert age == pytest.approx(299.0)


# ---------------------------------------------------------------------------
# FreshnessViolation exception
# ---------------------------------------------------------------------------


class TestFreshnessViolation:
    def test_is_exception(self):
        exc = FreshnessViolation("feat", 400.0, 300.0)
        assert isinstance(exc, Exception)

    def test_str_contains_feature_name(self):
        exc = FreshnessViolation("my_feature", 400.0, 300.0)
        assert "my_feature" in str(exc)

    def test_attributes(self):
        exc = FreshnessViolation("feat", 400.0, 300.0)
        assert exc.feature_name == "feat"
        assert exc.age == 400.0
        assert exc.limit == 300.0
