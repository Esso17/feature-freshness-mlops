# Feature Freshness — MLOps

> "Many production models do not fail because the model is wrong. They fail because the model is looking at the past."

Pure Python implementation of feature freshness concepts: sliding windows, SLA enforcement, and an in-process feature store. No external dependencies.

---

## Quickstart

```bash
git clone https://github.com/Esso17/feature-freshness-mlops.git
cd feature-freshness-mlops
pip install -r requirements.txt
pytest
python3 examples/fraud_detection_demo.py
```

---

## Structure

```
feature_freshness/
├── sliding_window.py   # Rolling aggregations (count, sum, mean, min, max)
├── freshness.py        # feature_age_seconds, FeatureFreshnessPolicy, check_freshness
├── feature_store.py    # FeatureStore — ingest events, scalar features, freshness guards
└── policies.py         # Per-feature SLA registry with metric hooks

tests/                  # 134 deterministic tests
examples/
└── fraud_detection_demo.py
```

---

## Usage

**Measure feature age**
```python
from feature_freshness import feature_age_seconds
from datetime import datetime, timezone, timedelta

age = feature_age_seconds(datetime.now(timezone.utc) - timedelta(minutes=8))
print(f"{age:.0f}s")  # 480s
```

**Enforce a freshness SLA**
```python
from feature_freshness import FeatureFreshnessPolicy, check_freshness, FreshnessViolation

policy = FeatureFreshnessPolicy("tx_count", warn_after_seconds=60, fail_after_seconds=300)

try:
    check_freshness("tx_count", feature_timestamp, policy)
except FreshnessViolation as e:
    print(e)  # block inference, emit metric
```

**Sliding window over events**
```python
from feature_freshness import SlidingWindow

window = SlidingWindow(window_seconds=300)
window.add(1200.0)
window.add(300.0)

print(window.count(), window.sum(), window.mean())
```

**Feature store with freshness guard**
```python
from feature_freshness import FeatureStore, Event, StaleFeatureError

store = FeatureStore(window_seconds=300)
store.set_scalar("u1", "account_age_days", 142, computed_at=ts)
store.ingest(Event("u1", "tx_amount", 1200.0))

try:
    features = store.get_feature_vector(
        "u1",
        scalar_features=["account_age_days"],
        window_features=[("tx_amount", "count"), ("tx_amount", "sum")],
        max_scalar_age_seconds=86400,
    )
except StaleFeatureError as e:
    print(e)  # pipeline failure detected
```

---

## References

See [references.md](references.md).

## License

MIT
