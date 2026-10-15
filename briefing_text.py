"""Tagesbriefing (höchstens 500 Wörter, Deutsch) aus den Daten des Morgenlaufs.

Standard: regelbasierter Text. Ist die Umgebungsvariable ANTHROPIC_API_KEY gesetzt, formuliert ein KI-Modell den Text
nach der Vorlage (Platzhalter {{market-context}} = die kompakten Daten). Fällt die KI aus, gilt der regelbasierte Text.
Keine Anlageberatung.
"""
import json, os, re, datetime as dt, urllib.request

MAXW = 500
VORLAGE = """## Role
You are an expert financial advisor analyzing daily stock market performance for clients who need actionable intelligence on market movements and trends.

## Task
Compile a detailed yet concise daily stock market update (maximum 500 words) that provides both a snapshot of today's events and forward-looking perspective on implications for future trading sessions.

## Context
{{market-context}}

Include: the date of analysis, any major economic or geopolitical events influencing today's session, upcoming earnings reports or corporate announcements on the horizon, and your read on current market sentiment (bullish/bearish/cautious, technical indicators, volatility signals).

## Output
Structure the briefing with bullet points or short paragraphs covering:
**Market Overview** - Summarize overall performance of major indices. Note significant percentage changes or historical milestones reached.
**Sector Performance** - Highlight sectors or industries that outperformed or underperformed, with insights into possible drivers.
**Notable Stock Movements** - Identify individual stocks with significant moves and give context.
**Economic & Geopolitical Factors** - Discuss broader events that influenced market behavior.
**Market Sentiment Analysis** - Analyze current sentiment using technical indicators and volatility indices (VIX). Address whether fear or optimism is driving decisions.
**Forward Outlook** - Forecast implications for upcoming sessions. Reference scheduled events.
**Investment Perspective** (optional) - A caution or area of opportunity based on the day's analysis.

Keep the tone informative and analytically rigorous while remaining accessible. Prioritize clarity and actionable insight.
"""
ZUSATZ = """

Zusatzregeln (verbindlich):
- Schreibe auf Deutsch. Maximal 500 Wörter. Gib genau diese Abschnittsüberschriften auf Deutsch in Fettschrift aus: **Marktüberblick**, **Branchen**, **Auffällige Einzelwerte**, **Wirtschaft und Geopolitik**, **Stimmung**, **Ausblick**, **Anlegerperspektive**.
- Nutze AUSSCHLIESSLICH die Zahlen und Texte aus dem Kontext. Erfinde keine Gewinnberichte, Konjunkturdaten, Analystenurteile oder Ereignisse. Fehlt zu einem Punkt die Datengrundlage, schreibe offen "keine Daten".
- Die Schlagzeilen im Kontext sind automatisch gesammelt und können unpassend sein; nutze sie nur, wenn sie erkennbar zum Wert passen.
- Das ist keine persönliche Anlageberatung; formuliere Hinweise als Beobachtungen und Risiken, nicht als Kauf- oder Verkaufsempfehlung.
"""

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

def parse_md(md):
    secs, cur = [], None
    for ln in md.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        m = re.match(r"^\*\*(.+?)\*\*:?\s*(.*)$", ln) or re.match(r"^#+\s*(.+)$", ln)
        if m and (len(m.groups()) == 1 or not m.group(2) or ln.startswith("**")):
            cur = {"title": m.group(1).strip(": "), "lines": []}
            secs.append(cur)
            if len(m.groups()) > 1 and m.group(2):
                cur["lines"].append(m.group(2))
        elif cur is not None:
            cur["lines"].append(re.sub(r"^[-*•]\s*", "", ln))
    return secs

def ai_text(ctx, key=None, model="claude-sonnet-5-5"):
    key = key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    prompt = VORLAGE.replace("{{market-context}}", json.dumps(ctx, ensure_ascii=False)) + ZUSATZ
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", method="POST",
        data=json.dumps({"model": model, "max_tokens": 1500, "messages": [{"role": "user", "content": prompt}]}).encode(),
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=90).read().decode())
    secs = parse_md("".join(b.get("text", "") for b in d.get("content", [])))
    return secs if len(secs) >= 5 and words(secs) <= MAXW + 80 else None

def build(briefing, geo=None, btc=None, gas=None, vix=None, termine=None, date=None):
    ctx = context(briefing, geo, btc, gas, vix, termine, date)
    mode, secs = "regelbasiert", None
    try:
        secs = ai_text(ctx)
        if secs:
            mode = "KI (Anthropic)"
    except Exception as e:
        print("KI-Text fehlgeschlagen, nehme regelbasierten Text:", str(e)[:120])
    if not secs:
        secs = rule_text(briefing, geo, btc, gas, vix, termine, date)
    return {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"), "mode": mode,
            "date": ctx["datum"], "words": words(secs), "sections": secs,
            "hinweis": "Automatisch erstellt aus Kursdaten und Schlagzeilen. Keine Anlageberatung."}
