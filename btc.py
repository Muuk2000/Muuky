"""Bitcoin-Indikator: Trend, Überhitzung, Risiko, Stimmung. Regelbasiert, keine Anlageberatung."""
import json, math, urllib.request
import numpy as np
import pandas as pd

def fear_greed(fetch=None):
    try:
        url = "https://api.alternative.me/fng/?limit=30"
        req = urllib.request.Request(url, headers={"User-Agent": "markt-briefing/1.0"})
        d = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())["data"]
        return {"value": int(d[0]["value"]), "label": d[0]["value_classification"],
                "avg30": round(sum(int(x["value"]) for x in d) / len(d), 1)}
    except Exception as e:
        print("Fear&Greed-Fehler", e)
        return None

def rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))

def analyse(close, ref=None, fng=None):
    """close: BTC-Tagesschlusskurse (>= 210 Tage); ref: Nasdaq-Schlusskurse für die Korrelation."""
    close = close.dropna()
    if len(close) < 210:
        return None
    last = float(close.iloc[-1])
    sma50, sma200 = close.rolling(50).mean().iloc[-1], close.rolling(200).mean().iloc[-1]
    pc = lambda n: (last / float(close.iloc[-1 - n]) - 1) * 100
    hi = float(close.tail(365).max())
    ret = close.pct_change().dropna()
    vol30 = float(ret.tail(30).std() * math.sqrt(365) * 100)
    vol_long = float(ret.tail(365).std() * math.sqrt(365) * 100)
    r = float(rsi(close).iloc[-1])
    mayer = last / float(sma200)
    out = {"price": round(last, 0), "d1": round(pc(1), 2), "d7": round(pc(7), 2), "d30": round(pc(30), 2),
           "rsi": round(r, 1), "vs_sma50": round((last / sma50 - 1) * 100, 1),
           "vs_sma200": round((last / sma200 - 1) * 100, 1), "mayer": round(mayer, 2),
           "from_high": round((last / hi - 1) * 100, 1), "vol30": round(vol30, 0), "vol_long": round(vol_long, 0),
           "spark": [round(float(x), 0) for x in close.tail(60)]}
    if ref is not None:
        j = pd.concat([close.pct_change(), ref.pct_change()], axis=1, join="inner").dropna().tail(30)
        if len(j) > 15:
            out["corr_nasdaq"] = round(float(j.iloc[:, 0].corr(j.iloc[:, 1])), 2)
    if fng:
        out["fear_greed"] = fng
    # Punktesystem -4 .. +4 (Trend zählt doppelt) -> Lagebild
    pts, why = 0, []
    if last > sma50 > sma200:
        pts += 2; why.append("Kurs über SMA50 und SMA200 (intakter Aufwärtstrend)")
    elif last < sma50 < sma200:
        pts -= 2; why.append("Kurs unter SMA50 und SMA200 (Abwärtstrend)")
    elif last > sma200:
        pts += 1; why.append("Kurs über SMA200, aber unter SMA50 (Trend wackelt)")
    else:
        pts -= 1; why.append("Kurs unter SMA200, aber über SMA50 (Erholung im Abwärtstrend)")
    if pc(30) > 10:
        pts += 1; why.append(f"Monatsmomentum {pc(30):+.0f} %")
    elif pc(30) < -10:
        pts -= 1; why.append(f"Monatsmomentum {pc(30):+.0f} %")
    if r >= 75 or mayer > 2.4:
        pts -= 1; why.append(f"Überhitzung (RSI {r:.0f}, Mayer-Multiple {mayer:.2f})")
    elif r <= 30 or mayer < 0.8:
        pts += 1; why.append(f"Überverkauft (RSI {r:.0f}, Mayer-Multiple {mayer:.2f})")
    if fng:
        if fng["value"] >= 80:
            pts -= 1; why.append(f"Extreme Gier im Markt (Fear & Greed {fng['value']})")
        elif fng["value"] <= 20:
            pts += 1; why.append(f"Extreme Angst im Markt (Fear & Greed {fng['value']}) - historisch oft Gegenindikator")
    if vol30 > vol_long * 1.5:
        why.append(f"Volatilität erhöht ({vol30:.0f} % p. a. gegenüber {vol_long:.0f} % im Jahresschnitt)")
    out["points"] = pts
    out["state"] = ("klar bullisch" if pts >= 3 else "eher bullisch" if pts >= 1 else
                    "neutral" if pts == 0 else "eher bärisch" if pts > -3 else "klar bärisch")
    out["why"] = why
    return out
