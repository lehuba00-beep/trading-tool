"""Strategieprofile aus YAML lesen.

Fehler in einer Profildatei muessen beim Laden auffallen und die betroffene
Datei benennen - nicht mitten im Screening-Lauf als leeres Ergebnis erscheinen.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from ..domain.enums import Direction, Horizon
from .base import RiskSpec, RuleSpec, Strategy, UniverseFilter
from .rules import REGISTRY, RuleConfigError

log = logging.getLogger(__name__)


class StrategyConfigError(ValueError):
    pass


def load_strategy(path: Path) -> Strategy:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise StrategyConfigError(f"{path.name}: YAML nicht lesbar - {exc}") from exc

    try:
        horizon = Horizon(raw.get("horizon", "kurzfristig"))
    except ValueError as exc:
        raise StrategyConfigError(
            f"{path.name}: unbekannter Horizont '{raw.get('horizon')}'. "
            f"Erlaubt: {[h.value for h in Horizon]}"
        ) from exc

    rules: list[RuleSpec] = []
    for entry in raw.get("rules", []):
        rule_type = entry.get("type")
        if rule_type not in REGISTRY:
            raise StrategyConfigError(
                f"{path.name}: unbekannte Regel '{rule_type}'. "
                f"Verfuegbar: {', '.join(sorted(REGISTRY))}"
            )
        rules.append(
            RuleSpec(
                type=rule_type,
                params=entry.get("params", {}) or {},
                weight=float(entry.get("weight", 10.0)),
                required=bool(entry.get("required", False)),
                id=entry.get("id", ""),
            )
        )

    if not rules:
        raise StrategyConfigError(f"{path.name}: keine Regeln definiert")

    uf = raw.get("universe_filter", {}) or {}
    risk = raw.get("risk", {}) or {}
    scoring = raw.get("scoring", {}) or {}

    strategy = Strategy(
        name=raw.get("name") or path.stem,
        label=raw.get("label", path.stem),
        horizon=horizon,
        direction=Direction(raw.get("direction", "long")),
        description=raw.get("description", ""),
        benchmark=raw.get("benchmark", ""),
        universe=UniverseFilter(
            asset_class=uf.get("asset_class", ["stock", "etf"]),
            tr_status=uf.get("tr_status", ["verified", "assumed"]),
            min_avg_turnover_eur=float(uf.get("min_avg_turnover_eur", 0)),
            min_history_days=int(uf.get("min_history_days", 250)),
        ),
        rules=rules,
        min_score=float(scoring.get("min_score", 60.0)),
        risk=RiskSpec(
            stop_atr_factor=float(risk.get("stop_atr_factor", 2.0)),
            target_atr_factor=float(risk.get("target_atr_factor", 3.0)),
            atr_period=int(risk.get("atr_period", 14)),
            max_holding_days=int(risk.get("max_holding_days", 10)),
        ),
    )

    # Parameterfehler frueh melden, statt sie im Lauf als leeres Ergebnis zu
    # verstecken: Signaturen der Regeln jetzt pruefen.
    import inspect
    for spec in rules:
        signature = inspect.signature(REGISTRY[spec.type])
        unknown = set(spec.params) - (set(signature.parameters) - {"ctx"})
        if unknown:
            raise RuleConfigError(
                f"{path.name}: Regel '{spec.type}' kennt {sorted(unknown)} nicht. "
                f"Erlaubt: {sorted(set(signature.parameters) - {'ctx'})}"
            )
    return strategy


def load_all(directory: Path) -> dict[str, Strategy]:
    strategies: dict[str, Strategy] = {}
    for path in sorted(directory.glob("*.yaml")):
        try:
            strategy = load_strategy(path)
        except (StrategyConfigError, RuleConfigError) as exc:
            log.error("Strategie uebersprungen: %s", exc)
            continue
        strategies[strategy.name] = strategy
    return strategies
