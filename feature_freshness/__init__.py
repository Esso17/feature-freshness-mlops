"""
feature_freshness — companion code for the Medium article:
"Feature Freshness: The Forgotten Problem of MLOps"

Modules
-------
sliding_window  Rolling aggregations over timestamped events.
freshness       Age calculation and SLA enforcement.
feature_store   In-process streaming feature store.
policies        Per-feature freshness policies and metric hooks.
"""

from feature_freshness.sliding_window import SlidingWindow
from feature_freshness.freshness import (
    feature_age_seconds,
    FeatureFreshnessPolicy,
    FreshnessViolation,
    FreshnessWarning,
    check_freshness,
)
from feature_freshness.feature_store import (
    Event,
    FeatureRecord,
    StaleFeatureError,
    FeatureStore,
)
from feature_freshness.policies import (
    FRESHNESS_POLICIES,
    check_feature_freshness,
)

__all__ = [
    "SlidingWindow",
    "feature_age_seconds",
    "FeatureFreshnessPolicy",
    "FreshnessViolation",
    "FreshnessWarning",
    "check_freshness",
    "Event",
    "FeatureRecord",
    "StaleFeatureError",
    "FeatureStore",
    "FRESHNESS_POLICIES",
    "check_feature_freshness",
]
