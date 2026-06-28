"""
Tests for feature_freshness.feature_store:
  - Event
  - FeatureRecord
  - StaleFeatureError
  - FeatureStore (ingestion, retrieval, freshness, composite vector)
"""

import pytest
from datetime import datetime, timezone, timedelta

from feature_freshness.feature_store import (
    Event,
    FeatureRecord,
    StaleFeatureError,
    FeatureStore,
)


BASE = datetime(2026, 6, 28, 12, 0, 0, tzinfo=timezone.utc)


def ts(offset_seconds: float) -> datetime:
    return BASE + timedelta(seconds=offset_seconds)


# ---------------------------------------------------------------------------
# Event
# ---------------------------------------------------------------------------


class TestEvent:
    def test_creation(self):
        e = Event(entity_id="u1", feature_name="tx", value=100.0, timestamp=BASE)
        assert e.entity_id == "u1"
        assert e.feature_name == "tx"
        assert e.value == 100.0
        assert e.timestamp == BASE

    def test_default_timestamp_is_utc_aware(self):
        e = Event("u1", "tx", 1.0)
        assert e.timestamp.tzinfo is not None

    def test_naive_timestamp_coerced_to_utc(self):
        naive = datetime(2026, 6, 28, 12, 0, 0)
        e = Event("u1", "tx", 1.0, timestamp=naive)
        assert e.timestamp.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# FeatureRecord
# ---------------------------------------------------------------------------


class TestFeatureRecord:
    def test_creation(self):
        rec = FeatureRecord(value=42, computed_at=BASE, source="batch-job")
        assert rec.value == 42
        assert rec.source == "batch-job"

    def test_age_seconds_is_positive(self):
        # Uses wall-clock internally; just check it's a non-negative number.
        rec = FeatureRecord(value=1, computed_at=BASE)
        age = rec.age_seconds
        assert isinstance(age, float)
        assert age >= 0

    def test_default_source(self):
        rec = FeatureRecord(value=1, computed_at=BASE)
        assert rec.source == "unknown"


# ---------------------------------------------------------------------------
# StaleFeatureError
# ---------------------------------------------------------------------------


class TestStaleFeatureError:
    def test_is_exception(self):
        exc = StaleFeatureError("u1", "tx", 500.0, 300.0)
        assert isinstance(exc, Exception)

    def test_attributes(self):
        exc = StaleFeatureError("u1", "tx", 500.0, 300.0)
        assert exc.entity_id == "u1"
        assert exc.feature_name == "tx"
        assert exc.age == 500.0
        assert exc.limit == 300.0

    def test_str_contains_entity_and_feature(self):
        exc = StaleFeatureError("u1", "tx", 500.0, 300.0)
        assert "u1" in str(exc)
        assert "tx" in str(exc)


# ---------------------------------------------------------------------------
# FeatureStore — construction
# ---------------------------------------------------------------------------


class TestFeatureStoreConstruction:
    def test_default_window(self):
        store = FeatureStore()
        assert store.window_seconds == 300.0

    def test_custom_window(self):
        store = FeatureStore(window_seconds=60)
        assert store.window_seconds == 60

    def test_zero_window_raises(self):
        with pytest.raises(ValueError):
            FeatureStore(window_seconds=0)

    def test_repr(self):
        store = FeatureStore(window_seconds=120)
        assert "120" in repr(store)


# ---------------------------------------------------------------------------
# FeatureStore — ingest / window retrieval
# ---------------------------------------------------------------------------


class TestFeatureStoreIngestion:
    def setup_method(self):
        self.store = FeatureStore(window_seconds=300)
        self.entity = "user_42"

    def test_ingest_and_count(self):
        for i in range(5):
            self.store.ingest(Event(self.entity, "tx", 10.0, ts(i * 10)))
        now = ts(60)
        assert self.store.get_count(self.entity, "tx", now=now) == 5

    def test_ingest_and_sum(self):
        amounts = [10.0, 20.0, 30.0]
        for i, a in enumerate(amounts):
            self.store.ingest(Event(self.entity, "tx", a, ts(i * 10)))
        assert self.store.get_sum(self.entity, "tx", now=ts(40)) == pytest.approx(60.0)

    def test_ingest_and_mean(self):
        for i, v in enumerate([1.0, 2.0, 3.0]):
            self.store.ingest(Event(self.entity, "tx", v, ts(i * 5)))
        assert self.store.get_mean(self.entity, "tx", now=ts(30)) == pytest.approx(2.0)

    def test_ingest_and_min_max(self):
        for v in [50.0, 10.0, 90.0, 30.0]:
            self.store.ingest(Event(self.entity, "tx", v, ts(0)))
        assert self.store.get_min(self.entity, "tx", now=ts(10)) == pytest.approx(10.0)
        assert self.store.get_max(self.entity, "tx", now=ts(10)) == pytest.approx(90.0)

    def test_empty_entity_returns_zero_count(self):
        assert self.store.get_count("nonexistent", "tx", now=ts(10)) == 0

    def test_empty_entity_returns_none_mean(self):
        assert self.store.get_mean("nonexistent", "tx", now=ts(10)) is None

    def test_ingest_batch(self):
        events = [
            Event(self.entity, "tx", float(i), ts(i * 5))
            for i in range(10)
        ]
        self.store.ingest_batch(events)
        assert self.store.get_count(self.entity, "tx", now=ts(60)) == 10


# ---------------------------------------------------------------------------
# FeatureStore — window eviction
# ---------------------------------------------------------------------------


class TestFeatureStoreEviction:
    def test_old_events_evicted(self):
        store = FeatureStore(window_seconds=60)
        entity = "u1"
        # Old events
        for i in range(3):
            store.ingest(Event(entity, "tx", 99.0, ts(i)))
        # Recent events
        store.ingest(Event(entity, "tx", 1.0, ts(90)))
        store.ingest(Event(entity, "tx", 2.0, ts(95)))

        now = ts(100)
        assert store.get_count(entity, "tx", now=now) == 2
        assert store.get_sum(entity, "tx", now=now) == pytest.approx(3.0)

    def test_all_events_expire(self):
        store = FeatureStore(window_seconds=60)
        entity = "u1"
        for i in range(5):
            store.ingest(Event(entity, "tx", 1.0, ts(i)))
        # Way beyond window
        assert store.get_count(entity, "tx", now=ts(1000)) == 0

    def test_entity_isolation(self):
        store = FeatureStore(window_seconds=300)
        store.ingest(Event("u1", "tx", 100.0, ts(0)))
        store.ingest(Event("u2", "tx", 200.0, ts(0)))
        assert store.get_sum("u1", "tx", now=ts(10)) == pytest.approx(100.0)
        assert store.get_sum("u2", "tx", now=ts(10)) == pytest.approx(200.0)

    def test_feature_isolation_per_entity(self):
        store = FeatureStore(window_seconds=300)
        entity = "u1"
        store.ingest(Event(entity, "tx_amount", 50.0, ts(0)))
        store.ingest(Event(entity, "login_count", 3.0, ts(0)))
        assert store.get_sum(entity, "tx_amount", now=ts(10)) == pytest.approx(50.0)
        assert store.get_sum(entity, "login_count", now=ts(10)) == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# FeatureStore — window age
# ---------------------------------------------------------------------------


class TestFeatureStoreWindowAge:
    def test_window_age_empty_returns_none(self):
        store = FeatureStore(window_seconds=300)
        assert store.get_window_age_seconds("u1", "tx", now=ts(0)) is None

    def test_window_age_single_event(self):
        store = FeatureStore(window_seconds=300)
        store.ingest(Event("u1", "tx", 1.0, ts(0)))
        # now = ts(50), oldest event at ts(0) → age = 50s
        age = store.get_window_age_seconds("u1", "tx", now=ts(50))
        assert age == pytest.approx(50.0)

    def test_window_age_multiple_events(self):
        store = FeatureStore(window_seconds=300)
        store.ingest(Event("u1", "tx", 1.0, ts(0)))   # oldest
        store.ingest(Event("u1", "tx", 1.0, ts(50)))
        store.ingest(Event("u1", "tx", 1.0, ts(100)))
        # Oldest is at ts(0), now=ts(150) → age = 150s
        age = store.get_window_age_seconds("u1", "tx", now=ts(150))
        assert age == pytest.approx(150.0)


# ---------------------------------------------------------------------------
# FeatureStore — scalar features
# ---------------------------------------------------------------------------


class TestFeatureStoreScalar:
    def setup_method(self):
        self.store = FeatureStore()
        self.entity = "u99"

    def test_set_and_get_scalar(self):
        self.store.set_scalar(self.entity, "account_age_days", 180, computed_at=ts(0))
        record = self.store.get_scalar(self.entity, "account_age_days")
        assert record.value == 180

    def test_get_missing_scalar_raises_keyerror(self):
        with pytest.raises(KeyError):
            self.store.get_scalar("nonexistent", "any_feature")

    def test_scalar_freshness_passes(self):
        self.store.set_scalar(
            self.entity, "risk_score", 0.78, computed_at=ts(-100)
        )
        # max_age_seconds=3600, feature is 100s old — should not raise
        record = self.store.get_scalar(
            self.entity, "risk_score", max_age_seconds=3600, now=BASE
        )
        assert record.value == pytest.approx(0.78)

    def test_scalar_freshness_fails(self):
        self.store.set_scalar(
            self.entity, "risk_score", 0.78, computed_at=ts(-500)
        )
        with pytest.raises(StaleFeatureError) as exc_info:
            self.store.get_scalar(
                self.entity, "risk_score", max_age_seconds=300, now=BASE
            )
        exc = exc_info.value
        assert exc.feature_name == "risk_score"
        assert exc.limit == 300.0

    def test_scalar_overwrite(self):
        self.store.set_scalar(self.entity, "score", 0.5, computed_at=ts(-200))
        self.store.set_scalar(self.entity, "score", 0.9, computed_at=ts(-10))
        record = self.store.get_scalar(self.entity, "score")
        assert record.value == pytest.approx(0.9)

    def test_scalar_source_stored(self):
        self.store.set_scalar(
            self.entity, "age", 42, computed_at=ts(0), source="daily-batch"
        )
        record = self.store.get_scalar(self.entity, "age")
        assert record.source == "daily-batch"

    def test_naive_computed_at_coerced(self):
        naive = datetime(2026, 6, 28, 12, 0, 0)
        self.store.set_scalar(self.entity, "feat", 1, computed_at=naive)
        record = self.store.get_scalar(self.entity, "feat")
        assert record.computed_at.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# FeatureStore — get_feature_vector
# ---------------------------------------------------------------------------


class TestFeatureVector:
    def setup_method(self):
        self.store = FeatureStore(window_seconds=300)
        self.entity = "u_vector"
        # Scalar feature: account age
        self.store.set_scalar(
            self.entity, "account_age_days", 200, computed_at=ts(-3600)
        )
        # Window events: transaction amounts over the last 5 minutes
        for i, amount in enumerate([50.0, 100.0, 200.0, 75.0]):
            self.store.ingest(Event(self.entity, "tx_amount", amount, ts(i * 30)))
        self.now = ts(150)

    def test_scalar_in_vector(self):
        vec = self.store.get_feature_vector(
            self.entity,
            scalar_features=["account_age_days"],
            now=self.now,
        )
        assert vec["account_age_days"] == 200

    def test_window_count_in_vector(self):
        vec = self.store.get_feature_vector(
            self.entity,
            window_features=[("tx_amount", "count")],
            now=self.now,
        )
        assert vec["tx_amount_count"] == 4

    def test_window_sum_in_vector(self):
        vec = self.store.get_feature_vector(
            self.entity,
            window_features=[("tx_amount", "sum")],
            now=self.now,
        )
        assert vec["tx_amount_sum"] == pytest.approx(425.0)

    def test_window_mean_in_vector(self):
        vec = self.store.get_feature_vector(
            self.entity,
            window_features=[("tx_amount", "mean")],
            now=self.now,
        )
        assert vec["tx_amount_mean"] == pytest.approx(106.25)

    def test_window_min_max_in_vector(self):
        vec = self.store.get_feature_vector(
            self.entity,
            window_features=[
                ("tx_amount", "min"),
                ("tx_amount", "max"),
            ],
            now=self.now,
        )
        assert vec["tx_amount_min"] == pytest.approx(50.0)
        assert vec["tx_amount_max"] == pytest.approx(200.0)

    def test_combined_scalar_and_window(self):
        vec = self.store.get_feature_vector(
            self.entity,
            scalar_features=["account_age_days"],
            window_features=[("tx_amount", "count"), ("tx_amount", "sum")],
            now=self.now,
        )
        assert set(vec.keys()) == {
            "account_age_days",
            "tx_amount_count",
            "tx_amount_sum",
        }

    def test_stale_scalar_raises(self):
        # account_age_days was computed at ts(-3600); now=ts(150) → age=3750s > 300s
        with pytest.raises(StaleFeatureError):
            self.store.get_feature_vector(
                self.entity,
                scalar_features=["account_age_days"],
                max_scalar_age_seconds=300,
                now=self.now,  # ts(150), feature computed at ts(-3600) → age=3750s
            )

    def test_unknown_aggregation_raises(self):
        with pytest.raises(ValueError):
            self.store.get_feature_vector(
                self.entity,
                window_features=[("tx_amount", "median")],  # not supported
                now=self.now,
            )

    def test_empty_vector_when_no_features_requested(self):
        vec = self.store.get_feature_vector(self.entity, now=self.now)
        assert vec == {}


# ---------------------------------------------------------------------------
# FeatureStore — known_entities helpers
# ---------------------------------------------------------------------------


class TestKnownEntities:
    def test_known_entities_empty(self):
        store = FeatureStore()
        assert store.known_entities() == []

    def test_known_entities_after_ingest(self):
        store = FeatureStore()
        store.ingest(Event("u1", "tx", 1.0, ts(0)))
        store.ingest(Event("u2", "tx", 1.0, ts(0)))
        assert set(store.known_entities()) == {"u1", "u2"}

    def test_known_scalar_entities(self):
        store = FeatureStore()
        store.set_scalar("u1", "feat", 1, computed_at=ts(0))
        assert "u1" in store.known_scalar_entities()
