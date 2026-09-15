"""Kurs-Cache mit inkrementellem Nachladen und Umrechnung nach EUR.

Zwei Aufgaben:

1. **Inkrementell laden.** Nur die fehlenden Tage werden abgerufen. Ohne das
   waere ein Lauf ueber 300 Titel jedes Mal ein Vollabzug - die kostenlosen
   Quellen drosseln lange vorher.
2. **Nach EUR umrechnen.** Rohkurse bleiben in Originalwaehrung gespeichert,
   die Umrechnung passiert beim Lesen. So bleibt die Quelle rekonstruierbar und
   ein spaeter korrigierter Wechselkurs wirkt rueckwirkend.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, timedelta

import pandas as pd

from ..config import Settings
from ..domain.models import Instrument
from ..providers.registry import ProviderChain
from .repositories import BarRepo, FxRepo

log = logging.getLogger(__name__)

# Yahoo notiert britische Titel in Pence, nicht in Pfund.
SUBUNIT_FACTOR = {"GBP": 1.0, "GBp": 100.0, "GBX": 100.0, "ZAc": 100.0, "ILA": 100.0}

# Ueberlappung beim Nachladen: Schlusskurse werden nachtraeglich korrigiert,
# und ein Wochenende ohne Handel darf nicht als Luecke erscheinen.
REFETCH_OVERLAP_DAYS = 7


class PriceCache:
    def __init__(self, conn: sqlite3.Connection, chain: ProviderChain, settings: Settings) -> None:
        self.bars = BarRepo(conn)
        self.fx = FxRepo(conn)
        self.chain = chain
        self.settings = settings
        self._fx_cache: dict[str, pd.Series] = {}

    # ---------------------------------------------------------------- Kurse

    def refresh(self, instrument: Instrument, today: date | None = None) -> int:
        """Fehlende Balken nachladen. Liefert die Anzahl geschriebener Zeilen."""
        today = today or date.today()
        provider_name = self.chain.primary_name
        last = self.bars.last_date(instrument.isin, provider_name)

        if last is None:
            start = today - timedelta(days=self.settings.provider.history_days)
        else:
            if last >= today:
                return 0
            start = last - timedelta(days=REFETCH_OVERLAP_DAYS)

        symbols = {"yfinance": instrument.ticker_yahoo, "csv": instrument.ticker_yahoo}
        if instrument.ticker_stooq:
            symbols["stooq"] = instrument.ticker_stooq

        frame, source = self.chain.fetch(symbols, start, today)
        if frame.empty or not source:
            return 0
        return self.bars.upsert(instrument.isin, source, frame)

    def raw_bars(self, instrument: Instrument) -> pd.DataFrame:
        return self.bars.load(instrument.isin)

    def bars_in_base_currency(self, instrument: Instrument) -> pd.DataFrame:
        """Kursreihe in der Basiswaehrung (EUR).

        Das Volumen bleibt unangetastet - es ist eine Stueckzahl, keine
        Geldgroesse. Der Umsatz wird spaeter aus umgerechnetem Kurs mal
        Stueckzahl gebildet.
        """
        frame = self.raw_bars(instrument)
        if frame.empty:
            return frame

        base = self.settings.screening.base_currency.upper()
        currency = (instrument.currency or base).strip()
        factor = SUBUNIT_FACTOR.get(currency, 1.0)
        code = "GBP" if currency in {"GBp", "GBX"} else currency.upper()

        if factor != 1.0:
            for col in ("open", "high", "low", "close", "adj_close"):
                frame[col] = frame[col] / factor

        if code == base:
            return frame

        rates = self._rates(code, frame.index)
        if rates is None:
            log.warning(
                "Kein Wechselkurs %s/%s - %s bleibt in Originalwaehrung",
                base, code, instrument.isin,
            )
            return frame

        for col in ("open", "high", "low", "close", "adj_close"):
            frame[col] = frame[col] / rates
        return frame.dropna(subset=["close"])

    # -------------------------------------------------------------- Devisen

    def refresh_fx(self, currencies: set[str], today: date | None = None) -> int:
        today = today or date.today()
        base = self.settings.screening.base_currency.upper()
        written = 0
        for currency in sorted(currencies):
            code = "GBP" if currency in {"GBp", "GBX"} else currency.upper()
            if code == base:
                continue
            last = self.fx.last_date(code)
            start = (
                today - timedelta(days=self.settings.provider.history_days)
                if last is None
                else last - timedelta(days=REFETCH_OVERLAP_DAYS)
            )
            if last is not None and last >= today:
                continue
            series = self.chain.fetch_fx(code, start, today)
            if not series.empty:
                written += self.fx.upsert(code, series)
                self._fx_cache.pop(code, None)
        return written

    def _rates(self, code: str, index: pd.DatetimeIndex) -> pd.Series | None:
        if code not in self._fx_cache:
            self._fx_cache[code] = self.fx.load(code)
        series = self._fx_cache[code]
        if series.empty:
            return None
        # Auf den Kursindex ziehen: Feiertage der Devisenseite duerfen keine
        # Luecke in der Kursreihe erzeugen.
        aligned = series.reindex(series.index.union(index)).ffill().reindex(index)
        return aligned.bfill()
