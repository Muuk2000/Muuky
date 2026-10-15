# Markt-Briefing

Tägliches Briefing und kurzfristige Marktsignale als mobile Webseite (PWA).
Welt-Indizes, Finanzen, Industrie, Rohstoffe, AI, Geopolitik, Bitcoin, Erdgas EU, Trefferquote.

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

Alles, was Kosten verursachen könnte (KI-Text, bezahlte Datenquellen, Aktualisierung per Aufruf), wird nur nach ausdrücklicher Freigabe des Besitzers eingebaut.
