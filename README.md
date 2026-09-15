# Trading-Tool – Analyse- und Screening-Werkzeug (Konzeptphase)

Lokal unter Windows lauffähiges Tool zur Identifikation kurz-, mittel- und
langfristiger Handelschancen in Aktien, ETFs und (später) Derivaten, beschränkt
auf bei Trade Republic handelbare Wertpapiere.

**Status: Konzept.** In diesem Stand existiert noch kein Code – nur die
Architektur- und Entscheidungsdokumente.

## Dokumente

| Datei | Inhalt |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Tech-Stack, Schichtenmodell, Ordnerstruktur, Datenmodell, Ausbaustufen |
| [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) | Kursdatenquellen im Vergleich, Pflege der Trade-Republic-Liste, Derivate-Daten |
| [docs/SIGNALS.md](docs/SIGNALS.md) | Indikator- und Regelkatalog je Zeithorizont, Scoring, Derivate-Mathematik |
| [docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md) | Offene Punkte, die vor bzw. während der Implementierung zu entscheiden sind |

## Abgrenzung

* Keine Verbindung zu Trade Republic oder einem anderen Broker.
* Keine Orderausführung, kein Kontozugriff, kein Portfoliotracking (v1).
* **Keine Anlageberatung.** Das Tool zeigt Kennzahlen und regelbasierte Signale
  an. Es spricht keine Empfehlung im Sinne von § 2 Abs. 8 Nr. 10 WpHG aus und
  berücksichtigt keine persönlichen Verhältnisse. Jede Handelsentscheidung
  trifft ausschließlich der Nutzer. Historische Signale sagen nichts über
  künftige Kursentwicklungen aus.
