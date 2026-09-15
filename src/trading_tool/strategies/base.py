"""Strategiedefinition und Auswertung."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ..domain.enums import Direction, Horizon
from ..domain.models import RuleHit
from .context import IndicatorContext
from .rules import evaluate as evaluate_rule


@dataclass(slots=True)
class RuleSpec:
    type: str
    params: dict = field(default_factory=dict)
    weight: float = 10.0
    required: bool = False
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            suffix = "_".join(str(v) for v in self.params.values() if not isinstance(v, list))
            self.id = f"{self.type}_{suffix}".rstrip("_")


@dataclass(slots=True)
class UniverseFilter:
    asset_class: list[str] = field(default_factory=lambda: ["stock", "etf"])
    tr_status: list[str] = field(default_factory=lambda: ["verified", "assumed"])
    min_avg_turnover_eur: float = 0.0
    min_history_days: int = 250


@dataclass(slots=True)
class RiskSpec:
    """Reine Kursabstaende. Keine Stueckzahlen, kein Depotvolumen."""

    stop_atr_factor: float = 2.0
    target_atr_factor: float = 3.0
    atr_period: int = 14
    max_holding_days: int = 10


@dataclass(slots=True)
class Strategy:
    name: str
    label: str
    horizon: Horizon
    direction: Direction = Direction.LONG
    description: str = ""
    benchmark: str = ""
    universe: UniverseFilter = field(default_factory=UniverseFilter)
    rules: list[RuleSpec] = field(default_factory=list)
    min_score: float = 60.0
    risk: RiskSpec = field(default_factory=RiskSpec)

    @property
    def required_rules(self) -> list[RuleSpec]:
        return [r for r in self.rules if r.required]

    @property
    def scored_rules(self) -> list[RuleSpec]:
        return [r for r in self.rules if not r.required]

    def evaluate(self, ctx: IndicatorContext) -> StrategyEvaluation:
        series: dict[str, pd.Series] = {}
        labels: dict[str, str] = {}

        for spec in self.rules:
            result, label = evaluate_rule(spec.type, ctx, spec.params)
            series[spec.id] = result
            labels[spec.id] = label

        index = ctx.index
        passes = pd.Series(True, index=index)
        for spec in self.required_rules:
            passes &= series[spec.id]

        total_weight = sum(spec.weight for spec in self.scored_rules)
        if total_weight <= 0:
            score = pd.Series(100.0, index=index).where(passes, 0.0)
        else:
            acc = pd.Series(0.0, index=index)
            for spec in self.scored_rules:
                acc += series[spec.id].astype(float) * spec.weight
            score = acc / total_weight * 100.0

        # Ein nicht erfuellter Pflichtfilter ist ein K.-o.-Kriterium, kein
        # Punktabzug. Sonst sammelt ein Titel gegen den Trend genug Punkte, um
        # in der Liste aufzutauchen.
        score = score.where(passes, 0.0)

        # Die ersten Balken haben keine gueltigen Indikatorwerte. Ohne diese
        # Sperre entstuende am Reihenanfang ein Scheinsignal aus lauter
        # not-a-number-Vergleichen, die als False gelten.
        warmup = min(self.universe.min_history_days, max(1, len(index) - 1))
        valid = pd.Series(False, index=index)
        valid.iloc[warmup:] = True

        eligible = passes & valid & score.ge(self.min_score)
        return StrategyEvaluation(
            strategy=self, rule_series=series, rule_labels=labels,
            score=score.where(valid, 0.0), passes_filter=passes & valid, eligible=eligible,
        )


@dataclass(slots=True)
class StrategyEvaluation:
    strategy: Strategy
    rule_series: dict[str, pd.Series]
    rule_labels: dict[str, str]
    score: pd.Series
    passes_filter: pd.Series
    eligible: pd.Series

    def hits_at(self, position: int = -1) -> list[RuleHit]:
        return [
            RuleHit(
                rule_id=spec.id,
                label=self.rule_labels[spec.id],
                triggered=bool(self.rule_series[spec.id].iloc[position]),
                weight=spec.weight,
                required=spec.required,
            )
            for spec in self.strategy.rules
        ]
