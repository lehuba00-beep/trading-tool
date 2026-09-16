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
    next_earnings: date | None = None
    """Naechster Termin fuer Quartalszahlen, soweit die Quelle ihn kennt."""
    earnings_checked_at: date | None = None

    def earnings_in_days(self, today: date | None = None) -> int | None:
        """Kalendertage bis zu den naechsten Zahlen. None, wenn unbekannt."""
        if self.next_earnings is None:
            return None
        return (self.next_earnings - (today or date.today())).days

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
    quality: str = "ok"
    """Befund der Datenqualitaetspruefung: ok, hinweis oder warnung."""
    quality_notes: list[str] = field(default_factory=list)
    earnings_date: date | None = None
    """Naechster Termin fuer Quartalszahlen, soweit bekannt."""

    def earnings_in_days(self, today: date | None = None) -> int | None:
        if self.earnings_date is None:
            return None
        return (self.earnings_date - (today or date.today())).days

    def earnings_within_holding(self, holding_days: int, today: date | None = None) -> bool:
        """Fallen die Zahlen in die geplante Haltedauer?

        Das ist der Fall, der zaehlt: Ein Ausbruchssignal zwei Tage vor Zahlen
        ist ein Muenzwurf, den die Regeln nicht erkennen koennen.
        """
        tage = self.earnings_in_days(today)
        # Handelstage sind knapp die Haelfte der Kalendertage - grosszuegig
        # gerechnet, damit der Hinweis eher zu frueh als zu spaet kommt.
        return tage is not None and 0 <= tage <= holding_days * 1.5

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
