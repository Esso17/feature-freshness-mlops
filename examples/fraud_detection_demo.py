"""
Fraud Detection Demo — end-to-end walkthrough of feature freshness concepts.

Demonstrates the exact failure scenario from the article:
  - A model that depends on transaction_count_last_5min
  - What happens when that feature goes stale
  - How freshness checks catch the problem before inference

Run:
    python examples/fraud_detection_demo.py
"""

import warnings
from datetime import datetime, timezone, timedelta
from typing import Any, Dict

from feature_freshness import (
    Event,
    FeatureStore,
    StaleFeatureError,
    FreshnessViolation,
    FreshnessWarning,
    check_feature_freshness,
)
from feature_freshness.freshness import feature_age_seconds, FeatureFreshnessPolicy
from feature_freshness.policies import register_policy, FRESHNESS_POLICIES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEPARATOR = "-" * 70


def banner(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def section(title: str) -> None:
    print(f"\n{SEPARATOR}")
    print(f"  {title}")
    print(f"{SEPARATOR}")


# ---------------------------------------------------------------------------
# 1. Basic freshness measurement
# ---------------------------------------------------------------------------

banner("1. Feature Age Calculation")

now = datetime.now(timezone.utc)
feature_timestamp = now - timedelta(minutes=8, seconds=23)

age = feature_age_seconds(feature_timestamp, now=now)
print(f"  Feature computed at:  {feature_timestamp.strftime('%H:%M:%S')} UTC")
print(f"  Current time:         {now.strftime('%H:%M:%S')} UTC")
print(f"  Feature age:          {age:.1f} seconds  ({age / 60:.1f} minutes)")

if age > 300:
    print("  Status: STALE — exceeds 5-minute threshold")
elif age > 60:
    print("  Status: WARNING — approaching staleness")
else:
    print("  Status: FRESH")


# ---------------------------------------------------------------------------
# 2. Sliding window in action
# ---------------------------------------------------------------------------

banner("2. Sliding Window — Transaction Velocity")

from feature_freshness.sliding_window import SlidingWindow

window_5m = SlidingWindow(window_seconds=300)

# Simulate 8 transactions over the last 4 minutes
base_ts = now - timedelta(minutes=4)
transactions = [
    (0,   12.50,  "coffee"),
    (30,  1200.00, "electronics"),   # suspicious: large jump
    (60,  45.00,  "grocery"),
    (90,  8.99,   "coffee"),
    (120, 1500.00, "jewelry"),       # suspicious: second large amount
    (150, 22.00,  "pharmacy"),
    (180, 89.00,  "restaurant"),
    (210, 340.00, "electronics"),    # suspicious: third large amount
]

print("\n  Ingesting transactions:")
for offset, amount, merchant in transactions:
    ts = base_ts + timedelta(seconds=offset)
    window_5m.add(amount, ts=ts)
    print(f"    +{offset:3d}s  ${amount:8.2f}  {merchant}")

print(f"\n  Window stats (last 5 minutes):")
print(f"    Count:   {window_5m.count(now=now)}")
print(f"    Sum:     ${window_5m.sum(now=now):.2f}")
print(f"    Mean:    ${window_5m.mean(now=now):.2f}")
print(f"    Max:     ${window_5m.max(now=now):.2f}")
print(f"    Min:     ${window_5m.min(now=now):.2f}")
print(f"    Window age: {window_5m.window_age_seconds(now=now):.1f}s")


# ---------------------------------------------------------------------------
# 3. Feature store — building a fraud feature vector
# ---------------------------------------------------------------------------

banner("3. Feature Store — Fraud Feature Vector")

store = FeatureStore(window_seconds=300)
entity = "user_9821"

# Batch feature: account metadata (from nightly job, 6 hours ago)
store.set_scalar(
    entity,
    "account_age_days",
    value=142,
    computed_at=now - timedelta(hours=6),
    source="nightly-batch",
)
store.set_scalar(
    entity,
    "daily_spending_avg",
    value=87.50,
    computed_at=now - timedelta(hours=2),
    source="hourly-batch",
)
store.set_scalar(
    entity,
    "risk_score",
    value=0.12,
    computed_at=now - timedelta(minutes=25),
    source="risk-service",
)

# Streaming events: same 8 transactions
for offset, amount, _ in transactions:
    event_ts = base_ts + timedelta(seconds=offset)
    store.ingest(Event(entity, "tx_amount", amount, event_ts))

# Retrieve a combined feature vector
vector = store.get_feature_vector(
    entity_id=entity,
    scalar_features=["account_age_days", "daily_spending_avg", "risk_score"],
    window_features=[
        ("tx_amount", "count"),
        ("tx_amount", "sum"),
        ("tx_amount", "mean"),
        ("tx_amount", "max"),
    ],
    max_scalar_age_seconds=86400,  # 24h for batch features
    now=now,
)

print("\n  Feature vector:")
for key, val in vector.items():
    if isinstance(val, float):
        print(f"    {key:<30} {val:.2f}")
    else:
        print(f"    {key:<30} {val}")


# ---------------------------------------------------------------------------
# 4. The postmortem scenario: stale features
# ---------------------------------------------------------------------------

banner("4. The Postmortem Scenario — Stale Feature Detection")

section("4a. Normal operation (fresh features)")

store_fresh = FeatureStore(window_seconds=300)

# Recent events — 2 minutes ago
recent_ts = now - timedelta(minutes=2)
for i, amount in enumerate([500.0, 800.0, 1200.0]):
    store_fresh.ingest(
        Event(entity, "tx_amount", amount, recent_ts + timedelta(seconds=i * 20))
    )

fresh_count = store_fresh.get_count(entity, "tx_amount", now=now)
fresh_age = store_fresh.get_window_age_seconds(entity, "tx_amount", now=now)

print(f"\n  tx_amount count (5m window): {fresh_count}")
print(f"  Window age:                  {fresh_age:.1f}s")
print(f"  Freshness status:            FRESH ✓")

section("4b. Pipeline failure (no new events for 35 minutes)")

store_stale = FeatureStore(window_seconds=300)

# Events from 35 minutes ago — all outside the 5-minute window
stale_ts = now - timedelta(minutes=35)
for i, amount in enumerate([500.0, 800.0, 1200.0]):
    store_stale.ingest(
        Event(entity, "tx_amount", amount, stale_ts + timedelta(seconds=i * 20))
    )

stale_count = store_stale.get_count(entity, "tx_amount", now=now)
print(f"\n  tx_amount count (5m window): {stale_count}   ← looks like no activity!")
print(f"  (Three real transactions exist but are outside the window)")
print(f"  Model sees 0 recent transactions → predicts LOW fraud risk")
print(f"  Actual fraud risk: HIGH  ← MISS")


# ---------------------------------------------------------------------------
# 5. Freshness SLA enforcement
# ---------------------------------------------------------------------------

banner("5. Freshness SLA Enforcement")

section("5a. Custom policy for a high-velocity feature")

# Register a tight SLA for demo purposes
register_policy(FeatureFreshnessPolicy(
    feature_name="demo_velocity",
    warn_after_seconds=30,
    fail_after_seconds=90,
))

test_cases = [
    (ts_offset, label)
    for ts_offset, label in [
        (-10, "10s old  → FRESH"),
        (-45, "45s old  → WARN"),
        (-120, "120s old → FAIL"),
    ]
]

for offset_seconds, label in test_cases:
    feature_ts = now + timedelta(seconds=offset_seconds)
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            age = check_feature_freshness(
                "demo_velocity", feature_ts, now=now,
                on_warn=None, on_fail=None
            )
            if caught:
                print(f"  {label}  (age={age:.0f}s, warned)")
            else:
                print(f"  {label}  (age={age:.0f}s, ok)")
    except FreshnessViolation as exc:
        print(f"  {label}  → FreshnessViolation: {exc}")

# Cleanup demo policy
del FRESHNESS_POLICIES["demo_velocity"]


# ---------------------------------------------------------------------------
# 6. Metric hooks: what to emit to your observability stack
# ---------------------------------------------------------------------------

banner("6. Metric Hooks for Observability")

metrics_log: list = []


def prometheus_warn_hook(feature_name: str, age: float) -> None:
    metrics_log.append({
        "metric": "feature_freshness_warn_total",
        "labels": {"feature": feature_name},
        "age_seconds": age,
    })


def prometheus_fail_hook(feature_name: str, age: float) -> None:
    metrics_log.append({
        "metric": "feature_freshness_fail_total",
        "labels": {"feature": feature_name},
        "age_seconds": age,
    })


# Trigger a warn
stale_ts = now - timedelta(seconds=90)
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    check_feature_freshness(
        "transaction_amount",
        stale_ts,
        now=now,
        on_warn=prometheus_warn_hook,
        on_fail=prometheus_fail_hook,
    )

# Trigger a fail
very_stale_ts = now - timedelta(seconds=400)
try:
    check_feature_freshness(
        "transaction_amount",
        very_stale_ts,
        now=now,
        on_warn=prometheus_warn_hook,
        on_fail=prometheus_fail_hook,
    )
except FreshnessViolation:
    pass

print("\n  Metrics emitted:")
for entry in metrics_log:
    print(
        f"    {entry['metric']}"
        f"{{feature=\"{entry['labels']['feature']}\"}} "
        f"age={entry['age_seconds']:.1f}s"
    )


# ---------------------------------------------------------------------------
# 7. Latency vs freshness tradeoff simulation
# ---------------------------------------------------------------------------

banner("7. Latency vs Freshness Tradeoff")

print("""
  Pipeline strategy         | Avg feature age | Serving latency
  --------------------------+-----------------+----------------
  Hourly batch → Redis      | ~30 minutes     |  <5ms
  5-minute micro-batch      | ~2.5 minutes    |  <5ms
  Per-event Flink + Redis   | Seconds         |  5–15ms
  On-demand computation     | ~0s             |  50–500ms
  30s TTL cache             | <30 seconds     |  <5ms (cache hit)

  Rule of thumb:
    Measure your model's AUC at simulated feature ages (0s, 1m, 5m, 15m).
    Set your SLA where AUC drops more than 2–5% relative.
    Choose your pipeline architecture to meet that SLA.
    Budget infrastructure from there — not the other way around.
""")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

banner("Summary")

print("""
  Key takeaways:

  1. feature_age = serving_time - feature_timestamp
     Track this for every feature, every request.

  2. Freshness SLAs belong in version control alongside model configs.
     When you retrain, review your SLAs.

  3. Separate model quality alerts from data quality alerts.
     Stale features are a pipeline problem, not an ML problem.

  4. Monitor P95 feature age, not just average.
     Tail latency in pipelines = tail staleness in features.

  5. Test your model's sensitivity to feature age offline.
     Don't discover it at 2 AM.

  Many production models do not fail because the model is wrong.
  They fail because the model is looking at the past.
""")
