# Markt-Briefing

Tägliches Briefing und kurzfristige Marktsignale als mobile Webseite (PWA).
Welt-Indizes, Zinsen & Währungen, Finanzen, Industrie, Rüstung, Energie & Versorger, Gesundheit & Pharma, Edelmetalle, Industriemetalle, Halbleiter, AI, Geopolitik, Bitcoin, Erdgas EU, Trefferquote.

## Zeitplan

GitHub startet geplante Läufe oft Stunden zu spät (Okt. 2026: ca. 5 Stunden). Deshalb:
- Pünktlicher Start um 06:45 Uhr über einen externen Wecker (cron-job.org), der `workflow_dispatch` aufruft (Schlüssel nur mit Actions-Recht für dieses Repo).
- Sicherheitsnetz: vier geplante Versuche, Zeitfenster 06:30 bis 13:30 Uhr; es aktualisiert nur der erste Lauf des Tages.

Keine Anlageberatung.

## Kosten: keine

| Teil | Kosten |
|---|---|
| GitHub Pages und Actions in einem **öffentlichen** Repo | 0 € |
| Kursdaten (Yahoo via yfinance), Schlagzeilen (Google News RSS), Geopolitik (GDELT), Bitcoin/Fear&Greed | 0 €, ohne Konto und ohne Schlüssel |
| Briefing-Text | regelbasiert, keine KI, keine API |

Schutzmaßnahmen:
- Der Workflow läuft **nur in einem öffentlichen Repo** (Kosten-Wächter im ersten Schritt); sonst tut er nichts.
- Jeder Lauf hat ein Zeitlimit von 15 Minuten.
- Es sind **keine Schlüssel oder Secrets** hinterlegt, auch keine KI-Schnittstelle.
- Die Aktualisierung per Aufruf der Seite (`UPDATE_ENABLED` in `index.html`) ist **ausgeschaltet**.

## Wirtschaft und Lehrplan (Ordner `wirtschaft/`)

Zweite Seite im selben Repo: Wirtschaftsnachrichten (VWL/BWL), eingeordnet nach dem LehrplanPLUS Bayern,
Gymnasium, Fach Wirtschaft und Recht, vertieft und nicht vertieft. Adresse: `/wirtschaft/`.

| Datei | Inhalt |
|---|---|
| `wirtschaft/index.html` | Seite mit den Reitern Heute, Rückblick, Lehrplan, Zurückgestellt |
| `wirtschaft/data/lehrplan.json` | Lernbereiche mit Stichwörtern für die Zuordnung |
| `wirtschaft/data/rueckblick.json` | Rückblick der letzten drei Monate, von Hand mit Quellen und Lehrplanbezug |
| `wirtschaft_update.py` | Tagesmeldungen holen (Google News RSS) und per Stichwort dem Lehrplan zuordnen |
| `.github/workflows/wirtschaft.yml` | werktags um 6:45 Uhr, nur im öffentlichen Repo |

Kosten: keine (Standardbibliothek, kein Schlüssel, keine KI). Die Stichwort-Zuordnung ist eine grobe Vorsortierung.

Alles, was Kosten verursachen könnte (KI-Text, bezahlte Datenquellen, Aktualisierung per Aufruf), wird nur nach ausdrücklicher Freigabe des Besitzers eingebaut.
