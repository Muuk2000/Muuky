"""Geopolitik-Lageindikator USA / China / Russland aus GDELT (Nachrichten-Stimmung).

Misst NICHT die Lage selbst, sondern wie englischsprachige Medien über ein Länderpaar berichten:
 - Ton (Average Tone, ca. -10 negativ bis +10 positiv) der Artikel, die beide Länder nennen
 - Spannungs-Anteil: Anteil der Berichterstattung mit Konfliktbegriffen (Sanktionen, Militär, Krieg ...)
Vergleich: letzte 3 Tage gegen die 27 Tage davor. Automatische Textanalyse, viel Rauschen.
"""
import json, math, time, urllib.parse, urllib.request
from statistics import mean, pstdev

API = "https://api.gdeltproject.org/api/v2/doc/doc"
CONFLICT = '(sanctions OR tariffs OR military OR missile OR war OR embargo OR "export controls" OR troops)'
PAIRS = {
    "USA – China": '"United States" China',
    "USA – Russland": '"United States" Russia',
    "China – Russland": "China Russia",
}

def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "markt-briefing/1.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def timeline(query, mode, fetch=fetch_json, pause=6.0):
    q = urllib.parse.urlencode({"query": query + " sourcelang:english", "mode": mode,
                                "timespan": "30d", "format": "json"})
    for attempt in range(3):
        try:
            d = fetch(f"{API}?{q}")
            break
        except Exception:
            if attempt == 2:
                raise
            time.sleep(pause * 2)
    time.sleep(pause)                       # GDELT erlaubt ca. 1 Anfrage je 5 s
    days = {}
    for s in d.get("timeline", []):
        for p in s.get("data", []):
            days.setdefault(str(p["date"])[:8], []).append(float(p["value"]))
    return [(k, mean(v)) for k, v in sorted(days.items())]

def label(tone_z, vol_ratio):
    if tone_z <= -1 and vol_ratio >= 1.3:
        return "eskalierend"
    if tone_z <= -1 or vol_ratio >= 1.5:
        return "Anspannung steigt"
    if tone_z >= 1 and vol_ratio <= 1.0:
        return "Entspannung"
    return "unverändert"

def pair_metrics(tone, vol):
    if len(tone) < 15 or len(vol) < 15:
        return None
    t = [v for _, v in tone]
    now, base = mean(t[-3:]), mean(t[:-3])
    sd = pstdev(t[:-3]) or 1.0
    z = (now - base) / sd
    v = [x for _, x in vol]
    vbase = mean(v[:-3]) or 1e-9
    vr = mean(v[-3:]) / vbase
    return {"tone_now": round(now, 2), "tone_base": round(base, 2), "tone_z": round(z, 2),
            "tension_ratio": round(vr, 2), "state": label(z, vr),
            "spark": [round(x, 2) for x in t[-30:]]}

def build(fetch=fetch_json, pause=6.0):
    out = []
    for name, q in PAIRS.items():
        try:
            m = pair_metrics(timeline(q, "timelinetone", fetch, pause),
                             timeline(f"{q} {CONFLICT}", "timelinevol", fetch, pause))
        except Exception as e:
            print("GDELT-Fehler", name, e)
            m = None
        if m:
            m["pair"] = name
            out.append(m)
    return out
