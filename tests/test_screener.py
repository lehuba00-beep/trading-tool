"""Cache, Waehrungsumrechnung und Screening-Lauf."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from trading_tool.domain.enums import AssetClass, TRStatus
from trading_tool.domain.models import Instrument
from trading_tool.providers.base import normalise
from trading_tool.providers.registry import ProviderChain
from trading_tool.screener.engine import Screener
from trading_tool.screener.ranking import sort_signals
from trading_tool.storage.cache import PriceCache
from trading_tool.storage.repositories import BarRepo, FxRepo, InstrumentRepo

from .conftest import trending_series


def build_cache(conn, settings) -> PriceCache:
    return PriceCache(conn, ProviderChain(settings), settings)


# ------------------------------------------------------------ Normalisierung

def test_normalise_vereinheitlicht_spalten_und_sortiert():
    raw = pd.DataFrame(
        {"Open": [1.0], "High": [2.0], "Low": [0.5], "Close": [1.5],
         "Adj Close": [1.4], "Volume": [100]},
        index=pd.to_datetime(["2024-01-02"]),
    )
    frame = normalise(raw)
    assert list(frame.columns) == ["open", "high", "low", "close", "adj_close", "volume"]
    assert frame["adj_close"].iloc[0] == 1.4


def test_normalise_ergaenzt_fehlende_spalten():
    """Nicht jede Quelle liefert Volumen oder bereinigte Kurse."""
    raw = pd.DataFrame({"Close": [10.0]}, index=pd.to_datetime(["2024-01-02"]))
    frame = normalise(raw)
    assert frame["adj_close"].iloc[0] == 10.0
    assert pd.isna(frame["volume"].iloc[0])


def test_normalise_wirft_zeilen_ohne_schlusskurs_weg():
    raw = pd.DataFrame({"Close": [10.0, None]}, index=pd.to_datetime(["2024-01-02", "2024-01-03"]))
    assert len(normalise(raw)) == 1


def test_normalise_entfernt_doppelte_tage():
    raw = pd.DataFrame({"Close": [10.0, 11.0]}, index=pd.to_datetime(["2024-01-02", "2024-01-02"]))
    frame = normalise(raw)
    assert len(frame) == 1
    assert frame["close"].iloc[0] == 11.0, "der spaetere Wert gewinnt"


# ------------------------------------------------------ Waehrungsumrechnung

def test_fremdwaehrung_wird_nach_eur_umgerechnet(conn, settings):
    index = pd.date_range("2024-01-01", periods=5, freq="B")
    BarRepo(conn).upsert("US0378331005", "yfinance", pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
         "adj_close": 100.0, "volume": 1e6}, index=index))
    FxRepo(conn).upsert("USD", pd.Series(1.25, index=index))

    instrument = Instrument(isin="US0378331005", name="Apple", asset_class=AssetClass.STOCK,
                            ticker_yahoo="AAPL", currency="USD")
    frame = build_cache(conn, settings).bars_in_base_currency(instrument)
    assert frame["close"].iloc[0] == pytest.approx(80.0)


def test_volumen_wird_nicht_umgerechnet(conn, settings):
    """Das Volumen ist eine Stueckzahl, keine Geldgroesse."""
    index = pd.date_range("2024-01-01", periods=3, freq="B")
    BarRepo(conn).upsert("US0378331005", "yfinance", pd.DataFrame(
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0,
         "adj_close": 100.0, "volume": 5e5}, index=index))
    FxRepo(conn).upsert("USD", pd.Series(1.25, index=index))
    instrument = Instrument(isin="US0378331005", name="Apple", asset_class=AssetClass.STOCK,
                            currency="USD")
    frame = build_cache(conn, settings).bars_in_base_currency(instrument)
    assert frame["volume"].iloc[0] == 5e5


def test_britische_pence_werden_beruecksichtigt(conn, settings):
    """Yahoo notiert britische Titel in Pence, nicht in Pfund."""
    index = pd.date_range("2024-01-01", periods=3, freq="B")
    BarRepo(conn).upsert("GB00B10RZP78", "yfinance", pd.DataFrame(
        {"open": 2500.0, "high": 2500.0, "low": 2500.0, "close": 2500.0,
         "adj_close": 2500.0, "volume": 1e6}, index=index))
    FxRepo(conn).upsert("GBP", pd.Series(0.85, index=index))
    instrument = Instrument(isin="GB00B10RZP78", name="Unilever",
                            asset_class=AssetClass.STOCK, currency="GBp")
    frame = build_cache(conn, settings).bars_in_base_currency(instrument)
    assert frame["close"].iloc[0] == pytest.approx(25 / 0.85, rel=1e-6)


def test_fehlende_wechselkurstage_werden_vorwaerts_gefuellt(conn, settings):
    """Feiertage der Devisenseite duerfen keine Luecke in die Kursreihe reissen."""
    index = pd.date_range("2024-01-01", periods=5, freq="B")
    BarRepo(conn).upsert("US0378331005", "yfinance", pd.DataFrame(
        {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0,
         "adj_close": 100.0, "volume": 1e6}, index=index))
    FxRepo(conn).upsert("USD", pd.Series([1.25], index=[index[0]]))
    instrument = Instrument(isin="US0378331005", name="Apple",
                            asset_class=AssetClass.STOCK, currency="USD")
    frame = build_cache(conn, settings).bars_in_base_currency(instrument)
    assert len(frame) == 5
    assert frame["close"].tolist() == pytest.approx([80.0] * 5)


def test_ohne_wechselkurs_bleibt_die_originalwaehrung(conn, settings):
    """Lieber sichtbar unveraendert als still falsch umgerechnet."""
    index = pd.date_range("2024-01-01", periods=3, freq="B")
    BarRepo(conn).upsert("US0378331005", "yfinance", pd.DataFrame(
        {"open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0,
         "adj_close": 100.0, "volume": 1e6}, index=index))
    instrument = Instrument(isin="US0378331005", name="Apple",
                            asset_class=AssetClass.STOCK, currency="USD")
    frame = build_cache(conn, settings).bars_in_base_currency(instrument)
    assert frame["close"].iloc[0] == 100.0


# ---------------------------------------------------------------- Screening

def _screener(conn, settings, strategies) -> Screener:
    return Screener(conn, build_cache(conn, settings), settings, strategies)


def test_screening_liefert_treffer_mit_kennzahlen(seeded, settings, strategies):
    screener = _screener(seeded, settings, strategies)
    run_id, signals = screener.run("swing", refresh=False)
    assert run_id > 0
    for signal in signals:
        assert 0 <= signal.score <= 100
        assert signal.metrics["kurs_eur"] > 0
        assert signal.metrics["stop"] < signal.metrics["kurs_eur"]
        assert signal.metrics["ziel"] > signal.metrics["kurs_eur"]
        assert signal.hits, "ohne Regelauswertung ist ein Score nicht ueberpruefbar"


def test_screening_nimmt_keine_nicht_handelbaren_titel(seeded, settings, strategies):
    """Die Vergleichsreihe steht im Universum, darf aber nie als Treffer erscheinen."""
    screener = _screener(seeded, settings, strategies)
    _, signals = screener.run("mittelfristig", refresh=False)
    assert all(s.isin != "IDX_MSCIWORLD" for s in signals)


def test_screening_beachtet_den_liquiditaetsfilter(seeded, settings, strategies):
    screener = _screener(seeded, settings, strategies)
    strategy = strategies["swing"]
    strategy.universe.min_avg_turnover_eur = 1e15  # unerreichbar
    _, signals = screener.run("swing", refresh=False)
    assert signals == []


def test_screening_ueberspringt_titel_ohne_historie(seeded, settings, strategies):
    InstrumentRepo(seeded).upsert_many([
        Instrument(isin="DE0008404005", name="Allianz", asset_class=AssetClass.STOCK,
                   ticker_yahoo="ALV.DE", currency="EUR", tr_status=TRStatus.ASSUMED)
    ])
    screener = _screener(seeded, settings, strategies)
    _, signals = screener.run("swing", refresh=False)
    assert all(s.isin != "DE0008404005" for s in signals)


def test_lauf_wird_protokolliert(seeded, settings, strategies):
    screener = _screener(seeded, settings, strategies)
    screener.run("kurz_ausbruch", refresh=False)
    run = screener.runs.latest("kurz_ausbruch")
    assert run is not None and run.status == "ok"
    assert run.n_instruments > 0


def test_unbekannte_strategie_wird_gemeldet(seeded, settings, strategies):
    with pytest.raises(KeyError):
        _screener(seeded, settings, strategies).run("gibt_es_nicht")


def test_vorlaeufig_markiert_unfertige_tagesbalken(seeded, settings, strategies):
    """Ein Signal auf dem laufenden Handelstag kann sich bis Schluss aufloesen."""
    heute = pd.Timestamp(date.today())
    frame = trending_series(seed=1)
    frame.index = pd.date_range(end=heute, periods=len(frame), freq="B")
    BarRepo(seeded).upsert("DE0007164600", "yfinance", frame)

    screener = _screener(seeded, settings, strategies)
    _, signals = screener.run("swing", refresh=False)
    treffer = [s for s in signals if s.isin == "DE0007164600"]
    if treffer:
        assert treffer[0].provisional is (treffer[0].as_of >= date.today())


def test_sortierung_nutzt_liquiditaet_als_zweitkriterium():
    from trading_tool.domain.enums import Direction, Horizon
    from trading_tool.domain.models import Signal

    gleich = [
        Signal(isin="A", name="A", strategy="s", horizon=Horizon.SHORT,
               direction=Direction.LONG, score=70.0, as_of=date.today(),
               metrics={"umsatz_20d_eur": 1_000_000}),
        Signal(isin="B", name="B", strategy="s", horizon=Horizon.SHORT,
               direction=Direction.LONG, score=70.0, as_of=date.today(),
               metrics={"umsatz_20d_eur": 9_000_000}),
    ]
    assert [s.isin for s in sort_signals(gleich)] == ["B", "A"]


# ------------------------------------- Datenqualitaet und Termine am Signal

def test_signal_traegt_den_qualitaetsbefund(seeded, settings, strategies):
    """Ein Titel mit Datenproblem wird markiert, nicht aussortiert - sonst
    verschwindet genau die Information, um derentwillen geprueft wird."""
    from trading_tool.storage.repositories import BarRepo

    frame = trending_series(seed=1)
    # Auf denselben aktuellen Zeitraum legen wie die Fixture, sonst kaeme der
    # Befund nur daher, dass die Reihe alt ist.
    frame.index = pd.bdate_range(
        end=pd.Timestamp(date.today()) - pd.offsets.BDay(1), periods=len(frame)
    )
    # Eingefrorene Reihe am Ende: sichtbarer Befund, aber weiter handelbar
    letzte = frame.index[-15:]
    wert = float(frame.loc[letzte[0], "close"])
    for spalte in ("open", "high", "low", "close", "adj_close"):
        frame.loc[letzte, spalte] = wert
    BarRepo(seeded).upsert("DE0007164600", "yfinance", frame)

    screener = _screener(seeded, settings, strategies)
    _, signals = screener.run("mittelfristig", refresh=False)
    betroffen = [s for s in signals if s.isin == "DE0007164600"]
    if betroffen:
        assert betroffen[0].quality != "ok"
        assert betroffen[0].quality_notes


def test_saubere_reihe_ergibt_signal_ohne_befund(seeded, settings, strategies):
    _, signals = _screener(seeded, settings, strategies).run("swing", refresh=False)
    assert signals, "die Testreihen sollten Treffer liefern"
    assert all(s.quality == "ok" for s in signals)
    assert all(s.quality_notes == [] for s in signals)


def test_lauf_nennt_die_zahl_der_auffaelligkeiten(seeded, settings, strategies):
    screener = _screener(seeded, settings, strategies)
    screener.run("swing", refresh=False)
    assert "Datenauffaelligkeiten" in screener.runs.latest("swing").message


def test_termin_wandert_an_das_signal(seeded, settings, strategies):
    from datetime import timedelta

    from trading_tool.storage.repositories import InstrumentRepo

    termin = date.today() + timedelta(days=4)
    InstrumentRepo(seeded).set_earnings("DE0007164600", termin)

    _, signals = _screener(seeded, settings, strategies).run("swing", refresh=False)
    betroffen = [s for s in signals if s.isin == "DE0007164600"]
    if betroffen:
        assert betroffen[0].earnings_date == termin
        assert betroffen[0].earnings_within_holding(20)


def test_qualitaet_und_termin_ueberleben_das_speichern(seeded, settings, strategies):
    """Die Trefferliste wird aus der Datenbank gelesen, nicht aus dem Speicher."""
    from datetime import timedelta

    from trading_tool.storage.repositories import InstrumentRepo

    InstrumentRepo(seeded).set_earnings("DE0007164600", date.today() + timedelta(days=4))
    screener = _screener(seeded, settings, strategies)
    run_id, _ = screener.run("swing", refresh=False)

    gelesen = screener.signals.for_run(run_id)
    assert gelesen, "es sollten Treffer gespeichert worden sein"
    assert all(hasattr(s, "quality") for s in gelesen)
    betroffen = [s for s in gelesen if s.isin == "DE0007164600"]
    if betroffen:
        assert betroffen[0].earnings_date is not None


def test_termine_ohne_passenden_anbieter_stoeren_nicht(seeded, settings, strategies):
    """Der CSV-Provider kennt keine Termine - das darf den Lauf nicht kippen."""
    assert _screener(seeded, settings, strategies).refresh_earnings() == 0
