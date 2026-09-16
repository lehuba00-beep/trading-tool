"""Laufend aktualisierte Kurse.

**Keine Echtzeitkurse.** Yahoo liefert je nach Boerse 15 bis 20 Minuten
verzoegerte Daten; echte Realtime-Kurse gibt es nur ueber einen lizenzierten,
kostenpflichtigen Feed. Was hier entsteht, ist der aktuellste verfuegbare
Kurs - und er wird in der Oberflaeche auch genau so ausgewiesen, mit
Abrufzeitpunkt und Verzoegerungshinweis. Ein Kurs, der so aussieht wie
Realtime, aber keiner ist, waere gefaehrlicher als gar keiner.

Zwei Dinge machen den Dienst alltagstauglich:

* **Buendelung.** Alle sichtbaren Titel werden in einem Abruf geholt, nicht
  einzeln. Eine Trefferliste mit 50 Zeilen wuerde die Quelle sonst binnen
  Minuten drosseln.
* **Zwischenspeicher mit Verfallszeit.** Mehrere Aufrufe innerhalb der
  Verfallszeit werden aus dem Speicher bedient. Die Oberflaeche darf haeufiger
  fragen, als die Quelle vertraegt.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime

from ..domain.models import Instrument

log = logging.getLogger(__name__)

SUBUNIT_FACTOR = {"GBp": 100.0, "GBX": 100.0, "ZAc": 100.0, "ILA": 100.0}


@dataclass(slots=True)
class Quote:
    symbol: str
    price: float
    previous_close: float | None = None
    currency: str = ""
    fetched_at: datetime | None = None
    delayed: bool = True

    @property
    def change_pct(self) -> float | None:
        if not self.previous_close:
            return None
        return (self.price - self.previous_close) / self.previous_close * 100


class QuoteService:
    def __init__(self, chain, cache, settings) -> None:
        self.chain = chain
        self.cache = cache
        self.settings = settings
        self._lock = threading.Lock()
        self._quotes: dict[str, Quote] = {}
        self._fetched: dict[str, datetime] = {}
        self.last_error = ""

    @property
    def enabled(self) -> bool:
        return self.settings.quotes.enabled

    def _provider(self):
        for provider in self.chain.providers:
            if hasattr(provider, "fetch_quotes"):
                return provider
        return None

    def _frisch(self, symbol: str, jetzt: datetime) -> bool:
        stand = self._fetched.get(symbol)
        if stand is None:
            return False
        return (jetzt - stand).total_seconds() < self.settings.quotes.ttl_seconds

    def get(self, instruments: list[Instrument]) -> dict[str, Quote]:
        """Kurse je ISIN, umgerechnet in die Basiswaehrung."""
        if not self.enabled or not instruments:
            return {}

        provider = self._provider()
        if provider is None:
            return {}

        jetzt = datetime.now()
        # Auf die Obergrenze kuerzen: Der Nutzer sieht ohnehin nur die oberen
        # Zeilen, und ein unbegrenzter Abruf waere der schnellste Weg in die
        # Drosselung.
        auswahl = [i for i in instruments if i.ticker_yahoo][
            : self.settings.quotes.max_symbols
        ]
        symbole = {i.ticker_yahoo for i in auswahl}
        waehrungen = {i.currency for i in auswahl}
        symbole |= {
            self._fx_symbol(w) for w in waehrungen if self._fx_symbol(w) is not None
        }

        fehlend = sorted(s for s in symbole if not self._frisch(s, jetzt))
        if fehlend:
            self._abrufen(provider, fehlend, jetzt)

        return self._zusammenstellen(auswahl)

    def _abrufen(self, provider, symbole: list[str], jetzt: datetime) -> None:
        try:
            neue = provider.fetch_quotes(symbole)
            self.last_error = ""
        except Exception as exc:
            # Ein gescheiterter Abruf darf die Seite nicht kippen - sie zeigt
            # dann weiter die Schlusskurse aus dem Cache.
            self.last_error = str(exc)
            log.warning("Kursabruf fehlgeschlagen: %s", exc)
            return

        with self._lock:
            for symbol in symbole:
                # Auch ein leeres Ergebnis merken, sonst wird jedes Mal erneut
                # nach einem Symbol gefragt, das die Quelle nicht kennt.
                self._fetched[symbol] = jetzt
                if symbol in neue:
                    self._quotes[symbol] = neue[symbol]

    def _zusammenstellen(self, instruments: list[Instrument]) -> dict[str, Quote]:
        basis = self.settings.screening.base_currency.upper()
        ergebnis: dict[str, Quote] = {}

        with self._lock:
            for instrument in instruments:
                quote = self._quotes.get(instrument.ticker_yahoo)
                if quote is None:
                    continue

                waehrung = (instrument.currency or basis).strip()
                faktor = SUBUNIT_FACTOR.get(waehrung, 1.0)
                code = "GBP" if waehrung in {"GBp", "GBX"} else waehrung.upper()
                kurs = quote.price / faktor
                vortag = quote.previous_close / faktor if quote.previous_close else None

                if code != basis:
                    rate = self._kurs_je_basiswaehrung(code)
                    if rate is None or rate <= 0:
                        # Lieber keinen Kurs zeigen als einen falsch
                        # umgerechneten. Die Zeile behaelt ihren Schlusskurs.
                        continue
                    kurs /= rate
                    vortag = vortag / rate if vortag else None

                ergebnis[instrument.isin] = Quote(
                    symbol=instrument.ticker_yahoo, price=kurs, previous_close=vortag,
                    currency=basis, fetched_at=quote.fetched_at, delayed=quote.delayed,
                )
        return ergebnis

    def _kurs_je_basiswaehrung(self, code: str) -> float | None:
        """Aktueller Wechselkurs, sonst der letzte gespeicherte Tageskurs."""
        symbol = self._fx_symbol(code)
        if symbol is not None:
            quote = self._quotes.get(symbol)
            if quote is not None and quote.price > 0:
                return quote.price
        reihe = self.cache.fx.load(code)
        return float(reihe.iloc[-1]) if not reihe.empty else None

    def _fx_symbol(self, waehrung: str) -> str | None:
        basis = self.settings.screening.base_currency.upper()
        code = "GBP" if waehrung in {"GBp", "GBX"} else waehrung.upper()
        if code == basis:
            return None
        return f"{basis}{code}=X"

    def status(self) -> dict:
        with self._lock:
            letzter = max(self._fetched.values(), default=None)
        return {
            "aktiv": self.enabled,
            "abgerufen": letzter.strftime("%H:%M:%S") if letzter else None,
            "symbole": len(self._quotes),
            "fehler": self.last_error,
            "intervall": self.settings.quotes.refresh_seconds,
        }
