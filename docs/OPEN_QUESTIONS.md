# Offene Punkte

Reihenfolge nach Auswirkung auf die Architektur. Zu jedem Punkt steht ein
Vorschlag – wo nichts entschieden wird, wird der Vorschlag umgesetzt.

## A. Entschieden (2026-09-15)

| Punkt | Entscheidung |
|---|---|
| A1 Oberfläche | **Lokale Web-UI** – FastAPI + Jinja2 + HTMX, Bindung auf `127.0.0.1`, Launcher öffnet den Browser |
| A2 Kursdaten | **yfinance primär, Stooq als Fallback**, Provider-Schicht bleibt austauschbar |
| A3 Derivate v1 | **Stufe 1** – Signale auf Basiswerten, dazu Hebel-/Barrieren-Rechner, Produkttyp-Hinweise und Emittenten-Deeplinks; keine Zertifikatskurse |
| A4 Universum | **DE/EU + US-Auswahl, Zielgröße ca. 300 Titel** – DAX, MDAX, TecDAX, EURO STOXX 50, Nasdaq-100, liquide S&P-500-Werte, gängige ETFs |
| A5 Richtung | Regelwerk richtungsfähig, v1 Long-Profile, Short in M4 |

Die ursprüngliche Fragestellung zu diesen Punkten bleibt unten als Begründung
stehen.

### Zu A (ursprüngliche Fragestellung)

**A1 – Oberfläche.** Lokale Web-UI (FastAPI + HTMX, Browser auf `127.0.0.1`)
oder native Desktop-GUI (PySide6)?
→ *Vorschlag: Web-UI.* Tabellen, Filter und Charts sind dort deutlich
günstiger; die App bleibt lokal und ohne Netzwerkfreigabe.

**A2 – Kursdatenquelle und Budget.** yfinance (kostenlos, inoffiziell, bricht
gelegentlich) genügt, oder soll direkt ein bezahlter Anbieter mit
ISIN-Mapping eingeplant werden (EODHD/Twelve Data, ca. 20–30 €/Monat)?
→ *Vorschlag: yfinance + Stooq-Fallback*, Provider-Schicht so gebaut, dass ein
Wechsel eine Datei betrifft.

**A3 – Derivate-Umfang in v1.** Nur Signale auf Basiswerten plus
Hebel-/Barrieren-Rechner und Deeplinks in die Emittenten-Produktfinder, oder
werden echte Zertifikatskurse gebraucht?
→ *Vorschlag: Stufe 1.* Echte KO-/OS-Kurse sind ohne kostenpflichtige
Datenvereinbarung realistisch nicht beschaffbar (s. DATA_SOURCES.md §3).

**A4 – Marktabdeckung und Universumsgröße.** Nur DE/EU oder auch US? 150–300
liquide Titel oder 1.000+?
→ *Vorschlag: DAX/MDAX/TecDAX + EURO STOXX 50 + Nasdaq-100/S&P-500-Auswahl,
Größenordnung 300 Titel.* Ein Lauf dauert dann wenige Minuten; bei 1.000+
Titeln werden die Rate-Limits kostenloser Quellen zum Engpass.

**A5 – Nur Long oder auch Short?** Short-Signale sind für Put-Optionsscheine
und Short-KOs relevant, verdoppeln aber Regelwerk und Tests.
→ *Vorschlag: Regelwerk richtungsfähig anlegen, v1 Long-Profile ausliefern,
Short-Profile in M4 ergänzen.*

## B. Entschieden (2026-09-15)

| Punkt | Entscheidung | Umsetzung |
|---|---|---|
| B2 Währung | **Alles in EUR** | Rohkurse werden in Originalwährung gecacht und beim Lesen über tagesgenaue FX-Kurse nach EUR umgerechnet. Indikatoren laufen auf der EUR-Reihe – der Nutzer sieht damit genau die Kursentwicklung, die bei TR im Depot ankommt |
| B3 Horizonte | **bestätigt** | Kurzfristig 1–5 Tage (zwei Profile: Pullback und Ausbruch) *und* 1–4 Wochen (Swing) als drittes Profil; mittelfristig 1–6 Monate; langfristig ab 6 Monaten. Zeiträume je Profil in der YAML änderbar |
| B5 Aktualisierung | **3× täglich** | Standard 09:30, 14:00, 22:30 (Ortszeit), in den Einstellungen änderbar – Begründung s. unten |
| B6 Benachrichtigungen | **nur in der App** | Neue Treffer werden in der Oberfläche markiert; keine Desktop-Popups, keine E-Mail |
| B7 Positionsgrößenrechner | **nein** | Kein Depotvolumen, keine Stückzahlberechnung. ATR-Stop und Zielzone bleiben als reine Kursabstände erhalten – die Knock-Out-Mathematik braucht sie |
| B8 Trefferquoten-Auswertung | **in v1** | Rückt aus M6 in den Kern. Hat Folgen für das Regelwerk, s. unten |

### Zu B5: Warum 09:30 / 14:00 / 22:30

Die Zeiten sind nicht gleichmäßig verteilt, sondern an den Handelszeiten
ausgerichtet:

* **09:30** – kurz nach Xetra-Eröffnung. Die US-Tagesbalken des Vortags sind
  final, die europäischen Eröffnungskurse liegen vor.
* **14:00** – vor US-Handelsbeginn, Zwischenstand des europäischen Tages.
* **22:30** – nach US-Schluss. Erst hier sind *alle* Tagesbalken endgültig;
  dieser Lauf ist der, auf dem die Signale des Tages beruhen.

Zwischenstände werden in der Oberfläche als vorläufig gekennzeichnet. Ein
Signal, das auf einem unfertigen Tagesbalken beruht, kann sich bis
Handelsschluss wieder auflösen – das muss sichtbar sein, sonst ist es
irreführend.

### Zu B8: Folge für das Regelwerk

Damit die Trefferquote ohne zweite Implementierung auswertbar ist, liefert
jede Regel **keinen einzelnen Wahrheitswert, sondern eine boolesche Zeitreihe**
über die gesamte Kurshistorie. Das aktuelle Screening liest davon den letzten
Wert; die Auswertung nutzt die ganze Reihe. Ohne diesen Zuschnitt gäbe es zwei
getrennte Regelauswertungen, die zwangsläufig auseinanderlaufen.

## C. Entschieden (2026-09-15)

| Punkt | Entscheidung |
|---|---|
| C1 Python | **Nicht auf dem Zielrechner installiert** → es muss eine eigenständige `.exe` geben. Konsequenz s. ARCHITECTURE.md §7 |
| C3 Sprache | Deutsch |

## D. Weiterhin offen (nicht blockierend)

**D1 – Eigene Watchlist oder TR-Export** als Ausgangsbasis für das Universum?
Bis dahin: Seed aus Indexkonstituenten mit Status `assumed`.

**D2 – Fundamentaldaten langfristig.** Vorerst rein trend-/momentumbasiert.

**D3 – Lizenz und Sichtbarkeit des Repositories.**

## E. Ursprüngliche Fragestellung (Begründungen)

**B1 – Trade-Republic-Liste.** Gibt es einen eigenen Export oder eine
Watchlist als Ausgangsbasis? Sonst Seed aus Indexkonstituenten + TR-ETF-Liste
mit Status `assumed` und schrittweiser Verifikation aus der UI heraus.

**B2 – Währungsumrechnung.** US-Titel: Kursdaten in USD, Abrechnung bei TR in
EUR. Performance und Signale in Originalwährung rechnen (sauberer für
Indikatoren) und den FX-Effekt separat ausweisen, oder alles in EUR umrechnen?
→ *Vorschlag: Indikatoren in Originalwährung, zusätzlich EUR-Performance als
Kennzahl.*

**B3 – Zeiträume der Horizonte.** Kurzfristig 1–5 Tage und 1–4 Wochen als
zwei getrennte Profile oder eines? Mittelfristig 1–6 Monate, langfristig ab 6
Monaten – bestätigt oder andere Grenzen?

**B4 – Fundamentaldaten langfristig.** Kostenlose Quellen sind lückenhaft und
teils fehlerhaft. Langfristig zunächst rein trendbasiert, oder ist eine
bezahlte Fundamentalquelle vorgesehen?

**B5 – Aktualisierung.** Einmal täglich nach Börsenschluss genügt, oder wird
ein Intraday-Refresh (verzögerte Kurse) während des Handelstags gewünscht?

**B6 – Benachrichtigungen.** Nur Anzeige in der App, oder Windows-Desktop-
Benachrichtigung bzw. E-Mail, wenn ein neues Signal auftritt?

**B7 – Risiko-/Positionsgrößenrechner.** Soll das Tool aus Kapital und
Risikoquote eine Stückzahl berechnen? Rein rechnerisch unproblematisch, aber
es setzt die Eingabe des Depotvolumens voraus – rein lokal gespeichert.

**B8 – Signalgüte-Auswertung.** Trefferquote historischer Signale schon in v1
(erhöht das Vertrauen in die Regeln erheblich) oder erst später?

### Technische Rahmenbedingungen (ursprünglich)

**C1 – Ist Python auf dem Zielrechner installiert**, oder muss es zwingend eine
eigenständige `.exe` sein? Beides ist vorgesehen; die Reihenfolge ändert sich
(`.exe`-Build kann sonst bis M5 warten).

**C2 – Windows-Version und Architektur** (Windows 10/11, x64/ARM)?

**C3 – Sprache der Oberfläche.** Deutsch angenommen.

**C4 – Lizenz und Sichtbarkeit des Repositories.** Aktuell nichts festgelegt.
