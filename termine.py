"""Terminkalender: Notenbank-Sitzungen (fest hinterlegt, geprüft) und Quartalszahlen der beobachteten Einzelwerte (Yahoo, Best Effort)."""
import datetime as dt

# Entscheidungstage. Quellen: federalreserve.gov (FOMC-Kalender 2026), ecb.europa.eu (Ratssitzungen 2026). Stand: Oktober 2026.
FED = ["2026-10-28", "2026-12-09"]
EZB = ["2026-10-29", "2026-12-17"]

def earnings(symbols, today=None, days=21):
    out, err = [], []
    try:
        import yfinance as yf
    except Exception as e:
        return out, [str(e)]
    today = today or dt.date.today()
    for sym, name in symbols.items():
        try:
            cal = yf.Ticker(sym).calendar or {}
            for d in cal.get("Earnings Date", []) or []:
                d = d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d)[:10])
                if 0 <= (d - today).days <= days:
                    out.append({"date": d.isoformat(), "what": f"Quartalszahlen {name}", "kind": "earnings"})
                    break
        except Exception as e:
            if len(err) < 3:
                err.append(f"{sym}: {str(e)[:60]}")
    return out, err

def build(single_stocks, today=None, horizon=21):
    today = today or dt.date.today()
    ev = []
    for d in FED:
        ev.append({"date": d, "what": "US-Notenbank Fed: Zinsentscheid", "kind": "notenbank"})
    for d in EZB:
        ev.append({"date": d, "what": "EZB: Zinsentscheid", "kind": "notenbank"})
    e, err = earnings(single_stocks, today, horizon)
    ev += e
    ev = [x for x in ev if 0 <= (dt.date.fromisoformat(x["date"]) - today).days <= horizon]
    ev.sort(key=lambda x: x["date"])
    return {"events": ev, "errors": err, "hinweis": "Konjunkturdaten (z. B. Inflation, Arbeitsmarkt) sind nicht hinterlegt."}
