"""Tagesbriefing (höchstens 500 Wörter, Deutsch) aus den Daten des Morgenlaufs.

Rein regelbasiert: keine KI, keine API, keine Kosten. Keine Anlageberatung.
"""
import json, re, datetime as dt

MAXW = 500

def de(x, d=1, sign=True):
    if x is None:
        return "–"
    s = f"{x:+.{d}f}" if sign else f"{x:.{d}f}"
    return s.replace(".", ",")

def dd(txt):
    return re.sub(r"(\d)\.(\d)", r"\1,\2", txt)

def datum(iso):
    return f"{iso[8:10]}.{iso[5:7]}.{iso[:4]}"

def pc(x, d=1):
    return de(x, d) + " %"

def words(sections):
    return sum(len(re.findall(r"\S+", t["title"] + " " + " ".join(t["lines"]))) for t in sections)

def items_of(briefing):
    return [i for g in briefing["groups"] for i in g["items"]]

def is_single(i):
    return not (i["symbol"].startswith("^") or i["symbol"].endswith("=F") or i["symbol"].endswith(".SS") or "ETF" in i["name"])

def context(briefing, geo=None, btc=None, gas=None, vix=None, termine=None, date=None):
    its = items_of(briefing)
    by = {i["symbol"]: i for i in its}
    keep = lambda i: {k: i.get(k) for k in ("name", "d1", "d5", "m1", "rsi", "from_high", "trend", "rs_state", "forecast") if i.get(k) is not None}
    mv = sorted([i for i in its if is_single(i)], key=lambda i: -abs(i["d1"] or 0))[:6]
    return {
        "datum": date or briefing["generated"][:10],
        "stand_daten": briefing["generated"],
        "indizes": [keep(i) for i in briefing["groups"][0]["items"]],
        "branchen_etf": [keep(by[r["symbol"]]) | {"rel_staerke_20t": r["rs20"], "status": r["state"]} for r in briefing.get("rotation", []) if r["symbol"] in by],
        "rohstoffe": [keep(i) for g in briefing["groups"] if g["name"] == "Rohstoffe" for i in g["items"] if i["symbol"].endswith("=F")],
        "einzelwerte_groesste_bewegungen": [keep(i) | {"signale": i.get("signals", [])[:2], "schlagzeilen": [n["t"] for n in i.get("news", [])[:2]]} for i in mv],
        "geopolitik_medienstimmung": [{k: p.get(k) for k in ("pair", "state", "tone_now", "tone_base", "tension_ratio")} for p in (geo or {}).get("pairs", [])],
        "bitcoin": {k: btc.get(k) for k in ("price", "d1", "d7", "d30", "rsi", "state", "why")} if btc else None,
        "erdgas_ttf": {k: gas.get(k) for k in ("price", "d1", "d7", "d30", "state", "why")} if gas else None,
        "vix": vix, "termine": (termine or {}).get("events", []), "termine_hinweis": (termine or {}).get("hinweis"),
    }

def rule_text(briefing, geo=None, btc=None, gas=None, vix=None, termine=None, date=None):
    its = items_of(briefing)
    by = {i["symbol"]: i for i in its}
    S = []

    def nm(sym, label=None):
        i = by.get(sym)
        return f"{label or i['name']} {pc(i['d1'])}" if i and i.get("d1") is not None else None
    join = lambda xs: ", ".join(x for x in xs if x)

    # Marktüberblick
    idx = briefing["groups"][0]["items"]
    up = sum(1 for i in idx if (i["d1"] or 0) > 0)
    avg = sum((i["d1"] or 0) for i in idx) / max(len(idx), 1)
    L = [f"Stand {datum(date or briefing['generated'][:10])}: {up} von {len(idx)} Weltindizes im Plus (Ø {pc(avg)})."]
    for lab, syms in (("USA", ["^DJI", "^GSPC", "^NDX"]), ("Europa", ["^GDAXI", "^STOXX50E", "^FTSE"]), ("Asien/Pazifik", ["^N225", "^HSI", "000001.SS", "^KS11", "^AXJO"])):
        t = join(nm(s) for s in syms)
        if t:
            L.append(f"{lab}: {t}.")
    hi = [i["name"] for i in idx if (i.get("from_high") or -99) >= -0.5]
    if hi:
        L.append("Auf oder nahe dem 52-Wochen-Hoch: " + ", ".join(hi) + ".")
    S.append({"title": "Marktüberblick", "lines": L})

    # Branchen
    rot = [r for r in briefing.get("rotation", []) if r.get("d1") is not None]
    L = []
    if rot:
        srt = sorted(rot, key=lambda r: -r["d1"])
        L.append("Stärkste Branchen heute: " + join(f"{r['name']} {pc(r['d1'])}" for r in srt[:2]) + ". Schwächste: " + join(f"{r['name']} {pc(r['d1'])}" for r in srt[-2:][::-1]) + ".")
        fi = [r["name"] for r in rot if r["state"] == "frueh_rein"]
        fo = [r["name"] for r in rot if r["state"] == "frueh_raus"]
        if fi:
            L.append("Frühsignal (relative Stärke dreht nach oben, Kurs noch nicht bestätigt): " + ", ".join(fi) + ".")
        if fo:
            L.append("Frühwarnung (relative Stärke lässt nach): " + ", ".join(fo) + ".")
    rs = join(nm(s, l) for s, l in (("GC=F", "Gold"), ("CL=F", "Öl (WTI)"), ("HG=F", "Kupfer"), ("NG=F", "US-Erdgas")))
    if rs:
        L.append("Rohstoffe als mögliche Treiber: " + rs + ".")
    S.append({"title": "Branchen", "lines": L or ["Keine Branchendaten."]})

    # Einzelwerte
    mv = sorted([i for i in its if is_single(i) and i.get("d1") is not None], key=lambda i: -abs(i["d1"]))[:3]
    L = []
    for i in mv:
        if abs(i["d1"]) < 1.5:
            continue
        t = f"{i['name']} {pc(i['d1'])}"
        if i.get("signals"):
            t += f" ({dd(i['signals'][0])})"
        if i.get("news"):
            n = i["news"][0]
            t += f". Schlagzeile: „{n['t']}“" + (f" ({n['p']})" if n.get("p") else "")
        L.append(t + ".")
    S.append({"title": "Auffällige Einzelwerte", "lines": L or ["Keine größeren Ausschläge (ab 1,5 %) bei den beobachteten Einzelwerten."]})

    # Wirtschaft & Geopolitik
    L = []
    for p in (geo or {}).get("pairs", []):
        L.append(f"{p['pair']}: Medienstimmung „{p['state']}“ (Ton {de(p['tone_now'], 1, False)} gegenüber {de(p['tone_base'], 1, False)} im 30-Tage-Schnitt).")
    if not geo or not geo.get("pairs"):
        L.append("Geopolitik: keine Daten.")
    if gas:
        L.append(f"Erdgas Europa (TTF): {de(gas['price'], 1, False)} €/MWh, {pc(gas['d1'])} heute, Lage „{gas['state']}“.")
    if btc:
        L.append(f"Bitcoin: {int(btc['price']):,} $".replace(",", ".") + f", {pc(btc['d1'])} heute, Lage „{btc['state']}“.")
    L.append("Konjunkturdaten sind nicht hinterlegt; keine Aussage dazu.")
    S.append({"title": "Wirtschaft und Geopolitik", "lines": L})

    # Stimmung
    tr = [i for i in its if i.get("trend")]
    share = 100 * sum(1 for i in tr if i["trend"] == "auf") / max(len(tr), 1)
    ob = [i for i in its if (i.get("rsi") or 0) >= 70]
    os_ = [i for i in its if (i.get("rsi") or 100) <= 30]
    L = []
    if vix:
        L.append(f"VIX {de(vix['level'], 1, False)} ({pc(vix['d1'])}): {vix['label']}; im Jahresvergleich Perzentil {vix['pctile']:.0f}.")
    else:
        L.append("VIX: keine Daten.")
    L.append(f"{share:.0f} % der beobachteten Werte liegen über SMA50 und SMA200 (intakter Trend); {len(ob)} überkauft (RSI ≥ 70), {len(os_)} überverkauft (RSI ≤ 30).")
    score = (1 if avg > 0.3 else -1 if avg < -0.3 else 0) + (1 if share >= 60 else -1 if share <= 40 else 0) + (-1 if vix and vix["level"] >= 22 else 1 if vix and vix["level"] <= 15 else 0)
    L.append("Gesamtbild: " + ("eher optimistisch" if score >= 2 else "eher vorsichtig" if score <= -2 else "gemischt/neutral") + ".")
    S.append({"title": "Stimmung", "lines": L})

    # Ausblick
    ev = (termine or {}).get("events", [])
    L = []
    if ev:
        for e in ev[:5]:
            L.append(f"{e['date'][8:10]}.{e['date'][5:7]}.: {e['what']}")
    else:
        L.append("Keine Termine in den nächsten 21 Tagen hinterlegt.")
    L.append("Beobachten: Hält die relative Stärke der führenden Branchen? Bleiben überkaufte Werte oben, oder kommt ein Rücksetzer?")
    S.append({"title": "Ausblick", "lines": L})

    # Anlegerperspektive
    L = []
    if len(ob) >= 5:
        L.append(f"Mehrere überkaufte Werte ({len(ob)}): Rücksetzer-Risiko beachten.")
    if any(p["state"] in ("eskalierend", "Anspannung steigt") for p in (geo or {}).get("pairs", [])):
        L.append("Geopolitische Anspannung kann Rohstoffe, Rüstung und Schwankung treiben.")
    L.append("Beobachtungen aus Kursdaten, keine Anlageberatung und keine Prognose.")
    S.append({"title": "Anlegerperspektive", "lines": L})

    # Wortgrenze: zuerst die längsten Abschnitte kürzen (nie die erste Zeile)
    while words(S) > MAXW:
        big = max((s for s in S if len(s["lines"]) > 1), key=lambda s: len(" ".join(s["lines"])), default=None)
        if not big:
            break
        big["lines"].pop(-2 if big["title"] in ("Ausblick", "Anlegerperspektive") else -1)
    return S

def build(briefing, geo=None, btc=None, gas=None, vix=None, termine=None, date=None):
    ctx = context(briefing, geo, btc, gas, vix, termine, date)
    mode = "regelbasiert"
    secs = rule_text(briefing, geo, btc, gas, vix, termine, date)
    return {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "mode": mode,
            "date": ctx["datum"], "words": words(secs), "sections": secs,
            "hinweis": "Automatisch erstellt aus Kursdaten und Schlagzeilen. Keine Anlageberatung."}
