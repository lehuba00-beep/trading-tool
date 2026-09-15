"""Stooq als Rueckfallquelle.

Nur Tagesschlusskurse, dafuer ohne Schluessel, ohne Drosselungsdrama und seit
Jahren formatstabil. Metadaten liefert Stooq keine - die Zuordnung
ISIN -> Symbol steht in der Universumsliste.
"""

from __future__ import annotations

from datetime import date
from io import StringIO

import pandas as pd
import requests

from .base import ProviderError, normalise

URL = "https://stooq.com/q/d/l/"


class StooqProvider:
    name = "stooq"

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    def fetch_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        params = {
            "s": symbol.lower(),
            "d1": start.strftime("%Y%m%d"),
            "d2": end.strftime("%Y%m%d"),
            "i": "d",
        }
        try:
            response = requests.get(URL, params=params, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ProviderError(f"stooq {symbol}: {exc}") from exc

        text = response.text.strip()
        # Stooq antwortet bei unbekanntem Symbol mit HTTP 200 und Klartext.
        if not text or text.lower().startswith("no data") or "," not in text.splitlines()[0]:
            return normalise(pd.DataFrame())

        frame = pd.read_csv(StringIO(text))
        if "Date" not in frame.columns:
            return normalise(pd.DataFrame())
        return normalise(frame.set_index("Date"))
