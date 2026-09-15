"""Trefferquoten-Auswertung."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from trading_tool.backtest import evaluate_instrument, evaluate_strategy, forward_return, summarise
from trading_tool.backtest.forward_returns import _non_overlapping
from trading_tool.domain.enums import Horizon
from trading_tool.strategies.base import RuleSpec, Strategy, UniverseFilter

from .conftest import make_series, trending_series


def test_vorwaertsrendite_steigt_erst_am_folgetag_ein():
    """Das Signal entsteht auf dem Schlusskurs - ein Einstieg am selben Tag
    waere ein Griff in die Zukunft."""
    frame = pd.DataFrame({
        "open": [10.0, 20.0, 30.0, 40.0],
        "high": [10.0, 20.0, 30.0, 40.0],
        "low": [10.0, 20.0, 30.0, 40.0],
        "close": [10.0, 20.0, 30.0, 40.0],
        "adj_close": [10.0, 20.0, 30.0, 40.0],
        "volume": [1.0] * 4,
    })
    # Signal auf Position 0 -> Einstieg zu 20 (Eroeffnung t+1),
    # Ausstieg nach 1 Tag zum Schluss von t+2 = 30 -> +50 %
    assert forward_return(frame, 1).iloc[0] == pytest.approx(50.0)


def test_ueberlappende_signale_werden_zusammengefasst():
    """Fuenf Signale an fuenf Folgetagen waeren fast dieselbe Beobachtung."""
    assert _non_overlapping(np.array([0, 1, 2, 3, 10, 11, 25]), 5) == [0, 10, 25]


def test_ohne_ueberlappung_bleiben_alle_signale():
    assert _non_overlapping(np.array([0, 10, 20]), 5) == [0, 10, 20]


def _strategy(min_score: float = 0.0, holding: int = 5) -> Strategy:
    from trading_tool.strategies.base import RiskSpec

    return Strategy(
        name="test", label="Test", horizon=Horizon.SHORT, min_score=min_score,
        universe=UniverseFilter(min_history_days=250),
        risk=RiskSpec(max_holding_days=holding),
        rules=[RuleSpec(type="rsi_below", params={"period": 2, "threshold": 10}, weight=100)],
    )


def test_auswertung_liefert_signal_und_vergleichsgruppe():
    signals, baseline = evaluate_instrument(_strategy(), trending_series())
    assert signals, "im Aufwaertstrend sollte die Regel gelegentlich ausloesen"
    assert len(baseline) > len(signals), "die Vergleichsgruppe umfasst alle Tage"


def test_kurze_historie_liefert_keine_auswertung():
    signals, baseline = evaluate_instrument(_strategy(), make_series(n=100))
    assert signals == [] and baseline == []


def test_zusammenfassung_rechnet_trefferquote_und_vorsprung():
    ergebnis = summarise([1.0, 2.0, -1.0, 3.0], [1.0, -1.0])
    assert ergebnis["signal"]["n"] == 4
    assert ergebnis["signal"]["trefferquote"] == 75.0
    assert ergebnis["vergleich"]["trefferquote"] == 50.0
    assert ergebnis["vorsprung_trefferquote_pp"] == 25.0


def test_zu_wenige_beobachtungen_werden_als_nicht_belastbar_markiert():
    """Unter 20 Beobachtungen ist jede Quote Zufall - das muss sichtbar sein."""
    assert summarise([1.0, 2.0], [1.0])["belastbar"] is False
    assert summarise([1.0] * 25, [1.0])["belastbar"] is True


def test_leere_eingabe_bricht_nicht_ab():
    ergebnis = summarise([], [])
    assert ergebnis["signal"]["n"] == 0
    assert ergebnis["vorsprung_trefferquote_pp"] is None


def test_auswertung_ueber_mehrere_titel(strategies):
    frames = {f"T{i}": trending_series(seed=i) for i in range(6)}
    ergebnis = evaluate_strategy(strategies["kurz_pullback"], frames)
    assert ergebnis["titel_ausgewertet"] == 6
    assert ergebnis["zeitraum_von"] < ergebnis["zeitraum_bis"]
    assert ergebnis["hinweise"], "die methodischen Einschraenkungen gehoeren ins Ergebnis"
    assert any("Delistete" in h for h in ergebnis["hinweise"])


def test_strengeres_profil_liefert_weniger_signale():
    viele, _ = evaluate_instrument(_strategy(min_score=0), trending_series())
    keine, _ = evaluate_instrument(_strategy(min_score=101), trending_series())
    assert len(viele) > len(keine) == 0


def test_kaputte_kursreihe_kippt_die_auswertung_nicht(strategies):
    frames = {"gut": trending_series(), "leer": pd.DataFrame()}
    ergebnis = evaluate_strategy(strategies["kurz_pullback"], frames)
    assert ergebnis["titel_ausgewertet"] == 2
