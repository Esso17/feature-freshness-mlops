"""
In-process streaming feature store.

Supports:
- Point-in-time event ingestion
- Per-entity, per-feature sliding windows
- Scalar (batch-computed) features with freshness metadata
- Freshness enforcement at retrieval time

Complexity
----------
ingest()              O(k) amortized (sliding window eviction).
get_count/sum/mean()  O(k + n) per call.
get_feature_vector()  O(F * (k + n)) where F = number of window features.

Memory
------
O(E * F * W) where E = distinct entities, F = distinct feature names,
W = max events per window.
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional, Tuple

from feature_freshness.freshness import feature_age_seconds


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Event:
    """
    A single timestamped observation tied to an entity.

    Attributes
    ----------
    entity_id : str
        Identifies the entity (user, account, device, …).
    feature_name : str
        Which feature this event contributes to.
    value : float
        Numeric observation (transaction amount, click count, …).
    timestamp : datetime
        When the event occurred.  Defaults to UTC now.
    """

    entity_id: str
    feature_name: str
    value: float
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            object.__setattr__(
                self,
                "timestamp",
                self.timestamp.replace(tzinfo=timezone.utc),
            )


@dataclass
class FeatureRecord:
    """
    A scalar feature value with provenance metadata.

    Attributes
    ----------
    value : Any
        The stored feature value.
    computed_at : datetime
        When the value was computed (drives freshness checks).
    source : str
        Informal label for where this value came from (e.g. 'batch-job').
    """

    value: Any
    computed_at: datetime
    source: str = "unknown"

    @property
    def age_seconds(self) -> float:
        return feature_age_seconds(self.computed_at)


class StaleFeatureError(Exception):
    """
    Raised when a feature's age exceeds the caller's max_age_seconds limit.
    """

    def __init__(
        self,
        entity_id: str,
        feature_name: str,
        age: float,
        limit: float,
    ) -> None:
        self.entity_id = entity_id
        self.feature_name = feature_name
        self.age = age
        self.limit = limit
        super().__init__(
            f"[STALE] entity='{entity_id}' feature='{feature_name}' "
            f"age={age:.1f}s > limit={limit:.1f}s"
        )


# ---------------------------------------------------------------------------
# Feature Store
# ---------------------------------------------------------------------------


class FeatureStore:
    """
    In-process streaming feature store with sliding window support.

    Parameters
    ----------
    window_seconds : float
        Duration of every sliding window kept in this store.
        All window features share the same window duration.
        For different durations per feature, compose multiple FeatureStore
        instances.

    Example
    -------
    >>> store = FeatureStore(window_seconds=300)
    >>> store.ingest(Event("u1", "tx_amount", 120.0))
    >>> store.get_count("u1", "tx_amount")
    1
    """

    def __init__(self, window_seconds: float = 300.0) -> None:
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.window_seconds = window_seconds
        # entity_id -> feature_name -> deque[(timestamp, value)]
        self._windows: Dict[
            str, Dict[str, Deque[Tuple[datetime, float]]]
        ] = defaultdict(lambda: defaultdict(deque))
        # entity_id -> feature_name -> FeatureRecord
        self._scalars: Dict[str, Dict[str, FeatureRecord]] = defaultdict(dict)

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest(self, event: Event) -> None:
        """
        Record an event and evict entries that have left the window.

        Parameters
        ----------
        event : Event
            The observation to store.
        """
        window = self._windows[event.entity_id][event.feature_name]
        window.append((event.timestamp, event.value))
        self._evict(window, event.timestamp)

    def ingest_batch(self, events: List[Event]) -> None:
        """Ingest a list of events in chronological order."""
        for event in events:
            self.ingest(event)

    def set_scalar(
        self,
        entity_id: str,
        feature_name: str,
        value: Any,
        computed_at: Optional[datetime] = None,
        source: str = "unknown",
    ) -> None:
        """
        Store a pre-computed scalar feature (e.g. from a batch pipeline).

        Parameters
        ----------
        entity_id : str
        feature_name : str
        value : Any
            The feature value.
        computed_at : datetime, optional
            When the value was computed.  Defaults to UTC now.
        source : str
            Informal label for provenance tracking.
        """
        if computed_at is None:
            computed_at = datetime.now(timezone.utc)
        if computed_at.tzinfo is None:
            computed_at = computed_at.replace(tzinfo=timezone.utc)
        self._scalars[entity_id][feature_name] = FeatureRecord(
            value=value,
            computed_at=computed_at,
            source=source,
        )

    # ------------------------------------------------------------------
    # Retrieval — scalars
    # ------------------------------------------------------------------

    def get_scalar(
        self,
        entity_id: str,
        feature_name: str,
        max_age_seconds: Optional[float] = None,
        now: Optional[datetime] = None,
    ) -> FeatureRecord:
        """
        Retrieve a scalar feature.

        Parameters
        ----------
        max_age_seconds : float, optional
            If provided, raise StaleFeatureError when age exceeds this limit.
        now : datetime, optional
            Override the current time for deterministic testing.

        Raises
        ------
        KeyError
            Feature has never been written for this entity.
        StaleFeatureError
            Feature exceeds max_age_seconds.
        """
        entity_scalars = self._scalars.get(entity_id, {})
        if feature_name not in entity_scalars:
            raise KeyError(
                f"No scalar feature '{feature_name}' for entity '{entity_id}'"
            )
        record = entity_scalars[feature_name]
        if max_age_seconds is not None:
            age = feature_age_seconds(record.computed_at, now=self._now(now))
            if age >= max_age_seconds:
                raise StaleFeatureError(
                    entity_id, feature_name, age, max_age_seconds
                )
        return record

    # ------------------------------------------------------------------
    # Retrieval — window aggregations
    # ------------------------------------------------------------------

    def get_count(
        self,
        entity_id: str,
        feature_name: str,
        now: Optional[datetime] = None,
    ) -> int:
        window = self._live_window(entity_id, feature_name, now)
        return len(window)

    def get_sum(
        self,
        entity_id: str,
        feature_name: str,
        now: Optional[datetime] = None,
    ) -> float:
        window = self._live_window(entity_id, feature_name, now)
        return sum(v for _, v in window)

    def get_mean(
        self,
        entity_id: str,
        feature_name: str,
        now: Optional[datetime] = None,
    ) -> Optional[float]:
        window = self._live_window(entity_id, feature_name, now)
        if not window:
            return None
        return sum(v for _, v in window) / len(window)

    def get_min(
        self,
        entity_id: str,
        feature_name: str,
        now: Optional[datetime] = None,
    ) -> Optional[float]:
        window = self._live_window(entity_id, feature_name, now)
        return min((v for _, v in window), default=None)

    def get_max(
        self,
        entity_id: str,
        feature_name: str,
        now: Optional[datetime] = None,
    ) -> Optional[float]:
        window = self._live_window(entity_id, feature_name, now)
        return max((v for _, v in window), default=None)

    def get_window_age_seconds(
        self,
        entity_id: str,
        feature_name: str,
        now: Optional[datetime] = None,
    ) -> Optional[float]:
        """
        Age of the oldest event in the window.
        Returns None if the window is empty (no events ingested, or all expired).
        """
        effective_now = self._now(now)
        window = self._live_window(entity_id, feature_name, effective_now)
        if not window:
            return None
        oldest_ts = window[0][0]
        return (effective_now - oldest_ts).total_seconds()

    # ------------------------------------------------------------------
    # Composite retrieval
    # ------------------------------------------------------------------

    def get_feature_vector(
        self,
        entity_id: str,
        scalar_features: Optional[List[str]] = None,
        window_features: Optional[List[Tuple[str, str]]] = None,
        max_scalar_age_seconds: Optional[float] = None,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Build a feature vector for model inference.

        Parameters
        ----------
        entity_id : str
        scalar_features : list of str, optional
            Names of scalar (batch) features to include.
        window_features : list of (feature_name, aggregation) tuples, optional
            Window aggregations to include.
            Supported aggregations: 'count', 'sum', 'mean', 'min', 'max'.
        max_scalar_age_seconds : float, optional
            Freshness limit applied to every scalar feature.
        now : datetime, optional
            Override current time (for testing).

        Returns
        -------
        dict
            Keys are feature names or '<name>_<agg>' for window features.

        Raises
        ------
        StaleFeatureError
            If any scalar feature exceeds max_scalar_age_seconds.
        KeyError
            If a requested scalar feature has never been set.
        ValueError
            If an unknown aggregation is requested.
        """
        effective_now = self._now(now)
        vector: Dict[str, Any] = {}

        for fname in scalar_features or []:
            record = self.get_scalar(entity_id, fname, max_scalar_age_seconds, now=effective_now)
            vector[fname] = record.value

        _AGG_MAP = {
            "count": self.get_count,
            "sum": self.get_sum,
            "mean": self.get_mean,
            "min": self.get_min,
            "max": self.get_max,
        }
        for fname, agg in window_features or []:
            if agg not in _AGG_MAP:
                raise ValueError(
                    f"Unknown aggregation '{agg}'. "
                    f"Supported: {list(_AGG_MAP)}"
                )
            vector[f"{fname}_{agg}"] = _AGG_MAP[agg](
                entity_id, fname, effective_now
            )

        return vector

    # ------------------------------------------------------------------
    # Inspection helpers
    # ------------------------------------------------------------------

    def known_entities(self) -> List[str]:
        """Return all entity IDs that have at least one window event."""
        return list(self._windows.keys())

    def known_scalar_entities(self) -> List[str]:
        """Return all entity IDs that have at least one scalar feature."""
        return list(self._scalars.keys())

    def __repr__(self) -> str:
        return (
            f"FeatureStore(window_seconds={self.window_seconds}, "
            f"entities={len(self._windows)}, "
            f"scalar_entities={len(self._scalars)})"
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _now(now: Optional[datetime]) -> datetime:
        if now is None:
            return datetime.now(timezone.utc)
        if now.tzinfo is None:
            return now.replace(tzinfo=timezone.utc)
        return now

    def _evict(
        self,
        window: Deque[Tuple[datetime, float]],
        now: datetime,
    ) -> None:
        cutoff = now.timestamp() - self.window_seconds
        while window and window[0][0].timestamp() < cutoff:
            window.popleft()

    def _live_window(
        self,
        entity_id: str,
        feature_name: str,
        now: Optional[datetime] = None,
    ) -> Deque[Tuple[datetime, float]]:
        effective_now = self._now(now)
        window = self._windows[entity_id][feature_name]
        self._evict(window, effective_now)
        return window
