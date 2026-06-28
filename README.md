# Feature Freshness: The Forgotten Problem of MLOps

Companion code for the Medium article:
**[Feature Freshness: The Forgotten Problem of MLOps]()**

> "Many production models do not fail because the model is wrong.
> They fail because the model is looking at the past."

---

## What this repo covers

| Concept | Module | Description |
|---|---|---|
| Feature age calculation | `freshness.py` | `feature_age = serving_time - feature_timestamp` |
| Freshness SLA enforcement | `freshness.py` | Warn/fail thresholds with metric hooks |
| Sliding window aggregations | `sliding_window.py` | Rolling count, sum, mean, min, max |
| In-process feature store | `feature_store.py` | Ingest, retrieve, freshness checks |
| Per-feature policy registry | `policies.py` | Configurable SLAs per feature name |
| Fraud detection demo | `examples/` | End-to-end walkthrough |

All code uses **only the Python standard library** — no NumPy, no pandas, no external dependencies for the core library.

---

## Project structure

```
feature-freshness-mlops/
├── feature_freshness/
│   ├── __init__.py
│   ├── sliding_window.py     # SlidingWindow — O(1) amortized eviction
│   ├── freshness.py          # feature_age_seconds, FeatureFreshnessPolicy, check_freshness
│   ├── feature_store.py      # Event, FeatureRecord, StaleFeatureError, FeatureStore
│   └── policies.py           # FRESHNESS_POLICIES registry, check_feature_freshness
├── tests/
│   ├── test_sliding_window.py  # 35+ tests: eviction, numerics, edge cases
│   ├── test_freshness.py       # 30+ tests: age calc, policies, warn/fail zones
│   ├── test_feature_store.py   # 40+ tests: ingestion, retrieval, vectors, scalars
│   └── test_policies.py        # 25+ tests: registry, SLA enforcement, hooks
├── examples/
│   └── fraud_detection_demo.py # Full walkthrough of the postmortem scenario
├── references.md               # 35+ academic papers, blog posts, and docs
├── pyproject.toml
└── requirements.txt
```

---

## Quickstart

```bash
# Clone
git clone https://github.com/Esso17/feature-freshness-mlops.git
cd feature-freshness-mlops

# Install dev dependencies
pip install -r requirements.txt

# Run the test suite
pytest

# Run with coverage
pytest --cov=feature_freshness --cov-report=term-missing

# Run the fraud detection demo
python examples/fraud_detection_demo.py
```

---

## Core concepts

### Feature age

```python
from feature_freshness import feature_age_seconds
from datetime import datetime, timezone, timedelta

feature_ts = datetime.now(timezone.utc) - timedelta(minutes=8)
age = feature_age_seconds(feature_ts)

print(f"Feature age: {age:.1f}s")  # Feature age: 480.0s
```

### Freshness SLA enforcement

```python
from feature_freshness import FeatureFreshnessPolicy, check_freshness, FreshnessViolation

policy = FeatureFreshnessPolicy(
    feature_name="transaction_count",
    warn_after_seconds=60,
    fail_after_seconds=300,
)

try:
    age = check_freshness("transaction_count", feature_ts, policy)
except FreshnessViolation as e:
    print(f"Stale: {e}")
```

### Sliding window

```python
from feature_freshness import SlidingWindow
from datetime import datetime, timezone, timedelta

window = SlidingWindow(window_seconds=300)  # 5-minute window

now = datetime.now(timezone.utc)
for i, amount in enumerate([50.0, 200.0, 1500.0, 30.0]):
    window.add(amount, ts=now - timedelta(minutes=4 - i))

print(f"Count: {window.count()}")
print(f"Sum:   {window.sum():.2f}")
print(f"Mean:  {window.mean():.2f}")
```

### Feature store

```python
from feature_freshness import FeatureStore, Event, StaleFeatureError
from datetime import datetime, timezone, timedelta

store = FeatureStore(window_seconds=300)
entity = "user_9821"

# Batch feature (from nightly job)
store.set_scalar(
    entity, "account_age_days",
    value=142,
    computed_at=datetime.now(timezone.utc) - timedelta(hours=6),
    source="nightly-batch",
)

# Streaming events
store.ingest(Event(entity, "tx_amount", 1200.0))
store.ingest(Event(entity, "tx_amount", 300.0))

# Retrieve feature vector with freshness guard
try:
    features = store.get_feature_vector(
        entity_id=entity,
        scalar_features=["account_age_days"],
        window_features=[
            ("tx_amount", "count"),
            ("tx_amount", "sum"),
            ("tx_amount", "mean"),
        ],
        max_scalar_age_seconds=86400,
    )
    print(features)
except StaleFeatureError as e:
    print(f"Pipeline failure detected: {e}")
```

---

## Test suite

```
tests/test_sliding_window.py   — construction, empty window, single event,
                                  multiple events, eviction, naive datetime,
                                  clear, numeric precision
tests/test_freshness.py        — age calculation, policy construction (valid/invalid),
                                  fresh/warn/fail zones, hooks, exception attributes
tests/test_feature_store.py    — Event/FeatureRecord/StaleFeatureError, ingestion,
                                  window eviction, entity isolation, scalar freshness,
                                  feature vectors, unknown aggregations
tests/test_policies.py         — registry validation, SLA tightness, unknown features,
                                  warn/fail zones, hook arguments, register/get policy
```

Run a specific test file:

```bash
pytest tests/test_sliding_window.py -v
```

---

## Production architecture (conceptual)

```
App Events ──┐
DB CDC       ├──► Kafka ──► Flink ──► Redis (online store, <10ms)
             │                            │
Batch Jobs ──┴──────────► Warehouse ──────┤
                                          │
                                     Feature Server
                                          │
                                     Model Server
```

Key SLA targets for fraud detection:
- Streaming features: warn at 60s, fail at 300s
- Batch features: warn at 12h, fail at 24h
- Feature server P99 latency: <10ms

---

## References

See [references.md](references.md) for 35+ citations covering:
- Feature store systems (Feast, Tecton, Hopsworks, Zipline)
- Stream processing (Apache Flink, Kafka, Spark Streaming)
- Production ML case studies (Uber Michelangelo, Airbnb, Netflix, Stripe)
- Academic papers (Hidden Technical Debt, ML Test Score, TFX)

---

## License

MIT
