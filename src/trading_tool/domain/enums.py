"""Aufzaehlungstypen der Fachdomaene."""

from __future__ import annotations

from enum import StrEnum


class Horizon(StrEnum):
    """Anlagehorizont. Die Zeitraeume je Profil stehen in der Strategie-YAML."""

    SHORT = "kurzfristig"
    SWING = "swing"
    MID = "mittelfristig"
    LONG = "langfristig"

    @property
    def label(self) -> str:
        return {
            Horizon.SHORT: "Kurzfristig (1-5 Tage)",
            Horizon.SWING: "Swing (1-4 Wochen)",
            Horizon.MID: "Mittelfristig (1-6 Monate)",
            Horizon.LONG: "Langfristig (ab 6 Monaten)",
        }[self]


class AssetClass(StrEnum):
    STOCK = "stock"
    ETF = "etf"
    INDEX = "index"


class TRStatus(StrEnum):
    """Handelbarkeit bei Trade Republic.

    Es gibt keine abfragbare Quelle dafuer; der Status wird kuratiert gepflegt.
    ``ASSUMED`` heisst: aus einer Liste uebernommen, bei der eine hohe
    Trefferwahrscheinlichkeit besteht, aber nicht einzeln geprueft.
    """

    VERIFIED = "verified"
    ASSUMED = "assumed"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"

    @property
    def label(self) -> str:
        return {
            TRStatus.VERIFIED: "geprueft",
            TRStatus.ASSUMED: "angenommen",
            TRStatus.UNAVAILABLE: "nicht handelbar",
            TRStatus.UNKNOWN: "unbekannt",
        }[self]


class Direction(StrEnum):
    LONG = "long"
    SHORT = "short"
