"""Laufend aktualisierte Kurse.

Der Dienst wird gegen einen erfundenen Provider geprueft - ein echter Abruf
findet im Test nie statt.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from trading_tool.domain.enums import AssetClass
from trading_tool.domain.models import Instrument
from trading_tool.providers.quotes import Quote, QuoteService
from trading_tool.providers.yfinance_provider import _in_gruppen, _letzte_kurse, _teilframe
from trading_tool.storage.cache import PriceCache
from trading_tool.storage.repositories import FxRepo


class FakeProvider:
    """Zaehlt Abrufe mit - so laesst sich Buendelung und Zwischenspeicher pruefen."""

    name = "fake"

    def __init__(self, kurse: dict[str, float], fehler: Exception | None = None) -> None:
        self.kurse = kurse
        self.fehler = fehler
        self.aufrufe: list[list[str]] = []

    def fetch_bars(self, symbol, start, end):
        return pd.DataFrame()

    def fetch_quotes(self, symbols: list[str]) -> dict[str, Quote]:
        self.aufrufe.append(list(symbols))
        if self.fehler:
            raise self.fehler
        return {
            s: Quote(symbol=s, price=self.kurse[s], previous_close=self.kurse[s] * 0.98,
                     fetched_at=datetime.now())
            for s in symbols
            if s in self.kurse
        }


class FakeChain:
    def __init__(self, provider) -> None:
        self.providers = [provider]
        self.primary_name = provider.name


@pytest.fixture
def dienst(conn, settings):
    def bauen(kurse: dict[str, float], fehler: Exception | None = None):
        provider = FakeProvider(kurse, fehler)
        chain = FakeChain(provider)
        cache = PriceCache(conn, chain, settings)
        return QuoteService(chain, cache, settings), provider
    return bauen


SAP = Instrument(isin="DE0007164600", name="SAP", asset_class=AssetClass.STOCK,
                 ticker_yahoo="SAP.DE", currency="EUR")
APPLE = Instrument(isin="US0378331005", name="Apple", asset_class=AssetClass.STOCK,
                   ticker_yahoo="AAPL", currency="USD")
SHELL = Instrument(isin="GB00B10RZP78", name="Shell", asset_class=AssetClass.STOCK,
                   ticker_yahoo="SHEL.L", currency="GBp")


def test_kurs_wird_geliefert(dienst):
    service, _ = dienst({"SAP.DE": 240.0})
    quotes = service.get([SAP])
    assert quotes[SAP.isin].price == pytest.approx(240.0)


def test_veraenderung_wird_aus_dem_vortag_gerechnet(dienst):
    service, _ = dienst({"SAP.DE": 100.0})  # Vortag = 98.0
    assert service.get([SAP])[SAP.isin].change_pct == pytest.approx(2.0408, abs=1e-3)


def test_alle_titel_werden_in_einem_abruf_geholt(dienst):
    """Eine Trefferliste mit vielen Zeilen darf nicht zu vielen Abrufen werden."""
    service, provider = dienst({"SAP.DE": 240.0, "AAPL": 200.0, "EURUSD=X": 1.10})
    service.get([SAP, APPLE])
    assert len(provider.aufrufe) == 1
    assert set(provider.aufrufe[0]) == {"SAP.DE", "AAPL", "EURUSD=X"}


def test_zwischenspeicher_verhindert_wiederholte_abrufe(dienst):
    service, provider = dienst({"SAP.DE": 240.0})
    for _ in range(5):
        service.get([SAP])
    assert len(provider.aufrufe) == 1, "die Quelle darf nicht bei jeder Abfrage belastet werden"


def test_abgelaufener_zwischenspeicher_holt_erneut(dienst, settings):
    settings.quotes.ttl_seconds = 0
    service, provider = dienst({"SAP.DE": 240.0})
    service.get([SAP])
    service.get([SAP])
    assert len(provider.aufrufe) == 2


def test_fremdwaehrung_wird_umgerechnet(dienst):
    service, _ = dienst({"AAPL": 200.0, "EURUSD=X": 1.25})
    assert service.get([APPLE])[APPLE.isin].price == pytest.approx(160.0)


def test_britische_pence_werden_beruecksichtigt(dienst):
    service, _ = dienst({"SHEL.L": 2500.0, "EURGBP=X": 0.85})
    assert service.get([SHELL])[SHELL.isin].price == pytest.approx(25 / 0.85, rel=1e-6)


def test_ohne_wechselkurs_wird_kein_kurs_gezeigt(dienst, conn):
    """Lieber der Schlusskurs von gestern als ein falsch umgerechneter von heute."""
    service, _ = dienst({"AAPL": 200.0})  # kein EURUSD
    assert APPLE.isin not in service.get([APPLE])


def test_gespeicherter_wechselkurs_dient_als_rueckfall(dienst, conn):
    FxRepo(conn).upsert("USD", pd.Series([1.25], index=pd.to_datetime(["2026-09-14"])))
    service, _ = dienst({"AAPL": 200.0})
    assert service.get([APPLE])[APPLE.isin].price == pytest.approx(160.0)


def test_gescheiterter_abruf_kippt_die_seite_nicht(dienst):
    service, _ = dienst({}, fehler=RuntimeError("Quelle gestoert"))
    assert service.get([SAP]) == {}
    assert "gestoert" in service.status()["fehler"]


def test_unbekanntes_symbol_wird_nicht_erneut_abgefragt(dienst):
    """Sonst fragt jede Aktualisierung erneut nach etwas, das es nicht gibt."""
    service, provider = dienst({})
    service.get([SAP])
    service.get([SAP])
    assert len(provider.aufrufe) == 1


def test_abgeschaltet_liefert_nichts(dienst, settings):
    settings.quotes.enabled = False
    service, provider = dienst({"SAP.DE": 240.0})
    assert service.get([SAP]) == {}
    assert provider.aufrufe == []


def test_obergrenze_begrenzt_den_abruf(dienst, settings):
    settings.quotes.max_symbols = 2
    viele = [
        Instrument(isin=f"X{i:011d}", name=f"T{i}", asset_class=AssetClass.STOCK,
                   ticker_yahoo=f"T{i}.DE", currency="EUR")
        for i in range(10)
    ]
    service, provider = dienst({f"T{i}.DE": 100.0 for i in range(10)})
    service.get(viele)
    assert len(provider.aufrufe[0]) == 2


def test_status_nennt_zeitpunkt_und_intervall(dienst):
    service, _ = dienst({"SAP.DE": 240.0})
    service.get([SAP])
    status = service.status()
    assert status["aktiv"] is True
    assert status["abgerufen"]
    assert status["intervall"] > 0


# ------------------------------------------- Zerlegung der Provider-Antwort

def test_mehrstufige_antwort_wird_je_symbol_zerlegt():
    idx = pd.date_range("2026-09-09", periods=3, freq="B")
    frame = pd.DataFrame({("SAP.DE", "Close"): [100.0, 101.0, 103.0],
                          ("AAPL", "Close"): [200.0, 205.0, 210.0]}, index=idx)
    frame.columns = pd.MultiIndex.from_tuples(frame.columns)
    assert _letzte_kurse(_teilframe(frame, "SAP.DE", 2)) == (103.0, 101.0)
    assert _teilframe(frame, "UNBEKANNT", 2) is None


def test_flache_antwort_gilt_nur_bei_einem_symbol():
    """yfinance liefert je nach Version mal flache, mal mehrstufige Spalten."""
    idx = pd.date_range("2026-09-09", periods=2, freq="B")
    frame = pd.DataFrame({"Close": [50.0, 52.0]}, index=idx)
    assert _letzte_kurse(_teilframe(frame, "SAP.DE", 1)) == (52.0, 50.0)
    assert _teilframe(frame, "SAP.DE", 2) is None


def test_unbrauchbare_antworten_liefern_nichts():
    assert _letzte_kurse(pd.DataFrame()) is None
    assert _letzte_kurse(None) is None
    assert _letzte_kurse(pd.DataFrame({"Open": [1.0]})) is None
    assert _letzte_kurse(pd.DataFrame({"Close": [0.0]})) is None


def test_einzelner_balken_hat_keinen_vortag():
    assert _letzte_kurse(pd.DataFrame({"Close": [42.0]})) == (42.0, None)


def test_gruppierung_teilt_in_bloecke():
    assert [len(g) for g in _in_gruppen(list(range(95)), 40)] == [40, 40, 15]
