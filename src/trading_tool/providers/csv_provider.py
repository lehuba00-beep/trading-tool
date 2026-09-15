"""Kursreihen aus lokalen CSV-Dateien.

Zwei Zwecke: Offline-Betrieb, wenn beide Onlinequellen ausfallen, und
reproduzierbare Tests ohne Netz.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from .base import normalise


class CsvProvider:
    name = "csv"

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)

    def fetch_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        path = self.directory / f"{symbol.replace('/', '_')}.csv"
        if not path.exists():
            return normalise(pd.DataFrame())
        frame = pd.read_csv(path)
        date_col = next((c for c in frame.columns if c.lower() in {"date", "datum"}), None)
        if date_col is None:
            return normalise(pd.DataFrame())
        frame = normalise(frame.set_index(date_col))
        mask = (frame.index >= pd.Timestamp(start)) & (frame.index <= pd.Timestamp(end))
        return frame[mask]
