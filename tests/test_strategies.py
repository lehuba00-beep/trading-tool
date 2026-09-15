"""Regelbausteine, Profile und Scoring."""

from __future__ import annotations

import pandas as pd
import pytest

from trading_tool.strategies.base import RuleSpec, Strategy, UniverseFilter
from trading_tool.strategies.context import IndicatorContext
from trading_tool.strategies.loader import StrategyConfigError, load_strategy
from trading_tool.strategies.rules import REGISTRY, RuleConfigError, evaluate

from .conftest import make_series, trending_series


def ctx(frame=None, benchmark=None) -> IndicatorContext:
    return IndicatorContext(frame if frame is not None else trending_series(), benchmark)


def test_jede_regel_liefert_eine_zeitreihe_ueber_die_ganze_historie():
    """Das ist die Voraussetzung dafuer, dass Screening und Trefferquoten-
    Auswertung dieselbe Logik nutzen."""
    context = ctx()
    for name in REGISTRY:
        series, label = evaluate(name, context, {})
        assert isinstance(series, pd.Series), name
        assert series.dtype == bool, f"{name} liefert keine booleschen Werte"
        assert len(series) == len(context.index), name
        assert label, f"{name} hat keine Beschriftung"


def test_regel_meldet_unbekannte_parameter_statt_sie_zu_ignorieren():
    with pytest.raises(RuleConfigError, match="unbekannte Parameter"):
        evaluate("rsi_below", ctx(), {"periode": 2})


def test_unbekannte_regel_wird_gemeldet():
    with pytest.raises(RuleConfigError, match="Unbekannte Regel"):
        evaluate("gibt_es_nicht", ctx(), {})


def test_above_ma_trifft_im_aufwaertstrend():
    assert bool(evaluate("above_ma", ctx(), {"ma": "sma", "period": 200})[0].iloc[-1])


def test_above_ma_trifft_nicht_im_abwaertstrend():
    fallend = make_series(drift=-0.0015, seed=11)
    assert not bool(evaluate("above_ma", ctx(fallend), {"ma": "sma", "period": 200})[0].iloc[-1])


def test_relative_staerke_ohne_vergleichsreihe_gilt_als_nicht_erfuellt():
    """Sonst waere der Score ohne Benchmark systematisch zu hoch."""
    series, label = evaluate("relative_strength_above", ctx(), {"period": 126})
    assert not series.any()
    assert "keine Vergleichsreihe" in label


def test_relative_staerke_erkennt_ueberrendite():
    stark = trending_series(seed=2)
    schwach = make_series(drift=0.0001, seed=2)["adj_close"]
    series, _ = evaluate("relative_strength_above", ctx(stark, schwach), {"period": 126})
    assert bool(series.iloc[-1])


def test_kreuzung_gilt_fuer_ein_zeitfenster():
    """Eine Kreuzung ist ein Einzeltagesereignis - ohne Fenster waere die Regel
    praktisch nie im Screening sichtbar."""
    context = ctx()
    eng, _ = evaluate("macd_cross_up", context, {"within_days": 1})
    weit, _ = evaluate("macd_cross_up", context, {"within_days": 20})
    assert weit.sum() > eng.sum()


def _strategy(rules: list[RuleSpec], min_score: float = 50.0) -> Strategy:
    from trading_tool.domain.enums import Horizon

    return Strategy(
        name="test", label="Test", horizon=Horizon.SHORT, rules=rules, min_score=min_score,
        universe=UniverseFilter(min_history_days=250),
    )


def test_pflichtfilter_setzt_den_score_auf_null():
    """Ein K.-o.-Kriterium ist kein Punktabzug - sonst sammelt ein Titel gegen
    den Trend genug Punkte fuer die Trefferliste."""
    strategy = _strategy([
        RuleSpec(type="above_ma", params={"ma": "sma", "period": 200}, required=True),
        RuleSpec(type="rsi_below", params={"period": 14, "threshold": 100}, weight=100),
    ])
    fallend = make_series(drift=-0.0015, seed=12)
    evaluation = strategy.evaluate(ctx(fallend))
    assert evaluation.score.iloc[-1] == 0.0
    assert not bool(evaluation.eligible.iloc[-1])


def test_score_ist_die_gewichtete_summe_normiert_auf_hundert():
    strategy = _strategy([
        RuleSpec(type="rsi_below", params={"period": 14, "threshold": 100}, weight=30),
        RuleSpec(type="rsi_above", params={"period": 14, "threshold": 100}, weight=70),
    ])
    # Erste Regel immer wahr, zweite nie -> 30 von 100 Punkten
    assert strategy.evaluate(ctx()).score.iloc[-1] == pytest.approx(30.0)


def test_am_reihenanfang_entsteht_kein_scheinsignal():
    """Ohne Aufwaermsperre wuerden lauter not-a-number-Vergleiche als False
    gelten und einen Treffer vortaeuschen."""
    strategy = _strategy([RuleSpec(type="rsi_below", params={"threshold": 100}, weight=10)])
    evaluation = strategy.evaluate(ctx())
    assert not evaluation.eligible.iloc[:250].any()


def test_alle_mitgelieferten_profile_laden_und_laufen(strategies):
    assert len(strategies) == 5
    context = ctx(benchmark=trending_series(seed=3)["adj_close"])
    for name, strategy in strategies.items():
        evaluation = strategy.evaluate(context)
        assert len(evaluation.score) == len(context.index), name
        assert evaluation.score.between(0, 100).all(), name
        assert strategy.required_rules, f"{name} hat keinen Pflichtfilter"
        assert strategy.scored_rules, f"{name} hat keine Punktregeln"


def test_profile_decken_alle_horizonte_ab(strategies):
    horizonte = {s.horizon.value for s in strategies.values()}
    assert horizonte == {"kurzfristig", "swing", "mittelfristig", "langfristig"}


def test_kaputtes_profil_wird_mit_dateiname_gemeldet(tmp_path):
    path = tmp_path / "kaputt.yaml"
    path.write_text("name: kaputt\nhorizon: gibt_es_nicht\nrules: []\n", encoding="utf-8")
    with pytest.raises(StrategyConfigError, match="kaputt.yaml"):
        load_strategy(path)


def test_profil_ohne_regeln_wird_abgelehnt(tmp_path):
    path = tmp_path / "leer.yaml"
    path.write_text("name: leer\nhorizon: kurzfristig\nrules: []\n", encoding="utf-8")
    with pytest.raises(StrategyConfigError, match="keine Regeln"):
        load_strategy(path)


def test_profil_mit_falschem_regelparameter_wird_abgelehnt(tmp_path):
    path = tmp_path / "falsch.yaml"
    path.write_text(
        "name: falsch\nhorizon: kurzfristig\nrules:\n"
        "  - type: rsi_below\n    params: {periode: 2}\n",
        encoding="utf-8",
    )
    with pytest.raises(RuleConfigError, match="falsch.yaml"):
        load_strategy(path)


def test_kontext_berechnet_jeden_indikator_nur_einmal():
    context = ctx()
    first = context.ma("ema", 50)
    assert context.ma("ema", 50) is first
