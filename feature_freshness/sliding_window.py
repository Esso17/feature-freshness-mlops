"""
Sliding window over timestamped events.

All time comparisons use UTC-aware datetimes.  If a naive datetime is
received it is assumed to be UTC and converted automatically.

Complexity
----------
add()    O(k) amortized — k is the number of entries evicted (amortized O(1)
         per event over the lifetime of the window).
count()  O(k + n) — k evictions, then O(n) trivial.
sum()    O(k + n) — linear scan of the deque.
mean()   O(k + n) — delegates to sum() and count().

Memory   O(n) where n = live events inside the window.
"""

from collections import deque
from datetime import datetime, timezone
from typing import Deque, Optional, Tuple


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


class SlidingWindow:
    """
    Fixed-duration sliding window over (timestamp, value) pairs.

    Parameters
    ----------
    window_seconds : float
        How far back in time events are retained.
    """

    def __init__(self, window_seconds: float) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.window_seconds = window_seconds
        self._data: Deque[Tuple[datetime, float]] = deque()

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add(self, value: float, ts: Optional[datetime] = None) -> None:
        """Append an event and evict entries that have expired."""
        if ts is None:
            ts = datetime.now(timezone.utc)
        ts = _utc(ts)
        self._evict(ts)
        self._data.append((ts, value))

    def clear(self) -> None:
        """Remove all entries."""
        self._data.clear()

    # ------------------------------------------------------------------
    # Read (accept optional `now` for deterministic testing)
    # ------------------------------------------------------------------

    def count(self, now: Optional[datetime] = None) -> int:
        """Number of events currently inside the window."""
        self._evict(self._now(now))
        return len(self._data)

    def sum(self, now: Optional[datetime] = None) -> float:
        """Sum of values inside the window.  Returns 0.0 for empty window."""
        self._evict(self._now(now))
        return sum(v for _, v in self._data)

    def mean(self, now: Optional[datetime] = None) -> Optional[float]:
        """Mean of values inside the window.  Returns None for empty window."""
        self._evict(self._now(now))
        n = len(self._data)
        if n == 0:
            return None
        return sum(v for _, v in self._data) / n

    def min(self, now: Optional[datetime] = None) -> Optional[float]:
        """Minimum value in the window.  Returns None for empty window."""
        self._evict(self._now(now))
        if not self._data:
            return None
        return min(v for _, v in self._data)

    def max(self, now: Optional[datetime] = None) -> Optional[float]:
        """Maximum value in the window.  Returns None for empty window."""
        self._evict(self._now(now))
        if not self._data:
            return None
        return max(v for _, v in self._data)

    def oldest_timestamp(self, now: Optional[datetime] = None) -> Optional[datetime]:
        """Timestamp of the oldest event still in the window."""
        self._evict(self._now(now))
        return self._data[0][0] if self._data else None

    def newest_timestamp(self, now: Optional[datetime] = None) -> Optional[datetime]:
        """Timestamp of the most-recently added event."""
        self._evict(self._now(now))
        return self._data[-1][0] if self._data else None

    def window_age_seconds(self, now: Optional[datetime] = None) -> Optional[float]:
        """
        Age of the oldest event in the window (seconds).
        Useful as a proxy for 'how fresh is this window?'
        Returns None when the window is empty.
        """
        effective_now = self._now(now)
        oldest = self.oldest_timestamp(effective_now)
        if oldest is None:
            return None
        return (effective_now - oldest).total_seconds()

    def __len__(self) -> int:
        return self.count()

    def __repr__(self) -> str:
        return (
            f"SlidingWindow(window_seconds={self.window_seconds}, "
            f"size={len(self._data)})"
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _now(now: Optional[datetime]) -> datetime:
        if now is None:
            return datetime.now(timezone.utc)
        return _utc(now)

    def _evict(self, now: datetime) -> None:
        cutoff = now.timestamp() - self.window_seconds
        while self._data and self._data[0][0].timestamp() < cutoff:
            self._data.popleft()
