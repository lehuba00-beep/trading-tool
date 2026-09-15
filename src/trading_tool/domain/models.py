"""Datenklassen, die zwischen den Schichten wandern."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from .enums import AssetClass, Direction, Horizon, TRStatus


@dataclass(slots=True)
class Instrument:
    isin: str
    name: str
    asset_class: AssetClass
    ticker_yahoo: str = ""
    ticker_stooq: str = ""
    currency: str = "EUR"
    exchange: str = ""
    tr_status: TRStatus = TRStatus.UNKNOWN
    tr_checked_at: date | None = None
    source: str = ""
    notes: str = ""

    @property
    def screenable(self) -> bool:
        """Ohne Yahoo-Ticker gibt es keine Kursreihe und damit kein Signal."""
        return bool(self.ticker_yahoo) and self.tr_status is not TRStatus.UNAVAILABLE


@dataclass(slots=True)
class RuleHit:
    """Ergebnis einer einzelnen Regel zum Auswertungszeitpunkt."""

    rule_id: str
    label: str
    triggered: bool
    weight: float
    required: bool = False


@dataclass(slots=True)
class Signal:
    """Ein Treffer des Screeners fuer genau ein Instrument und eine Strategie."""

    isin: str
    name: str
    strategy: str
    horizon: Horizon
    direction: Direction
    score: float
    as_of: date
    hits: list[RuleHit] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    tr_status: TRStatus = TRStatus.UNKNOWN
    provisional: bool = False
    """True, wenn der letzte Balken noch nicht abgeschlossen ist."""

    @property
    def triggered_labels(self) -> list[str]:
        return [h.label for h in self.hits if h.triggered]

    @property
    def missing_labels(self) -> list[str]:
        return [h.label for h in self.hits if not h.triggered and not h.required]


@dataclass(slots=True)
class ScreenRun:
    id: int | None
    strategy: str
    started_at: datetime
    finished_at: datetime | None = None
    n_instruments: int = 0
    n_hits: int = 0
    provider: str = ""
    status: str = "running"
    message: str = ""
