"""Provider-Protokoll.

Die Kursquelle ist bewusst austauschbar gehalten. Die kostenlosen Quellen
brechen erfahrungsgemaess mehrmals im Jahr; ein Wechsel darf nicht mehr sein
als ein neues Modul und eine Zeile in den Einstellungen.
"""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

import pandas as pd

COLUMNS = ["open", "high", "low", "close", "adj_close", "volume"]


class ProviderError(RuntimeError):
    """Abruf fehlgeschlagen - der Aufrufer entscheidet ueber den Fallback."""


@runtime_checkable
class PriceProvider(Protocol):
    name: str

    def fetch_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Tagesbalken mit DatetimeIndex und den Spalten aus ``COLUMNS``.

        Fehlende Spalten sind erlaubt (nicht jede Quelle liefert Volumen),
        fehlende Zeilen ebenso. Leerer Frame heisst 'nichts gefunden', eine
        ``ProviderError`` heisst 'Quelle gestoert'. Der Unterschied entscheidet,
        ob auf die naechste Quelle ausgewichen wird.
        """
        ...


def normalise(frame: pd.DataFrame) -> pd.DataFrame:
    """Spaltennamen vereinheitlichen, Duplikate und Leerzeilen entfernen."""
    if frame is None or frame.empty:
        return pd.DataFrame(columns=COLUMNS)

    frame = frame.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)

    frame.columns = [str(c).strip().lower().replace(" ", "_") for c in frame.columns]
    frame = frame.rename(columns={"adjclose": "adj_close", "adj_close.": "adj_close"})

    for col in COLUMNS:
        if col not in frame.columns:
            frame[col] = pd.NA
    frame = frame[COLUMNS]

    frame.index = pd.to_datetime(frame.index, errors="coerce", utc=True).tz_localize(None).normalize()
    frame = frame[frame.index.notna()]
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()

    for col in COLUMNS:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")

    # Ohne Schlusskurs ist ein Balken wertlos. adj_close notfalls aus close.
    frame = frame[frame["close"].notna()]
    frame["adj_close"] = frame["adj_close"].fillna(frame["close"])
    return frame
