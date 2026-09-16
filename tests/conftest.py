"""Gemeinsame Testvorrichtungen.

Alle Tests laufen ohne Netz. Die Kursreihen sind synthetisch und mit festem
Zufallskeim erzeugt - damit ist jeder Lauf reproduzierbar, und ein
fehlgeschlagener Test liegt nie an einer Kursquelle.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from trading_tool.config import Settings
from trading_tool.domain.enums import AssetClass, TRStatus
from trading_tool.domain.models import Instrument
from trading_tool.storage.db import init_db
from trading_tool.storage.repositories import BarRepo, FxRepo, InstrumentRepo


def make_series(
    n: int = 900,
    drift: float = 0.0004,
    vol: float = 0.013,
    seed: int = 0,
    start: str = "2021-01-04",
    price: float = 100.0,
) -> pd.DataFrame:
    """OHLCV-Reihe mit vorgegebenem Trend und Rauschen."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, vol, n)
    index = pd.date_range(start, periods=n, freq="B")
    close = pd.Series(price * np.cumprod(1 + returns), index=index)

    # Hoch und Tief werden aus Eroeffnung und Schluss abgeleitet, damit beide
    # innerhalb der Tagesspanne liegen. Bei echten Kursdaten ist das per
    # Definition so - eine Fixture, die das verletzt, laesst die
    # Datenqualitaetspruefung zu Recht Alarm schlagen.
    open_ = (close.shift(1) * (1 + rng.normal(0, vol / 4, n))).bfill()
    noise = np.abs(rng.normal(0, vol / 2, n))
    hoch = pd.concat([open_, close], axis=1).max(axis=1) * (1 + noise)
    tief = pd.concat([open_, close], axis=1).min(axis=1) * (1 - noise)

    return pd.DataFrame(
        {
            "open": open_,
            "high": hoch,
            "low": tief,
            "close": close,
            "adj_close": close,
            "volume": rng.integers(200_000, 2_000_000, n).astype(float),
        },
        index=index,
    )


def trending_series(n: int = 900, seed: int = 1) -> pd.DataFrame:
    """Klarer Aufwaertstrend - erfuellt die Pflichtfilter der Long-Profile."""
    return make_series(n=n, drift=0.0012, vol=0.011, seed=seed)


def trending_session_series(n: int = 400, ende: str = "2026-09-14", seed: int = 1) -> pd.DataFrame:
    """Aufwaertstrend, der auf einem festen Datum endet.

    Fuer Pruefungen, die vom Abstand zum heutigen Tag abhaengen.
    """
    frame = trending_series(n=n, seed=seed)
    frame.index = pd.date_range(end=pd.Timestamp(ende), periods=n, freq="B")
    return frame


@pytest.fixture(autouse=True)
def kein_netzzugriff(monkeypatch):
    """Jeder Netzabruf im Test ist ein Fehler - und zwar ein lauter.

    Anlass: Ein Oberflaechentest hat ein echtes Screening ausgeloest. Auf einem
    Rechner ohne Netz scheiterte jeder Abruf sofort und der Test lief durch; im
    CI-Container mit Netz begann der Hintergrundlauf tatsaechlich, hunderte
    Titel zu laden, und der Abbau der Anwendung blieb daran haengen. Stumm
    langsam ist die schlechteste Fehlerart - deshalb hier ein Riegel.
    """
    from trading_tool.providers.stooq_provider import StooqProvider
    from trading_tool.providers.yfinance_provider import YFinanceProvider

    def verboten(self, *args, **kwargs):
        raise AssertionError(
            f"Test versucht einen echten Kursabruf ueber {type(self).__name__}. "
            "Tests muessen ohne Netz auskommen - Kursreihen kommen aus "
            "conftest.make_series oder dem CSV-Provider."
        )

    for klasse in (YFinanceProvider, StooqProvider):
        monkeypatch.setattr(klasse, "fetch_bars", verboten)
    for methode in ("fetch_fx", "fetch_quotes", "fetch_earnings_date"):
        monkeypatch.setattr(YFinanceProvider, methode, verboten)


@pytest.fixture
def settings(tmp_path) -> Settings:
    s = Settings(data_dir=tmp_path)
    (tmp_path / "exports").mkdir(exist_ok=True)
    # Ausschliesslich der CSV-Provider auf ein leeres Verzeichnis: liefert
    # nichts, ruft nichts ab, wartet nicht.
    s.provider.primary = "csv"
    s.provider.fallback = []
    s.provider.request_pause_seconds = 0.0
    return s


@pytest.fixture
def conn(settings):
    connection = init_db(settings.db_path)
    yield connection
    connection.close()


@pytest.fixture
def seeded(conn, settings):
    """Datenbank mit Instrumenten, Kursen und Wechselkursen."""
    instruments = [
        Instrument(isin="DE0007164600", name="SAP", asset_class=AssetClass.STOCK,
                   ticker_yahoo="SAP.DE", currency="EUR", exchange="XETRA",
                   tr_status=TRStatus.ASSUMED, source="test"),
        Instrument(isin="DE0005190003", name="BMW", asset_class=AssetClass.STOCK,
                   ticker_yahoo="BMW.DE", currency="EUR", exchange="XETRA",
                   tr_status=TRStatus.VERIFIED, tr_checked_at=date.today(), source="test"),
        Instrument(isin="US0378331005", name="Apple", asset_class=AssetClass.STOCK,
                   ticker_yahoo="AAPL", currency="USD", exchange="NASDAQ",
                   tr_status=TRStatus.ASSUMED, source="test"),
        Instrument(isin="IE00B4L5Y983", name="MSCI World ETF", asset_class=AssetClass.ETF,
                   ticker_yahoo="EUNL.DE", currency="EUR", exchange="XETRA",
                   tr_status=TRStatus.ASSUMED, source="test"),
        Instrument(isin="IDX_MSCIWORLD", name="MSCI World", asset_class=AssetClass.INDEX,
                   ticker_yahoo="URTH", currency="USD", exchange="NYSE",
                   tr_status=TRStatus.UNAVAILABLE, source="test"),
    ]
    InstrumentRepo(conn).upsert_many(instruments)

    bars = BarRepo(conn)
    # Die Reihen enden am letzten Werktag, nicht irgendwann in der
    # Vergangenheit: Die Fixture soll einen frisch aktualisierten Cache
    # darstellen. Eine zwei Jahre alte Reihe wuerde die
    # Datenqualitaetspruefung zu Recht als veraltet melden.
    index = pd.bdate_range(end=pd.Timestamp(date.today()) - pd.offsets.BDay(1), periods=900)
    for number, instrument in enumerate(instruments):
        frame = trending_series(seed=number + 1)
        frame.index = index
        bars.upsert(instrument.isin, "yfinance", frame)

    FxRepo(conn).upsert("USD", pd.Series(1.08, index=index))
    return conn


@pytest.fixture
def strategies():
    from pathlib import Path

    from trading_tool.strategies import load_all

    root = Path(__file__).resolve().parents[1]
    return load_all(root / "config" / "strategies")


@pytest.fixture
def yesterday() -> date:
    return date.today() - timedelta(days=1)
