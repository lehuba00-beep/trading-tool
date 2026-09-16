"""Kurscharts als eingebettetes SVG.

Bewusst serverseitig gezeichnet statt mit einer Chart-Bibliothek: kein CDN,
keine JavaScript-Abhaengigkeit, nichts, was PyInstaller mitpacken muesste - und
die App funktioniert vollstaendig ohne Internetverbindung.
"""

from __future__ import annotations

import pandas as pd

WIDTH = 960
PRICE_HEIGHT = 340
VOLUME_HEIGHT = 70
PADDING_LEFT = 8
PADDING_RIGHT = 62
PADDING_TOP = 12
GAP = 14


def _scale(value: float, low: float, high: float, top: float, bottom: float) -> float:
    if high <= low:
        return (top + bottom) / 2
    return bottom - (value - low) / (high - low) * (bottom - top)


def candlestick(
    frame: pd.DataFrame,
    overlays: dict[str, pd.Series] | None = None,
    bars: int = 140,
    title: str = "",
    levels: list[tuple[str, float, str]] | None = None,
) -> str:
    """Kerzenchart mit Volumen, Linien-Overlays und waagerechten Marken.

    ``levels`` sind Marken wie Stop und Ziel als (Beschriftung, Kurs, Stilklasse).
    Sie gehen in die Skalierung ein - ein Stop unterhalb des sichtbaren
    Bereichs waere eine Marke, die man gerade dann nicht sieht, wenn sie zaehlt.
    """
    if frame is None or frame.empty:
        return '<p class="muted">Keine Kursdaten vorhanden.</p>'

    data = frame.tail(bars)
    overlays = {
        name: series.reindex(data.index) for name, series in (overlays or {}).items()
    }

    levels = [lv for lv in (levels or []) if lv[1] is not None and pd.notna(lv[1])]

    highs = [data["high"].max()] + [s.max() for s in overlays.values() if s.notna().any()]
    lows = [data["low"].min()] + [s.min() for s in overlays.values() if s.notna().any()]
    highs += [float(lv[1]) for lv in levels]
    lows += [float(lv[1]) for lv in levels]
    high = float(max(v for v in highs if pd.notna(v)))
    low = float(min(v for v in lows if pd.notna(v)))
    span = (high - low) or 1.0
    high += span * 0.04
    low -= span * 0.04

    plot_width = WIDTH - PADDING_LEFT - PADDING_RIGHT
    step = plot_width / max(len(data), 1)
    body = max(1.4, step * 0.62)
    price_top = PADDING_TOP
    price_bottom = PADDING_TOP + PRICE_HEIGHT
    volume_top = price_bottom + GAP
    volume_bottom = volume_top + VOLUME_HEIGHT
    total_height = volume_bottom + 22

    parts: list[str] = [
        f'<svg class="chart" viewBox="0 0 {WIDTH} {total_height}" '
        f'role="img" aria-label="Kursverlauf {title}" preserveAspectRatio="xMidYMid meet">'
    ]

    # Gitternetz mit Preisachse
    for fraction in (0, 0.25, 0.5, 0.75, 1.0):
        y = price_top + fraction * PRICE_HEIGHT
        price = high - fraction * (high - low)
        parts.append(
            f'<line class="grid" x1="{PADDING_LEFT}" y1="{y:.1f}" '
            f'x2="{WIDTH - PADDING_RIGHT}" y2="{y:.1f}"/>'
            f'<text class="axis" x="{WIDTH - PADDING_RIGHT + 6}" y="{y + 4:.1f}">'
            f"{price:,.2f}</text>"
        )

    max_volume = float(data["volume"].max() or 0)

    for index, (stamp, row) in enumerate(data.iterrows()):
        x = PADDING_LEFT + index * step + step / 2
        rising = float(row["close"]) >= float(row["open"])
        css = "up" if rising else "down"

        y_high = _scale(float(row["high"]), low, high, price_top, price_bottom)
        y_low = _scale(float(row["low"]), low, high, price_top, price_bottom)
        y_open = _scale(float(row["open"]), low, high, price_top, price_bottom)
        y_close = _scale(float(row["close"]), low, high, price_top, price_bottom)
        top = min(y_open, y_close)
        height = max(abs(y_close - y_open), 1.0)

        parts.append(
            f'<line class="wick {css}" x1="{x:.1f}" y1="{y_high:.1f}" '
            f'x2="{x:.1f}" y2="{y_low:.1f}"/>'
            f'<rect class="candle {css}" x="{x - body / 2:.1f}" y="{top:.1f}" '
            f'width="{body:.1f}" height="{height:.1f}">'
            f"<title>{stamp:%d.%m.%Y} | O {row['open']:.2f} H {row['high']:.2f} "
            f"L {row['low']:.2f} C {row['close']:.2f}</title></rect>"
        )

        if max_volume > 0 and pd.notna(row["volume"]):
            vh = float(row["volume"]) / max_volume * VOLUME_HEIGHT
            parts.append(
                f'<rect class="vol {css}" x="{x - body / 2:.1f}" '
                f'y="{volume_bottom - vh:.1f}" width="{body:.1f}" height="{vh:.1f}"/>'
            )

    for beschriftung, wert, stil in levels:
        y = _scale(float(wert), low, high, price_top, price_bottom)
        breite = 8 + len(beschriftung) * 6.5
        parts.append(
            f'<line class="level {stil}" x1="{PADDING_LEFT}" y1="{y:.1f}" '
            f'x2="{WIDTH - PADDING_RIGHT}" y2="{y:.1f}"/>'
            f'<rect class="level-tag {stil}" x="{PADDING_LEFT + 2}" '
            f'y="{y - 8:.1f}" width="{breite:.0f}" height="16" rx="3"/>'
            f'<text class="level-text" x="{PADDING_LEFT + 6}" y="{y + 4:.1f}">'
            f"{beschriftung}</text>"
        )

    for number, series in enumerate(overlays.values(), start=1):
        points = [
            f"{PADDING_LEFT + i * step + step / 2:.1f},"
            f"{_scale(float(v), low, high, price_top, price_bottom):.1f}"
            for i, v in enumerate(series)
            if pd.notna(v)
        ]
        if len(points) > 1:
            parts.append(
                f'<polyline class="overlay ov{number}" points="{" ".join(points)}"/>'
            )

    # Zeitachse: erster, mittlerer und letzter Balken genuegen
    for position in (0, len(data) // 2, len(data) - 1):
        stamp = data.index[position]
        x = PADDING_LEFT + position * step + step / 2
        anchor = "start" if position == 0 else ("end" if position == len(data) - 1 else "middle")
        parts.append(
            f'<text class="axis" x="{x:.1f}" y="{total_height - 6}" '
            f'text-anchor="{anchor}">{stamp:%d.%m.%y}</text>'
        )

    parts.append("</svg>")

    legend = " ".join(
        f'<span class="legend ov{n}">{name}</span>'
        for n, name in enumerate(overlays, start=1)
    )
    return f'<div class="chart-wrap">{"".join(parts)}<div class="legend-row">{legend}</div></div>'
