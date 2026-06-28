"""
Tests for feature_freshness.policies:
  - FRESHNESS_POLICIES registry
  - check_feature_freshness
  - register_policy / get_policy
"""

import warnings
import pytest
from datetime import datetime, timezone, timedelta

from feature_freshness.policies import (
    FRESHNESS_POLICIES,
    check_feature_freshness,
    register_policy,
    get_policy,
)
from feature_freshness.freshness import (
    FeatureFreshnessPolicy,
    FreshnessViolation,
    FreshnessWarning,
)


BASE = datetime(2026, 6, 28, 12, 0, 0, tzinfo=timezone.utc)


def ts(offset_seconds: float) -> datetime:
    return BASE + timedelta(seconds=offset_seconds)


# ---------------------------------------------------------------------------
# Policy registry
# ---------------------------------------------------------------------------


class TestPolicyRegistry:
    def test_all_registered_policies_have_valid_thresholds(self):
        for name, policy in FRESHNESS_POLICIES.items():
            assert policy.warn_after_seconds <= policy.fail_after_seconds, (
                f"Policy '{name}': warn must be <= fail"
            )
            assert policy.fail_after_seconds > 0, (
                f"Policy '{name}': fail must be > 0"
            )

    def test_known_features_registered(self):
        expected = {
            "transaction_amount",
            "spending_velocity",
            "account_age_days",
            "daily_spending_avg",
            "risk_score",
        }
        for feature in expected:
            assert feature in FRESHNESS_POLICIES, (
                f"'{feature}' not in FRESHNESS_POLICIES"
            )

    def test_high_velocity_features_have_tighter_sla(self):
        # Streaming features should have shorter fail windows than batch.
        tx = FRESHNESS_POLICIES["transaction_amount"]
        acct = FRESHNESS_POLICIES["account_age_days"]
        assert tx.fail_after_seconds < acct.fail_after_seconds

    def test_all_policies_have_matching_feature_name(self):
        for key, policy in FRESHNESS_POLICIES.items():
            assert policy.feature_name == key


# ---------------------------------------------------------------------------
# check_feature_freshness — unknown feature
# ---------------------------------------------------------------------------


class TestCheckFeatureFreshnessUnknown:
    def test_unknown_feature_returns_zero(self):
        result = check_feature_freshness(
            "totally_unknown_feature", ts(-100), now=BASE
        )
        assert result == 0.0

    def test_unknown_feature_raises_no_exception(self):
        # Should not raise regardless of age
        result = check_feature_freshness(
            "undefined_feature", ts(-999999), now=BASE
        )
        assert result == 0.0


# ---------------------------------------------------------------------------
# check_feature_freshness — fresh feature
# ---------------------------------------------------------------------------


class TestCheckFeatureFreshnessFresh:
    def test_fresh_transaction_amount(self):
        # 10s old, warn at 60s — should pass cleanly
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            age = check_feature_freshness(
                "transaction_amount", ts(-10), now=BASE, on_warn=None, on_fail=None
            )
        assert age == pytest.approx(10.0)

    def test_fresh_account_age_days(self):
        # 1h old, warn at 12h — should pass cleanly
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            age = check_feature_freshness(
                "account_age_days", ts(-3600), now=BASE, on_warn=None, on_fail=None
            )
        assert age == pytest.approx(3600.0)


# ---------------------------------------------------------------------------
# check_feature_freshness — warn zone
# ---------------------------------------------------------------------------


class TestCheckFeatureFreshnessWarn:
    def test_transaction_amount_warn(self):
        # 90s old — crosses 60s warn threshold
        with pytest.warns(FreshnessWarning):
            check_feature_freshness(
                "transaction_amount", ts(-90), now=BASE, on_warn=None, on_fail=None
            )

    def test_spending_velocity_warn(self):
        # 60s old — crosses 30s warn threshold for spending_velocity
        with pytest.warns(FreshnessWarning):
            check_feature_freshness(
                "spending_velocity", ts(-60), now=BASE, on_warn=None, on_fail=None
            )

    def test_warn_hook_receives_correct_args(self):
        calls = []
        check_feature_freshness(
            "transaction_amount",
            ts(-90),
            now=BASE,
            on_warn=lambda n, a: calls.append((n, a)),
            on_fail=None,
        )
        assert len(calls) == 1
        name, age = calls[0]
        assert name == "transaction_amount"
        assert age == pytest.approx(90.0)


# ---------------------------------------------------------------------------
# check_feature_freshness — fail zone
# ---------------------------------------------------------------------------


class TestCheckFeatureFreshnessFail:
    def test_transaction_amount_fail(self):
        # 400s old — crosses 300s fail threshold
        with pytest.raises(FreshnessViolation):
            check_feature_freshness(
                "transaction_amount", ts(-400), now=BASE
            )

    def test_spending_velocity_fail(self):
        # 200s old — crosses 120s fail threshold
        with pytest.raises(FreshnessViolation):
            check_feature_freshness(
                "spending_velocity", ts(-200), now=BASE
            )

    def test_fail_hook_called(self):
        calls = []
        with pytest.raises(FreshnessViolation):
            check_feature_freshness(
                "transaction_amount",
                ts(-400),
                now=BASE,
                on_fail=lambda n, a: calls.append((n, a)),
            )
        assert len(calls) == 1

    def test_violation_is_catchable(self):
        caught = False
        try:
            check_feature_freshness("transaction_amount", ts(-400), now=BASE)
        except FreshnessViolation:
            caught = True
        assert caught


# ---------------------------------------------------------------------------
# register_policy / get_policy
# ---------------------------------------------------------------------------


class TestRegisterPolicy:
    def test_register_new_policy(self):
        new_policy = FeatureFreshnessPolicy(
            feature_name="test_feature_xyz",
            warn_after_seconds=10,
            fail_after_seconds=30,
        )
        register_policy(new_policy)
        assert get_policy("test_feature_xyz") is new_policy
        # Cleanup
        del FRESHNESS_POLICIES["test_feature_xyz"]

    def test_get_policy_none_for_unknown(self):
        assert get_policy("absolutely_not_registered") is None

    def test_register_replaces_existing(self):
        original = FRESHNESS_POLICIES.get("risk_score")
        replacement = FeatureFreshnessPolicy(
            feature_name="risk_score",
            warn_after_seconds=999,
            fail_after_seconds=9999,
        )
        register_policy(replacement)
        assert get_policy("risk_score") is replacement
        # Restore original
        if original:
            FRESHNESS_POLICIES["risk_score"] = original

    def test_registered_policy_enforced(self):
        custom = FeatureFreshnessPolicy(
            feature_name="custom_fresh_feat",
            warn_after_seconds=5,
            fail_after_seconds=10,
        )
        register_policy(custom)

        # 20s old → should fail
        with pytest.raises(FreshnessViolation):
            check_feature_freshness("custom_fresh_feat", ts(-20), now=BASE)

        # 7s old → should warn
        with pytest.warns(FreshnessWarning):
            check_feature_freshness(
                "custom_fresh_feat", ts(-7), now=BASE, on_warn=None, on_fail=None
            )

        # Cleanup
        del FRESHNESS_POLICIES["custom_fresh_feat"]
