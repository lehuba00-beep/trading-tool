"""Yahoo Finance ueber die Bibliothek ``yfinance``.

Inoffizielle Schnittstelle: breite Abdeckung (Xetra ``.DE``, ETFs, US), aber
undokumentierte Drosselung und gelegentliche Formataenderungen. Deshalb hier
defensiv: jede Abweichung vom erwarteten Format wird zur ProviderError, damit
der Registry-Fallback greifen kann statt stillschweigend leere Reihen zu liefern.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    from .quotes import Quote

from .base import ProviderError, normalise

log = logging.getLogger(__name__)

# Groesse eines gebuendelten Kursabrufs. Groesser waere schneller, erhoeht aber
# das Risiko, dass ein einzelnes unbekanntes Symbol die ganze Antwort verdirbt.
QUOTE_BATCH_SIZE = 40


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

    def fetch_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        """Aktuellste verfuegbare Kurse fuer mehrere Symbole in einem Abruf.

        Verwendet Tagesbalken statt Minutendaten: Der Balken des laufenden
        Handelstages wird von Yahoo waehrend der Sitzung fortgeschrieben und
        liefert damit den aktuellen Stand *und* den Vortagesschluss fuer die
        Veraenderung - in einer Abfrage statt in zweien. Die Daten sind
        verzoegert; das wird im Ergebnis vermerkt und in der Oberflaeche
        angezeigt.
        """
        from .quotes import Quote

        try:
            import yfinance as yf
        except ImportError:  # pragma: no cover
            raise ProviderError("yfinance ist nicht installiert") from None

        ergebnis: dict[str, Quote] = {}
        jetzt = datetime.now()

        for gruppe in _in_gruppen(symbols, QUOTE_BATCH_SIZE):
            try:
                roh = yf.download(
                    tickers=gruppe, period="5d", interval="1d", group_by="ticker",
                    auto_adjust=False, actions=False, progress=False, threads=False,
                )
            except Exception as exc:
                raise ProviderError(f"Kursabruf fehlgeschlagen: {exc}") from exc

            if roh is None or roh.empty:
                continue

            for symbol in gruppe:
                teil = _teilframe(roh, symbol, len(gruppe))
                werte = _letzte_kurse(teil)
                if werte is None:
                    continue
                kurs, vortag = werte
                ergebnis[symbol] = Quote(
                    symbol=symbol, price=kurs, previous_close=vortag,
                    fetched_at=jetzt, delayed=True,
                )
        return ergebnis

    def fetch_earnings_date(self, symbol: str) -> date | None:
        """Naechster Termin fuer Quartalszahlen.

        Yahoo liefert das Feld in wechselnder Form - mal als Liste von
        Zeitstempeln, mal als einzelner Wert, mal als DataFrame, und fuer ETFs
        und Indizes gar nicht. Deshalb wird hier nichts vorausgesetzt: Was sich
        nicht zweifelsfrei in ein Datum uebersetzen laesst, gilt als unbekannt.
        Ein falsch geratener Termin waere schlechter als gar keiner.
        """
        try:
            import yfinance as yf
        except ImportError:  # pragma: no cover
            return None

        try:
            kalender = yf.Ticker(symbol).calendar
        except Exception as exc:
            log.debug("Kein Termin fuer %s: %s", symbol, exc)
            return None

        rohwert = None
        if isinstance(kalender, dict):
            rohwert = kalender.get("Earnings Date")
        elif kalender is not None and hasattr(kalender, "loc"):
            try:
                rohwert = kalender.loc["Earnings Date"].iloc[0]
            except Exception:
                rohwert = None

        return _als_datum(rohwert)


def _als_datum(wert) -> date | None:
    """Beliebige Datumsdarstellung in ein date uebersetzen - oder None."""
    if wert is None:
        return None
    if isinstance(wert, (list, tuple)):
        # Yahoo liefert bei geschaetzten Terminen eine Spanne; der erste Wert
        # ist der fruehere - und damit der, der fuer eine Warnung zaehlt.
        wert = wert[0] if wert else None
        if wert is None:
            return None
    if isinstance(wert, datetime):
        return wert.date()
    if isinstance(wert, date):
        return wert
    try:
        stempel = pd.Timestamp(wert)
    except (ValueError, TypeError):
        return None
    if pd.isna(stempel):
        return None
    return stempel.date()


def _in_gruppen(werte: list[str], groesse: int):
    for anfang in range(0, len(werte), groesse):
        yield werte[anfang : anfang + groesse]


def _teilframe(roh: pd.DataFrame, symbol: str, anzahl_symbole: int) -> pd.DataFrame | None:
    """Den Teil der Antwort herausloesen, der zu einem Symbol gehoert.

    yfinance liefert bei mehreren Symbolen mehrstufige Spalten, bei einem
    einzelnen flache - und welcher Fall eintritt, haengt an der Version.
    """
    if isinstance(roh.columns, pd.MultiIndex):
        if symbol not in roh.columns.get_level_values(0):
            return None
        return roh[symbol]
    return roh if anzahl_symbole == 1 else None


def _letzte_kurse(frame: pd.DataFrame | None) -> tuple[float, float | None] | None:
    """(aktueller Kurs, Vortagesschluss) aus einem Tagesbalken-Frame."""
    if frame is None or frame.empty:
        return None
    spalte = next((c for c in frame.columns if str(c).lower() == "close"), None)
    if spalte is None:
        return None

    reihe = pd.to_numeric(frame[spalte], errors="coerce").dropna()
    if reihe.empty:
        return None

    kurs = float(reihe.iloc[-1])
    vortag = float(reihe.iloc[-2]) if len(reihe) > 1 else None
    if kurs <= 0:
        return None
    return kurs, vortag
