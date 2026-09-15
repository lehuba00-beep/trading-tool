# Signal-Logik

Grundsatz: Jeder Horizont bekommt **eigene Indikatoren und eine eigene
Datenbasis-Länge**. Ein RSI(2) ist für einen Sechsmonatshorizont Rauschen, ein
Golden Cross für fünf Tage zu träge. Alle Regeln arbeiten auf Tagesbalken.

Zweitens: Es wird immer zwischen **Filter** (Pflichtbedingung, K.-o.-Kriterium)
und **Punktregel** (zahlt auf den Score ein) unterschieden. Ein Score ohne
Filter produziert Treffer, die formal Punkte sammeln, aber gegen den
übergeordneten Trend laufen.

## 1. Kurzfristig (1–5 Tage bzw. 1–4 Wochen)

Historie: ≥ 1 Jahr. Charakter: Pullback im Trend oder Ausbruch mit Volumen.

| Baustein | Typische Parameter | Rolle |
|---|---|---|
| Trendfilter | Close > EMA(50); optional Close > SMA(200) | Filter – nur mit dem Trend handeln |
| Liquiditätsfilter | Ø Umsatz 20 Tage > 1 Mio € | Filter – Spread frisst sonst den Vorteil |
| RSI(2) < 10 | Mean-Reversion-Pullback | Punkte |
| RSI(14) 30/70 | klassische Überdehnung | Punkte (alternativ zu RSI(2)) |
| MACD(12,26,9) Kreuzung | Momentumwechsel | Punkte |
| ROC(5), ROC(10) | kurzfristiges Momentum | Punkte |
| Relatives Volumen > 1,5× (20 Tage) | Beteiligung am Move | Punkte – ein Ausbruch ohne Volumen ist meist keiner |
| Donchian(20)-Ausbruch | Ausbruch über 20-Tage-Hoch | Punkte |
| Bollinger-Squeeze | Bandbreite im unteren Perzentil → Ausbruch erwartbar | Punkte |
| Abstand 52-Wochen-Hoch < 10 % | relative Stärke | Punkte |
| Gap-Erkennung | Overnight-Gap > 2 % | Kontext/Warnung |
| ATR(14) | Stop, Ziel, Positionsgröße | Kennzahl |

**Bewusst getrennte Profile:** „Pullback“ (RSI(2) im Aufwärtstrend) und
„Ausbruch“ (Donchian + Volumen) sind gegensätzliche Setups. In einem Score
vermischt heben sie sich teilweise auf. Vorschlag: zwei kurzfristige Profile,
in der UI als Reiter.

## 2. Mittelfristig (1–6 Monate, konfigurierbar)

Historie: ≥ 2 Jahre.

| Baustein | Typische Parameter | Rolle |
|---|---|---|
| Trendstruktur | Close > SMA(50) > SMA(200) | Filter |
| Golden Cross | SMA(50) kreuzt SMA(200) in den letzten n Tagen | Punkte |
| ADX(14) > 20–25 | Trendstärke – trennt Trend von Seitwärts | Filter oder Punkte |
| Relative Stärke vs. Benchmark | 3-/6-Monats-Performance minus Index | Punkte – zentral: den Index zu schlagen ist der eigentliche Zweck |
| Wochen-MACD | Momentum auf höherem Zeitrahmen | Punkte |
| Abstand 52-Wochen-Hoch < 15 % | Punkte |
| Max. Drawdown 6 Monate | Risikokennzahl | Kennzahl |
| Volatilität (annualisiert) | Positionsgröße | Kennzahl |

## 3. Langfristig (ab 6 Monaten, konfigurierbar)

Historie: ≥ 3–5 Jahre.

| Baustein | Typische Parameter | Rolle |
|---|---|---|
| Regimefilter | Close > SMA(200), SMA(200) steigend | Filter |
| 12-1-Momentum | 12-Monats-Rendite ohne den letzten Monat | Punkte – der in der Forschung robusteste Momentum-Ansatz; der ausgelassene Monat entfernt die kurzfristige Umkehr |
| Relative Stärke 6/12 Monate | vs. Benchmark | Punkte |
| Volatilität niedrig | risikoadjustiert | Punkte |
| Trendkonsistenz | Anteil Monate über SMA(200) | Punkte |
| Fundamentaldaten (optional) | KGV, KBV, Dividendenrendite, Umsatz-/Gewinnwachstum, Verschuldung | Punkte – s. offener Punkt |

Für **ETFs** greift das Fundamentalteil nicht. Sie bekommen ein eigenes
Regelset: Trend, relative Stärke, Volatilität, ergänzt um Stammdaten (TER,
Fondsvolumen, Replikationsart), die als statische Felder im Universum gepflegt
werden.

**Zu Fundamentaldaten:** Kostenlos verfügbare Fundamentaldaten sind in
Abdeckung und Aktualität schwach und teilweise schlicht falsch. Die
Empfehlung lautet, langfristig zunächst rein trend-/momentumbasiert zu fahren
und Fundamentaldaten erst zu ergänzen, wenn eine belastbare Quelle feststeht.

## 4. Scoring

```
score = 100 × (Summe Gewichte erfüllter Punktregeln / Summe aller Gewichte)
Pflichtfilter nicht erfüllt → kein Treffer (kein Score)
```

Angezeigt werden neben dem Score immer die **ausgelösten Einzelregeln**. Eine
nackte Zahl „87“ ist nicht überprüfbar; „Trend + Volumen + Ausbruch, kein
Momentum“ ist es. Das ist auch die Abgrenzung zur Empfehlung: Das Tool legt
offen, welche Bedingung zutrifft, und bewertet nicht, ob gekauft werden soll.

**Ranking** je Horizont nach Score, bei Gleichstand nach Liquidität.

## 5. Risiko-Kennzahlen je Treffer

Rein rechnerische Größen, keine Empfehlung:

* **Stop-Vorschlag:** Einstieg − 2 × ATR(14) (Long).
* **Zielzone:** Einstieg + 3 × ATR(14) → Chance-Risiko-Verhältnis 1,5.
* **Positionsgröße** bei vorgegebenem Risiko pro Position:
  `Stückzahl = (Kapital × Risiko%) / (Einstieg − Stop)`.
* **Erwartete Haltedauer** aus dem Profil (z. B. max. 10 Handelstage).

## 6. Derivate-Mathematik (ohne Produktdaten)

Für ein Knock-Out-Zertifikat (Long) gilt näherungsweise:

```
Zertifikatspreis ≈ (Basiswertkurs − Basispreis) × Bezugsverhältnis   (+ Aufgeld)
Hebel            ≈ (Basiswertkurs × Bezugsverhältnis) / Zertifikatspreis
                 ≈ Basiswertkurs / (Basiswertkurs − Basispreis)
                 ≈ 1 / relativer Abstand zur Knock-Out-Schwelle
```

Daraus folgt unmittelbar die praktisch wichtigste Regel: **Der Hebel ist der
Kehrwert des Schwellenabstands.** Hebel 20 bedeutet, dass 5 % Rückgang im
Basiswert den Totalverlust auslösen.

Daraus leitet das Tool ab:

1. Stop-Abstand aus der Volatilität: `2 × ATR(14) / Kurs` (z. B. 4 %).
2. Sicherheitspuffer: Die Knock-Out-Schwelle sollte deutlich hinter dem Stop
   liegen, Vorschlag Faktor 1,5 → Mindestabstand ≈ 6 %.
3. Maximal sinnvoller Hebel ≈ `1 / 0,06` ≈ **16**.
4. Verlust bei Stop-Auslösung ≈ `Positionswert × Hebel × Stop-Abstand`.

Angezeigt wird also: „ATR-basierter Stop 4 % → Schwelle mindestens 6 % entfernt
→ Hebel höchstens ca. 16“. Das ist reine Arithmetik und braucht keinen einzigen
Zertifikatskurs.

**Produkttyp-Hinweise**, die das Tool zum Horizont ausgibt:

* **Knock-Out:** Totalverlust bei Schwellenberührung, auch außerhalb der
  Handelszeiten des Basiswerts. Nur kurzfristig.
* **Optionsschein:** zusätzlich Zeitwertverlust und Vega – eine richtige
  Richtungsprognose kann trotzdem Geld verlieren, wenn die Volatilität fällt.
* **Faktor-Zertifikat:** täglicher Reset, pfadabhängig. In Seitwärtsmärkten
  verliert es auch ohne Bewegung im Basiswert. Nur bei bestätigtem Trend
  (z. B. ADX > 25) und kurzer Haltedauer.
* Bei allen: **Emittentenrisiko** (Inhaberschuldverschreibung) und Spread.

Konsequenz für die UI: Derivate-Hinweise werden nur bei kurz- und begrenzt bei
mittelfristigen Signalen angeboten, nicht bei langfristigen.

## 7. Validierung der Signalgüte (optional, M6)

Bevor man einer Regel Geld anvertraut, gehört sie überprüft. Vorgesehen ist
keine Backtest-Engine mit Orderausführung, sondern eine schlanke Auswertung:
Für jedes historische Signal die Vorwärtsrendite über den Horizont berechnen und
Trefferquote, Median und Verteilung gegen die Vergleichsgruppe „alle Titel,
gleicher Zeitraum“ stellen.

Zu beachten wären dabei: Look-ahead vermeiden (Signal auf Schlusskurs →
Einstieg frühestens am Folgetag), Survivorship Bias (delistete Titel fehlen in
allen kostenlosen Quellen), und die Tatsache, dass mit genügend
Parametervariationen jede Regel irgendwann gut aussieht.
