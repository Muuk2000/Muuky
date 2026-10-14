"""Erdgas-Europa-Indikator: TTF-Preis (Front-Month), Trend, Preisniveau, Abstand zu US-Gas, optional Speicherstand.

Speicherstand: nur wenn ein kostenloser API-Key der GIE (agsi.gie.eu) als Umgebungsvariable GIE_API_KEY vorliegt.
Regelbasiert, keine Anlageberatung.
"""
import json, math, os, datetime as dt, urllib.request
import numpy as np
import pandas as pd

MMBTU_TO_MWH = 0.293071

def rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))

def storage(key=None, today=None):
    """EU-Gasspeicher: Füllstand heute, 7-Tage-Veränderung, Abstand zum Vorjahr (Prozentpunkte)."""
    key = key or os.environ.get("GIE_API_KEY")
    if not key:
        return None
    try:
        today = today or dt.date.today()
        url = f"https://agsi.gie.eu/api?type=eu&from={today - dt.timedelta(days=400)}&to={today}&size=500"
        req = urllib.request.Request(url, headers={"x-key": key, "User-Agent": "markt-briefing/1.0"})
        rows = json.loads(urllib.request.urlopen(req, timeout=40).read().decode())["data"]
        s = pd.Series({pd.Timestamp(r["gasDayStart"]): float(r["full"]) for r in rows if r.get("full") not in (None, "", "-")}).sort_index()
        if len(s) < 30:
            return None
        last_day = s.index[-1]
        ly = s[s.index <= last_day - pd.Timedelta(days=365)]
        return {"full": round(float(s.iloc[-1]), 1), "d7": round(float(s.iloc[-1] - s.iloc[-8]), 1),
                "vs_last_year": round(float(s.iloc[-1] - ly.iloc[-1]), 1) if len(ly) else None,
                "date": str(last_day.date())}
    except Exception as e:
        print("Gasspeicher-Fehler", e)
        return None

def analyse(ttf, henry=None, eurusd=None, stor=None):
    """ttf: TTF-Schlusskurse in EUR/MWh; henry: NG=F in USD/MMBtu; eurusd: EUR/USD."""
    ttf = ttf.dropna()
    if len(ttf) < 210:
        return None
    last = float(ttf.iloc[-1])
    pc = lambda n: (last / float(ttf.iloc[-1 - n]) - 1) * 100
    sma50, sma200 = float(ttf.rolling(50).mean().iloc[-1]), float(ttf.rolling(200).mean().iloc[-1])
    yr = ttf.tail(252)
    pctile = float((yr < last).mean() * 100)
    ret = ttf.pct_change().dropna()
    out = {"price": round(last, 2), "d1": round(pc(1), 2), "d7": round(pc(7), 2), "d30": round(pc(30), 2),
           "vs_sma50": round((last / sma50 - 1) * 100, 1), "vs_sma200": round((last / sma200 - 1) * 100, 1),
           "rsi": round(float(rsi(ttf).iloc[-1]), 1), "range_pctile": round(pctile, 0),
           "low_1y": round(float(yr.min()), 1), "high_1y": round(float(yr.max()), 1),
           "vol30": round(float(ret.tail(30).std() * math.sqrt(252) * 100), 0),
           "spark": [round(float(x), 2) for x in ttf.tail(60)]}
    if henry is not None and eurusd is not None:
        h, e = float(henry.dropna().iloc[-1]), float(eurusd.dropna().iloc[-1])
        hh_eur_mwh = h / MMBTU_TO_MWH / e
        out["henry_hub_eur_mwh"] = round(hh_eur_mwh, 1)
        out["premium_x"] = round(last / hh_eur_mwh, 1)
    if stor:
        out["storage"] = stor
    pts, why = 0, []
    if last > sma50 > sma200:
        pts += 1; why.append("TTF über SMA50 und SMA200 (Aufwärtstrend)")
    elif last < sma50 < sma200:
        pts -= 1; why.append("TTF unter SMA50 und SMA200 (Abwärtstrend)")
    if pc(30) > 15:
        pts += 1; why.append(f"Monatsmomentum {pc(30):+.0f} %")
    elif pc(30) < -15:
        pts -= 1; why.append(f"Monatsmomentum {pc(30):+.0f} %")
    if stor and stor.get("vs_last_year") is not None:
        v = stor["vs_last_year"]
        if v <= -5:
            pts += 1; why.append(f"Speicher {abs(v):.0f} Prozentpunkte unter Vorjahr ({stor['full']} % gefüllt) - knappere Lage")
        elif v >= 5:
            pts -= 1; why.append(f"Speicher {v:.0f} Prozentpunkte über Vorjahr ({stor['full']} % gefüllt) - entspanntere Lage")
    if pctile >= 85:
        why.append(f"Preis im oberen Bereich der 1-Jahres-Spanne (Perzentil {pctile:.0f})")
    elif pctile <= 15:
        why.append(f"Preis im unteren Bereich der 1-Jahres-Spanne (Perzentil {pctile:.0f})")
    if out["vol30"] > 80:
        why.append(f"Hohe Schwankung ({out['vol30']:.0f} % p. a.) - nervöser Markt")
    out["points"] = pts
    out["state"] = "Preisdruck steigt" if pts >= 2 else "eher steigend" if pts == 1 else \
                   "neutral" if pts == 0 else "eher fallend" if pts == -1 else "Preisdruck lässt nach"
    out["why"] = why
    return out
