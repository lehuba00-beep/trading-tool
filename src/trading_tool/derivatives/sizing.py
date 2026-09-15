"""Hebel- und Barrierenmathematik fuer Hebelprodukte.

Der Kern in einem Satz: **Der Hebel eines Knock-Out-Produkts ist naeherungsweise
der Kehrwert des relativen Abstands zur Knock-Out-Schwelle.**

    Zertifikatspreis ~ (Basiswertkurs - Basispreis) * Bezugsverhaeltnis
    Hebel            ~ Basiswertkurs / (Basiswertkurs - Basispreis)
                     ~ 1 / Schwellenabstand

Hebel 20 heisst also: 5 % Rueckgang im Basiswert loesen den Totalverlust aus.
Daraus laesst sich alles Noetige ableiten, ohne einen einzigen Zertifikatskurs
zu kennen - und genau deshalb kommt die erste Ausbaustufe ohne Emittentendaten
aus.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.enums import Direction, Horizon

# Die Schwelle muss deutlich hinter dem Stop liegen. Wird sie beruehrt, ist das
# Produkt wertlos - ein ausgeloester Stop kostet dagegen nur den geplanten
# Verlust. Dieser Puffer ist die wichtigste Groesse im ganzen Modul.
DEFAULT_BARRIER_BUFFER = 1.5


@dataclass(slots=True)
class LeverageHint:
    direction: Direction
    stop_distance_pct: float
    min_barrier_distance_pct: float
    max_leverage: float
    suggested_barrier: float
    loss_at_stop_pct: float
    buffer_factor: float

    def as_text(self) -> str:
        return (
            f"Stop {self.stop_distance_pct:.1f} % entfernt -> Schwelle mindestens "
            f"{self.min_barrier_distance_pct:.1f} % entfernt -> Hebel hoechstens "
            f"ca. {self.max_leverage:.0f}"
        )


def leverage_from_barrier(price: float, barrier: float) -> float:
    """Hebel aus Kurs und Knock-Out-Schwelle."""
    distance = abs(price - barrier)
    if price <= 0 or distance <= 0:
        return float("inf")
    return price / distance


def barrier_from_distance(price: float, distance_pct: float, direction: Direction) -> float:
    factor = 1 - distance_pct / 100 if direction is Direction.LONG else 1 + distance_pct / 100
    return price * factor


def loss_at_stop_pct(leverage: float, stop_distance_pct: float) -> float:
    """Verlust der Zertifikatsposition, wenn der Stop im Basiswert ausloest.

    Bei Hebel 10 und 4 % Stop-Abstand sind das rund 40 % der Position - nicht
    4 %. Das ist die Zahl, die in der Praxis unterschaetzt wird.
    """
    return min(100.0, leverage * stop_distance_pct)


def leverage_hint(
    price: float,
    stop: float,
    direction: Direction = Direction.LONG,
    buffer_factor: float = DEFAULT_BARRIER_BUFFER,
) -> LeverageHint | None:
    """Leitet aus Kurs und ATR-Stop den maximal sinnvollen Hebel ab."""
    if price <= 0 or stop <= 0:
        return None
    stop_distance_pct = abs(price - stop) / price * 100
    if stop_distance_pct <= 0:
        return None

    min_barrier_distance = stop_distance_pct * buffer_factor
    max_leverage = 100.0 / min_barrier_distance
    return LeverageHint(
        direction=direction,
        stop_distance_pct=round(stop_distance_pct, 2),
        min_barrier_distance_pct=round(min_barrier_distance, 2),
        max_leverage=round(max_leverage, 1),
        suggested_barrier=round(barrier_from_distance(price, min_barrier_distance, direction), 4),
        loss_at_stop_pct=round(loss_at_stop_pct(max_leverage, stop_distance_pct), 1),
        buffer_factor=buffer_factor,
    )


# Produkttyp-Hinweise je Horizont. Bewusst Eignung und Risiko, keine Empfehlung.
PRODUCT_NOTES: dict[str, dict[str, str]] = {
    "knock_out": {
        "label": "Knock-Out-Zertifikat",
        "eignung": "kurzfristig",
        "hinweis": (
            "Totalverlust bei Beruehrung der Schwelle - auch ausserhalb der "
            "Handelszeiten des Basiswerts, etwa durch eine Eroeffnungsluecke."
        ),
    },
    "optionsschein": {
        "label": "Optionsschein",
        "eignung": "kurz- bis mittelfristig",
        "hinweis": (
            "Zusaetzlich Zeitwertverlust und Volatilitaetsabhaengigkeit: Eine "
            "richtige Richtungsprognose kann trotzdem Geld verlieren, wenn die "
            "Volatilitaet faellt."
        ),
    },
    "faktor": {
        "label": "Faktor-Zertifikat",
        "eignung": "nur bei bestaetigtem Trend",
        "hinweis": (
            "Taeglicher Reset, pfadabhaengig. In Seitwaertsmaerkten verliert es "
            "auch dann, wenn der Basiswert am Ende unveraendert notiert."
        ),
    },
}

# Langfristige Signale bekommen bewusst keine Derivate-Hinweise: Hebelprodukte
# sind fuer Haltedauern ab sechs Monaten nicht das passende Vehikel.
HORIZON_PRODUCTS: dict[Horizon, list[str]] = {
    Horizon.SHORT: ["knock_out", "optionsschein", "faktor"],
    Horizon.SWING: ["knock_out", "optionsschein"],
    Horizon.MID: ["optionsschein"],
    Horizon.LONG: [],
}


def products_for(horizon: Horizon, adx: float | None = None) -> list[dict]:
    """Passende Produkttypen. Faktor-Zertifikate nur bei bestaetigtem Trend."""
    keys = HORIZON_PRODUCTS.get(horizon, [])
    if adx is not None and adx < 25:
        keys = [k for k in keys if k != "faktor"]
    return [{"key": k, **PRODUCT_NOTES[k]} for k in keys]


GENERAL_RISKS = [
    "Emittentenrisiko: Hebelprodukte sind Inhaberschuldverschreibungen. Bei "
    "Zahlungsunfaehigkeit des Emittenten droht der Totalverlust unabhaengig vom "
    "Kursverlauf des Basiswerts.",
    "Der Emittent stellt die Kurse selbst - der Spread ist ein echter Kostenblock.",
    "Die Angaben hier sind gerechnete Groessen aus Kurs und Volatilitaet, keine "
    "Produktempfehlung und keine Anlageberatung.",
]
