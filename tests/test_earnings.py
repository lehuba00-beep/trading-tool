"""Termine fuer Quartalszahlen.

Das Regelwerk kennt nur Kurse. Ein Ausbruchssignal zwei Tage vor Zahlen ist
ein Muenzwurf, den kein Indikator erkennen kann - deshalb der Hinweis.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd
import pytest

from trading_tool.domain.enums import AssetClass, Direction, Horizon, TRStatus
from trading_tool.domain.models import Instrument, Signal
from trading_tool.providers.yfinance_provider import _als_datum
from trading_tool.storage.repositories import InstrumentRepo

HEUTE = date(2026, 9, 16)


@pytest.mark.parametrize(
    "rohwert, erwartet",
    [
        ([date(2026, 10, 22)], date(2026, 10, 22)),
        ((datetime(2026, 10, 22, 14, 0),), date(2026, 10, 22)),
        ("2026-10-22", date(2026, 10, 22)),
        (pd.Timestamp("2026-10-22"), date(2026, 10, 22)),
        (date(2026, 10, 22), date(2026, 10, 22)),
        # Bei geschaetzten Terminen liefert die Quelle eine Spanne; der fruehere
        # Wert zaehlt, weil er die Warnung ausloest.
        ([date(2026, 10, 22), date(2026, 10, 26)], date(2026, 10, 22)),
    ],
)
def test_datumsformate_werden_erkannt(rohwert, erwartet):
    assert _als_datum(rohwert) == erwartet


@pytest.mark.parametrize("rohwert", [None, [], "kein Datum", float("nan"), {}, object()])
def test_unbrauchbare_werte_gelten_als_unbekannt(rohwert):
    """Ein falsch geratener Termin waere schlechter als gar keiner."""
    assert _als_datum(rohwert) is None


def _repo(conn) -> InstrumentRepo:
    repo = InstrumentRepo(conn)
    repo.upsert_many([
        Instrument(isin="DE0007164600", name="SAP", asset_class=AssetClass.STOCK,
                   ticker_yahoo="SAP.DE", tr_status=TRStatus.ASSUMED),
        Instrument(isin="IE00B4L5Y983", name="MSCI World ETF", asset_class=AssetClass.ETF,
                   ticker_yahoo="EUNL.DE", tr_status=TRStatus.ASSUMED),
    ])
    return repo


def test_etfs_werden_nicht_nach_terminen_gefragt(conn):
    """Fuer ETFs und Indizes gibt es keine Quartalszahlen."""
    offen = _repo(conn).needs_earnings_refresh(7)
    assert [i.isin for i in offen] == ["DE0007164600"]


def test_termin_wird_gespeichert_und_gelesen(conn):
    repo = _repo(conn)
    repo.set_earnings("DE0007164600", date(2026, 10, 22))
    instrument = repo.get("DE0007164600")
    assert instrument.next_earnings == date(2026, 10, 22)
    assert instrument.earnings_checked_at == date.today()


def test_leeres_ergebnis_wird_ebenfalls_vermerkt(conn):
    """Sonst fragt jeder Lauf erneut nach Titeln, fuer die die Quelle nichts hat."""
    repo = _repo(conn)
    repo.set_earnings("DE0007164600", None)
    assert repo.get("DE0007164600").earnings_checked_at is not None
    assert repo.needs_earnings_refresh(7) == []


def test_abgelaufener_termin_wird_neu_abgefragt(conn):
    repo = _repo(conn)
    repo.set_earnings("DE0007164600", date.today() - timedelta(days=1))
    assert [i.isin for i in repo.needs_earnings_refresh(7)] == ["DE0007164600"]


def test_erneuter_import_loescht_den_termin_nicht(conn):
    repo = _repo(conn)
    repo.set_earnings("DE0007164600", date(2026, 10, 22))
    repo.upsert_many([Instrument(isin="DE0007164600", name="SAP SE",
                                 asset_class=AssetClass.STOCK, ticker_yahoo="SAP.DE",
                                 tr_status=TRStatus.ASSUMED)])
    assert repo.get("DE0007164600").next_earnings == date(2026, 10, 22)


def test_anstehende_termine_werden_gefunden(conn):
    repo = _repo(conn)
    repo.set_earnings("DE0007164600", date.today() + timedelta(days=5))
    assert [i.isin for i in repo.upcoming_earnings(14)] == ["DE0007164600"]
    assert repo.upcoming_earnings(3) == []


def _signal(termin: date | None) -> Signal:
    return Signal(isin="X", name="X", strategy="s", horizon=Horizon.SHORT,
                  direction=Direction.LONG, score=80.0, as_of=HEUTE, earnings_date=termin)


def test_termin_in_der_haltedauer_wird_erkannt():
    assert _signal(HEUTE + timedelta(days=3)).earnings_within_holding(5, HEUTE)


def test_termin_nach_der_haltedauer_ist_kein_hinweis():
    assert not _signal(HEUTE + timedelta(days=40)).earnings_within_holding(5, HEUTE)


def test_vergangener_termin_ist_kein_hinweis():
    assert not _signal(HEUTE - timedelta(days=2)).earnings_within_holding(5, HEUTE)


def test_ohne_termin_kein_hinweis():
    assert not _signal(None).earnings_within_holding(5, HEUTE)
    assert _signal(None).earnings_in_days(HEUTE) is None


def test_laengere_haltedauer_erfasst_spaetere_termine():
    """Mittelfristig zaehlt ein Termin, der kurzfristig noch weit weg waere."""
    signal = _signal(HEUTE + timedelta(days=60))
    assert not signal.earnings_within_holding(5, HEUTE)
    assert signal.earnings_within_holding(126, HEUTE)
