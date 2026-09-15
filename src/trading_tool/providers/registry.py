"""Auswahl der Kursquelle und Fallback-Kette."""

from __future__ import annotations

import logging
import time
from datetime import date
from pathlib import Path

import pandas as pd

from ..config import Settings
from .base import PriceProvider, ProviderError
from .csv_provider import CsvProvider
from .stooq_provider import StooqProvider
from .yfinance_provider import YFinanceProvider

log = logging.getLogger(__name__)


def build_provider(name: str, settings: Settings) -> PriceProvider:
    if name == "yfinance":
        return YFinanceProvider(pause=settings.provider.request_pause_seconds)
    if name == "stooq":
        return StooqProvider()
    if name == "csv":
        return CsvProvider(settings.data_dir / "csv")
    raise ValueError(f"Unbekannte Kursquelle: {name}")


class ProviderChain:
    """Primaerquelle mit Rueckfallquellen.

    Wichtig fuer die Symbolwahl: Jede Quelle hat ihre eigene Schreibweise
    (Yahoo ``SAP.DE``, Stooq ``sap.de``). Deshalb bekommt die Kette je Quelle
    ein eigenes Symbol uebergeben, nicht ein gemeinsames.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        names = [settings.provider.primary, *settings.provider.fallback]
        self.providers: list[PriceProvider] = []
        for name in names:
            try:
                self.providers.append(build_provider(name, settings))
            except ValueError:
                log.warning("Kursquelle %s uebersprungen (unbekannt)", name)

    @property
    def primary_name(self) -> str:
        return self.providers[0].name if self.providers else "-"

    def fetch(self, symbols: dict[str, str], start: date, end: date) -> tuple[pd.DataFrame, str]:
        """``symbols`` bildet Providername auf das dort gueltige Symbol ab."""
        last_error: Exception | None = None
        for provider in self.providers:
            symbol = symbols.get(provider.name)
            if not symbol:
                continue
            for attempt in range(self.settings.provider.max_retries + 1):
                try:
                    frame = provider.fetch_bars(symbol, start, end)
                    if not frame.empty:
                        return frame, provider.name
                    break  # leer heisst 'nicht gefunden' - Wiederholung hilft nicht
                except ProviderError as exc:
                    last_error = exc
                    if attempt < self.settings.provider.max_retries:
                        time.sleep(1.5 * (attempt + 1))
                    else:
                        log.warning("%s: %s", provider.name, exc)
            time.sleep(self.settings.provider.request_pause_seconds)

        if last_error is not None:
            log.debug("Alle Quellen fehlgeschlagen: %s", last_error)
        return pd.DataFrame(), ""

    def fetch_fx(self, currency: str, start: date, end: date) -> pd.Series:
        for provider in self.providers:
            fetch = getattr(provider, "fetch_fx", None)
            if fetch is None:
                continue
            try:
                series = fetch(currency, start, end)
                if not series.empty:
                    return series
            except ProviderError as exc:
                log.warning("FX %s ueber %s: %s", currency, provider.name, exc)
        return pd.Series(dtype="float64")


def csv_fixture_chain(directory: Path, settings: Settings) -> ProviderChain:
    """Kette, die ausschliesslich lokale CSV-Dateien liest (Tests, Offline)."""
    chain = ProviderChain.__new__(ProviderChain)
    chain.settings = settings
    chain.providers = [CsvProvider(directory)]
    return chain
