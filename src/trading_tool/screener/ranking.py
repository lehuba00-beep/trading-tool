"""Sortierung und Gruppierung der Treffer."""

from __future__ import annotations

from collections import defaultdict

from ..domain.enums import Horizon
from ..domain.models import Signal

SORT_KEYS = {
    "score": lambda s: -s.score,
    "name": lambda s: s.name.lower(),
    "umsatz": lambda s: -(s.metrics.get("umsatz_20d_eur") or 0),
    "vola": lambda s: (s.metrics.get("vola_ann_pct") or 0),
    "abstand_hoch": lambda s: (s.metrics.get("abstand_52w_hoch_pct") or 999),
    "perf_20d": lambda s: -(s.metrics.get("perf_20d_pct") or 0),
}


def sort_signals(signals: list[Signal], key: str = "score") -> list[Signal]:
    # Bei Punktgleichstand entscheidet die Liquiditaet: zwei Titel mit
    # identischem Score sind nicht gleich handelbar.
    primary = SORT_KEYS.get(key, SORT_KEYS["score"])
    return sorted(signals, key=lambda s: (primary(s), -(s.metrics.get("umsatz_20d_eur") or 0)))


def group_by_horizon(signals: list[Signal]) -> dict[Horizon, list[Signal]]:
    grouped: dict[Horizon, list[Signal]] = defaultdict(list)
    for signal in signals:
        grouped[signal.horizon].append(signal)
    return dict(grouped)
