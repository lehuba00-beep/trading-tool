"""Datenqualitaetspruefung fuer Kursreihen.

Anlass: Die kostenlosen Kursquellen liefern gelegentlich fehlerhafte
Einzelkurse. Ein falscher Ausreisser nach oben erzeugt ein makelloses
Donchian-Ausbruchssignal - der Screener kann nicht wissen, dass der Kurs nie
gehandelt wurde. Ebenso still ist eine Reihe, die vor drei Wochen aufgehoert
hat zu laufen: Alle Indikatoren rechnen weiter, nur eben auf altem Stand.

Die Pruefungen sind bewusst konservativ ausgelegt. Ein Fehlalarm kostet einen
Blick auf den Chart, ein uebersehener Fehler kostet Geld.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum

import numpy as np
import pandas as pd


class Severity(StrEnum):
    OK = "ok"
    HINWEIS = "hinweis"
    WARNUNG = "warnung"

    @property
    def rank(self) -> int:
        return {Severity.OK: 0, Severity.HINWEIS: 1, Severity.WARNUNG: 2}[self]


@dataclass(slots=True)
class Finding:
    code: str
    severity: Severity
    message: str
    detail: str = ""


@dataclass(slots=True)
class QualityReport:
    isin: str = ""
    bars: int = 0
    last_bar: date | None = None
    findings: list[Finding] = field(default_factory=list)

    @property
    def severity(self) -> Severity:
        if not self.findings:
            return Severity.OK
        return max((f.severity for f in self.findings), key=lambda s: s.rank)

    @property
    def ok(self) -> bool:
        return self.severity is Severity.OK

    @property
    def codes(self) -> list[str]:
        return [f.code for f in self.findings]

    def summary(self) -> str:
        if self.ok:
            return "keine Auffaelligkeiten"
        return "; ".join(f.message for f in self.findings)


# Ein Tagessprung ueber dieser Groesse ist bei einem Standardwert
# erklaerungsbeduerftig - meist eine Nachricht, manchmal ein Datenfehler.
SPIKE_THRESHOLD_PCT = 20.0
# Liegt der Kurs am Folgetag wieder nahe am Niveau vor dem Sprung - genauer:
# ist der Abstand kleiner als ein Drittel der Sprunghoehe - war es fast immer
# ein fehlerhafter Einzelkurs und keine echte Bewegung.
SPIKE_REVERSAL_RATIO = 0.67
STALE_TRADING_DAYS = 5
MIN_COVERAGE_RATIO = 0.85
FLATLINE_DAYS = 10


def _expected_business_days(index: pd.DatetimeIndex) -> int:
    if len(index) < 2:
        return len(index)
    return int(np.busday_count(index[0].date(), index[-1].date())) + 1


def check_series(
    frame: pd.DataFrame, isin: str = "", today: date | None = None
) -> QualityReport:
    """Eine Kursreihe pruefen. ``frame`` hat den Aufbau aus providers.base."""
    report = QualityReport(isin=isin)
    if frame is None or frame.empty:
        report.findings.append(
            Finding("leer", Severity.WARNUNG, "keine Kursdaten",
                    "Fuer diesen Titel liegt keine Kursreihe im Cache.")
        )
        return report

    today = today or date.today()
    report.bars = len(frame)
    report.last_bar = frame.index[-1].date()

    _check_stale(report, today)
    _check_coverage(report, frame)
    _check_spikes(report, frame)
    _check_ohlc(report, frame)
    _check_flatline(report, frame)
    _check_volume(report, frame)
    return report


def _check_stale(report: QualityReport, today: date) -> None:
    if report.last_bar is None:
        return
    alter = int(np.busday_count(report.last_bar, today))
    if alter > STALE_TRADING_DAYS:
        report.findings.append(
            Finding(
                "veraltet", Severity.WARNUNG,
                f"Kursreihe endet vor {alter} Handelstagen",
                f"Letzter Balken {report.last_bar:%d.%m.%Y}. Indikatoren rechnen "
                "weiter, aber auf altem Stand - das Signal beschreibt die "
                "Vergangenheit.",
            )
        )


def _check_coverage(report: QualityReport, frame: pd.DataFrame) -> None:
    """Fehlende Handelstage innerhalb der Reihe.

    Feiertage unterscheiden sich je Boerse, deshalb wird nicht auf einzelne
    Luecken geprueft, sondern auf die Abdeckung insgesamt.
    """
    erwartet = _expected_business_days(frame.index)
    if erwartet < 60:
        return
    abdeckung = len(frame) / erwartet
    if abdeckung < MIN_COVERAGE_RATIO:
        fehlend = erwartet - len(frame)
        report.findings.append(
            Finding(
                "luecken", Severity.HINWEIS,
                f"{abdeckung * 100:.0f} % Abdeckung ({fehlend} Handelstage fehlen)",
                "Feiertage erklaeren einen Teil davon. Bei deutlich unter 90 % "
                "hat die Quelle vermutlich Tage nicht geliefert.",
            )
        )


def _check_spikes(report: QualityReport, frame: pd.DataFrame) -> None:
    """Einzelne Ausreisser, die am Folgetag weitgehend zurueckgenommen werden.

    Das ist die Signatur eines fehlerhaften Einzelkurses: Ein echter
    Kurssprung bleibt, ein Datenfehler verschwindet am naechsten Tag wieder.
    """
    close = frame["close"]
    if len(close) < 3:
        return
    rendite = close.pct_change() * 100

    # Verglichen wird das Kursniveau vor und nach dem Balken, nicht die Summe
    # der Tagesrenditen: Ein Sprung um +45 % und vollstaendig zurueck ergibt
    # -31 %, in der Summe also +14 %. Das ist Prozentarithmetik, kein
    # Restfehler - wer darauf schwellt, uebersieht genau die grossen Ausreisser.
    rueckkehr = (close.shift(-1) / close.shift(1) - 1).abs() * 100

    verdaechtig = (rendite.abs() > SPIKE_THRESHOLD_PCT) & (
        rueckkehr < rendite.abs() * (1 - SPIKE_REVERSAL_RATIO)
    )
    treffer = frame.index[verdaechtig.fillna(False).to_numpy()]
    if len(treffer) == 0:
        return

    letzte = [f"{d:%d.%m.%Y} ({rendite.loc[d]:+.0f} %)" for d in treffer[-3:]]
    # Ein Ausreisser in den letzten 30 Balken kann ein aktuelles Signal
    # ausgeloest haben - das ist mehr als ein Schoenheitsfehler.
    aktuell = any(d >= frame.index[-30] for d in treffer) if len(frame) >= 30 else True
    report.findings.append(
        Finding(
            "ausreisser",
            Severity.WARNUNG if aktuell else Severity.HINWEIS,
            f"{len(treffer)} verdaechtige Kurssprünge",
            "Sprung mit Rücknahme am Folgetag - typisch für einen fehlerhaften "
            "Einzelkurs. Zuletzt: " + ", ".join(letzte),
        )
    )


def _check_ohlc(report: QualityReport, frame: pd.DataFrame) -> None:
    """Innere Widersprüche. Wenn die auftreten, ist der Balken unbrauchbar."""
    hoch, tief = frame["high"], frame["low"]
    schluss, eroeffnung = frame["close"], frame["open"]

    kaputt = (hoch < tief) | (schluss > hoch) | (schluss < tief)
    gueltig = eroeffnung.notna()
    kaputt |= gueltig & ((eroeffnung > hoch) | (eroeffnung < tief))

    anzahl = int(kaputt.fillna(False).sum())
    if anzahl:
        report.findings.append(
            Finding(
                "ohlc", Severity.WARNUNG, f"{anzahl} widersprüchliche Balken",
                "Hoch unter Tief oder Schluss außerhalb der Tagesspanne. "
                "Solche Balken verfälschen ATR und Ausbruchsregeln.",
            )
        )


def _check_flatline(report: QualityReport, frame: pd.DataFrame) -> None:
    """Unveraenderte Schlusskurse ueber viele Tage - meist eine tote Reihe."""
    close = frame["close"].tail(120)
    if len(close) < FLATLINE_DAYS + 1:
        return
    unveraendert = close.diff().eq(0)
    # Laengste zusammenhaengende Serie
    laengste = int(
        unveraendert.groupby((~unveraendert).cumsum()).cumsum().max() or 0
    )
    if laengste >= FLATLINE_DAYS:
        report.findings.append(
            Finding(
                "flatline", Severity.WARNUNG,
                f"{laengste} Tage ohne Kursänderung",
                "Die Quelle liefert vermutlich einen eingefrorenen Kurs statt "
                "aktueller Daten.",
            )
        )


def _check_volume(report: QualityReport, frame: pd.DataFrame) -> None:
    volumen = frame["volume"].tail(60)
    if volumen.empty:
        return
    fehlend = int(volumen.isna().sum() + volumen.fillna(0).eq(0).sum())
    if fehlend > len(volumen) * 0.3:
        report.findings.append(
            Finding(
                "volumen", Severity.HINWEIS,
                f"Volumen fehlt an {fehlend} der letzten {len(volumen)} Tage",
                "Regeln zum relativen Volumen und der Liquiditätsfilter "
                "greifen für diesen Titel nicht zuverlässig.",
            )
        )


def stale_cutoff(today: date | None = None) -> date:
    today = today or date.today()
    return today - timedelta(days=STALE_TRADING_DAYS * 2)
