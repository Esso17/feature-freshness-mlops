"""
Tests for feature_freshness.sliding_window.SlidingWindow.

All tests use explicit timestamps so they are deterministic and
do not rely on wall-clock time.
"""

import pytest
from datetime import datetime, timezone, timedelta

from feature_freshness.sliding_window import SlidingWindow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE = datetime(2026, 6, 28, 10, 0, 0, tzinfo=timezone.utc)


def ts(offset_seconds: float) -> datetime:
    """Return BASE + offset_seconds."""
    return BASE + timedelta(seconds=offset_seconds)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_valid_window(self):
        w = SlidingWindow(window_seconds=300)
        assert w.window_seconds == 300

    def test_zero_raises(self):
        with pytest.raises(ValueError):
            SlidingWindow(window_seconds=0)

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            SlidingWindow(window_seconds=-10)

    def test_repr(self):
        w = SlidingWindow(window_seconds=60)
        assert "60" in repr(w)


# ---------------------------------------------------------------------------
# Empty window behaviour
# ---------------------------------------------------------------------------


class TestEmptyWindow:
    def setup_method(self):
        self.w = SlidingWindow(window_seconds=300)
        self.now = ts(1000)

    def test_count_empty(self):
        assert self.w.count(now=self.now) == 0

    def test_sum_empty(self):
        assert self.w.sum(now=self.now) == 0.0

    def test_mean_empty_returns_none(self):
        assert self.w.mean(now=self.now) is None

    def test_min_empty_returns_none(self):
        assert self.w.min(now=self.now) is None

    def test_max_empty_returns_none(self):
        assert self.w.max(now=self.now) is None

    def test_oldest_timestamp_empty_returns_none(self):
        assert self.w.oldest_timestamp(now=self.now) is None

    def test_newest_timestamp_empty_returns_none(self):
        assert self.w.newest_timestamp(now=self.now) is None

    def test_window_age_empty_returns_none(self):
        assert self.w.window_age_seconds(now=self.now) is None

    def test_len_empty(self):
        assert len(self.w) == 0


# ---------------------------------------------------------------------------
# Single event
# ---------------------------------------------------------------------------


class TestSingleEvent:
    def setup_method(self):
        self.w = SlidingWindow(window_seconds=300)
        self.event_ts = ts(0)
        self.now = ts(10)
        self.w.add(42.0, ts=self.event_ts)

    def test_count_one(self):
        assert self.w.count(now=self.now) == 1

    def test_sum_equals_value(self):
        assert self.w.sum(now=self.now) == 42.0

    def test_mean_equals_value(self):
        assert self.w.mean(now=self.now) == 42.0

    def test_min_equals_value(self):
        assert self.w.min(now=self.now) == 42.0

    def test_max_equals_value(self):
        assert self.w.max(now=self.now) == 42.0

    def test_oldest_equals_event_ts(self):
        assert self.w.oldest_timestamp(now=self.now) == self.event_ts

    def test_newest_equals_event_ts(self):
        assert self.w.newest_timestamp(now=self.now) == self.event_ts

    def test_window_age(self):
        # now is 10s after the event, so age should be 10s
        age = self.w.window_age_seconds(now=self.now)
        assert age == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Multiple events — all inside the window
# ---------------------------------------------------------------------------


class TestMultipleEvents:
    def setup_method(self):
        self.w = SlidingWindow(window_seconds=300)
        self.values = [10.0, 20.0, 30.0, 40.0]
        for i, v in enumerate(self.values):
            self.w.add(v, ts=ts(i * 10))
        self.now = ts(60)  # 60s after BASE, all events within 300s window

    def test_count(self):
        assert self.w.count(now=self.now) == 4

    def test_sum(self):
        assert self.w.sum(now=self.now) == pytest.approx(100.0)

    def test_mean(self):
        assert self.w.mean(now=self.now) == pytest.approx(25.0)

    def test_min(self):
        assert self.w.min(now=self.now) == pytest.approx(10.0)

    def test_max(self):
        assert self.w.max(now=self.now) == pytest.approx(40.0)

    def test_oldest_timestamp(self):
        assert self.w.oldest_timestamp(now=self.now) == ts(0)

    def test_newest_timestamp(self):
        assert self.w.newest_timestamp(now=self.now) == ts(30)


# ---------------------------------------------------------------------------
# Eviction: events that fall outside the window
# ---------------------------------------------------------------------------


class TestEviction:
    def test_all_events_expire(self):
        w = SlidingWindow(window_seconds=60)
        for i in range(5):
            w.add(float(i), ts=ts(i))
        # Move now to 120s after BASE — all events are > 60s old
        assert w.count(now=ts(120)) == 0
        assert w.sum(now=ts(120)) == 0.0

    def test_partial_eviction(self):
        w = SlidingWindow(window_seconds=60)
        # Add 3 old events (outside the window when now=ts(100))
        for i in range(3):
            w.add(1.0, ts=ts(i))
        # Add 2 recent events (inside the window when now=ts(100))
        w.add(10.0, ts=ts(80))
        w.add(20.0, ts=ts(90))

        now = ts(100)
        assert w.count(now=now) == 2
        assert w.sum(now=now) == pytest.approx(30.0)
        assert w.mean(now=now) == pytest.approx(15.0)

    def test_eviction_is_amortised_on_add(self):
        # Events added in order; old ones are evicted on each subsequent add.
        w = SlidingWindow(window_seconds=10)
        for i in range(100):
            w.add(1.0, ts=ts(i))
        # Only events within the last 10 seconds of the last add (ts(99)) survive.
        # ts(89) .. ts(99) = 11 events (inclusive).
        now = ts(100)
        count = w.count(now=now)
        # ts(90) to ts(99) fall inside window [90, 100) — 10 events
        assert 10 <= count <= 11

    def test_boundary_event_included(self):
        # An event exactly at the boundary should still be visible.
        w = SlidingWindow(window_seconds=60)
        w.add(99.0, ts=ts(0))
        # now = ts(60): cutoff = ts(0) exactly. The event timestamp equals cutoff
        # but the cutoff comparison is strictly less-than, so it stays.
        assert w.count(now=ts(60)) == 1

    def test_event_one_second_past_boundary_evicted(self):
        w = SlidingWindow(window_seconds=60)
        w.add(99.0, ts=ts(0))
        # now = ts(61): cutoff = ts(1). The event at ts(0) < ts(1), so evicted.
        assert w.count(now=ts(61)) == 0


# ---------------------------------------------------------------------------
# Naive datetime handling
# ---------------------------------------------------------------------------


class TestNaiveDatetime:
    def test_naive_add_treated_as_utc(self):
        w = SlidingWindow(window_seconds=300)
        naive_ts = datetime(2026, 6, 28, 10, 0, 0)  # no tzinfo
        w.add(5.0, ts=naive_ts)
        # now is 10s later, also naive
        now_naive = datetime(2026, 6, 28, 10, 0, 10)
        assert w.count(now=now_naive) == 1

    def test_mixed_aware_naive(self):
        w = SlidingWindow(window_seconds=300)
        w.add(7.0, ts=BASE)  # aware
        # Query with naive now
        now_naive = datetime(2026, 6, 28, 10, 0, 10)
        assert w.count(now=now_naive) == 1


# ---------------------------------------------------------------------------
# Clear
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear_empties_window(self):
        w = SlidingWindow(window_seconds=300)
        for i in range(5):
            w.add(float(i), ts=ts(i))
        w.clear()
        assert w.count(now=ts(100)) == 0
        assert w.sum(now=ts(100)) == 0.0

    def test_add_after_clear(self):
        w = SlidingWindow(window_seconds=300)
        w.add(1.0, ts=ts(0))
        w.clear()
        w.add(99.0, ts=ts(10))
        assert w.count(now=ts(20)) == 1
        assert w.sum(now=ts(20)) == 99.0


# ---------------------------------------------------------------------------
# Precision / floating-point
# ---------------------------------------------------------------------------


class TestNumerics:
    def test_sum_large_values(self):
        w = SlidingWindow(window_seconds=300)
        for i in range(100):
            w.add(1_000_000.0, ts=ts(i))
        now = ts(200)
        assert w.sum(now=now) == pytest.approx(100_000_000.0)

    def test_mean_precision(self):
        w = SlidingWindow(window_seconds=300)
        w.add(1.0, ts=ts(0))
        w.add(2.0, ts=ts(1))
        w.add(3.0, ts=ts(2))
        assert w.mean(now=ts(10)) == pytest.approx(2.0)

    def test_negative_values(self):
        w = SlidingWindow(window_seconds=300)
        w.add(-10.0, ts=ts(0))
        w.add(5.0, ts=ts(1))
        assert w.sum(now=ts(10)) == pytest.approx(-5.0)
        assert w.min(now=ts(10)) == pytest.approx(-10.0)
        assert w.max(now=ts(10)) == pytest.approx(5.0)
