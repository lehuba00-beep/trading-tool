# Offene Punkte

Reihenfolge nach Auswirkung auf die Architektur. Zu jedem Punkt steht ein
Vorschlag – wo nichts entschieden wird, wird der Vorschlag umgesetzt.

## A. Entscheidungsrelevant vor Implementierungsbeginn

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

## B. Fachliche Klärung während M0–M2

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

## C. Technische Rahmenbedingungen

**C1 – Ist Python auf dem Zielrechner installiert**, oder muss es zwingend eine
eigenständige `.exe` sein? Beides ist vorgesehen; die Reihenfolge ändert sich
(`.exe`-Build kann sonst bis M5 warten).

**C2 – Windows-Version und Architektur** (Windows 10/11, x64/ARM)?

**C3 – Sprache der Oberfläche.** Deutsch angenommen.

**C4 – Lizenz und Sichtbarkeit des Repositories.** Aktuell nichts festgelegt.
