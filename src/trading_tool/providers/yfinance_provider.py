"""Yahoo Finance ueber die Bibliothek ``yfinance``.

Inoffizielle Schnittstelle: breite Abdeckung (Xetra ``.DE``, ETFs, US), aber
undokumentierte Drosselung und gelegentliche Formataenderungen. Deshalb hier
defensiv: jede Abweichung vom erwarteten Format wird zur ProviderError, damit
der Registry-Fallback greifen kann statt stillschweigend leere Reihen zu liefern.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from .base import ProviderError, normalise

log = logging.getLogger(__name__)


class YFinanceProvider:
    name = "yfinance"

    def __init__(self, pause: float = 0.4) -> None:
        self.pause = pause

    def fetch_bars(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        try:
            import yfinance as yf
        except ImportError as exc:  # pragma: no cover
            raise ProviderError("yfinance ist nicht installiert") from exc

        try:
            ticker = yf.Ticker(symbol)
            raw = ticker.history(
                start=start.isoformat(),
                end=(end + timedelta(days=1)).isoformat(),
                interval="1d",
                auto_adjust=False,
                actions=False,
                raise_errors=False,
            )
        except Exception as exc:  # yfinance wirft alles Moegliche
            raise ProviderError(f"yfinance {symbol}: {exc}") from exc

        if raw is None:
            raise ProviderError(f"yfinance {symbol}: keine Antwort")
        return normalise(raw)

    def fetch_fx(self, currency: str, start: date, end: date) -> pd.Series:
        """Einheiten ``currency`` je 1 EUR."""
        frame = self.fetch_bars(f"EUR{currency.upper()}=X", start, end)
        return frame["close"].dropna()
