#!/usr/bin/env python3
"""Holt Kursdaten, berechnet Signale und schreibt data/briefing.json.

Aufruf:  python fetch_data.py          (echte Daten via Yahoo Finance)
         python fetch_data.py --demo   (synthetische Testdaten, ohne Netz)
Keine Anlageberatung - rein regelbasierte Auswertung von Kursdaten.
"""
import json, sys, math, datetime as dt
from pathlib import Path

OUT = Path(__file__).parent / "data" / "briefing.json"

UNIVERSE = {
    "Welt-Indizes": {
        "^GSPC": "S&P 500", "^NDX": "Nasdaq 100", "^GDAXI": "DAX",
        "^STOXX50E": "Euro Stoxx 50", "^FTSE": "FTSE 100", "^N225": "Nikkei 225",
        "^HSI": "Hang Seng", "000001.SS": "Shanghai Comp.", "^NSEI": "Nifty 50",
        "^BVSP": "Bovespa", "^AXJO": "ASX 200", "^KS11": "Kospi",
    },
    "Finanzen": {
        "XLF": "Financials (US, ETF)", "KBE": "Banken (US, ETF)", "KIE": "Versicherer (US, ETF)",
        "EUFN": "Finanzen Europa (ETF)", "JPM": "JPMorgan", "GS": "Goldman Sachs",
        "ALV.DE": "Allianz", "DBK.DE": "Deutsche Bank",
    },
    "Industrie": {
        "XLI": "Industrials (US, ETF)", "ITA": "Luft/Rüstung (ETF)", "IYT": "Transport (ETF)",
        "CAT": "Caterpillar", "GE": "GE Aerospace", "SIE.DE": "Siemens", "RHM.DE": "Rheinmetall",
    },
    "Rohstoffe": {
        "GC=F": "Gold", "SI=F": "Silber", "CL=F": "WTI Öl", "BZ=F": "Brent Öl",
        "NG=F": "Erdgas", "HG=F": "Kupfer", "XLE": "Energie (US, ETF)", "XLB": "Materialien (US, ETF)",
    },
    "AI": {
        "NVDA": "Nvidia", "MSFT": "Microsoft", "AMD": "AMD", "TSM": "TSMC",
        "PLTR": "Palantir", "SMH": "Halbleiter (ETF)", "AIQ": "AI & Big Data (ETF)", "BOTZ": "Robotik & AI (ETF)",
    },
}

def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = up / dn.replace(0, float("nan"))
    return 100 - 100 / (1 + rs)

def pct(a, b):
    return None if b in (0, None) or a is None else (a / b - 1) * 100

def analyse(sym, name, df):
    """df: DataFrame mit Close (und optional Volume), mind. ~60 Zeilen."""
    close = df["Close"].dropna()
    if len(close) < 30:
        return None
    last = float(close.iloc[-1])
    sma50 = close.rolling(50).mean()
    sma200 = close.rolling(200).mean()
    r = float(rsi(close).iloc[-1])
    hi52 = float(close.tail(252).max())
    item = {
        "symbol": sym, "name": name, "price": round(last, 2),
        "d1": pct(last, float(close.iloc[-2])),
        "d5": pct(last, float(close.iloc[-6])) if len(close) > 6 else None,
        "m1": pct(last, float(close.iloc[-22])) if len(close) > 22 else None,
        "rsi": round(r, 1),
        "vs_sma50": pct(last, float(sma50.iloc[-1])) if not math.isnan(sma50.iloc[-1]) else None,
        "vs_sma200": pct(last, float(sma200.iloc[-1])) if not math.isnan(sma200.iloc[-1]) else None,
        "from_high": pct(last, hi52),
        "spark": [round(float(x), 2) for x in close.tail(30)],
    }
    for k in ("d1", "d5", "m1", "vs_sma50", "vs_sma200", "from_high"):
        if item[k] is not None:
            item[k] = round(item[k], 2)

    sig = []  # (score, text)
    d1 = item["d1"] or 0
    if abs(d1) >= 2.5:
        sig.append((abs(d1), f"Starke Tagesbewegung {d1:+.1f} %"))
    if r >= 70:
        sig.append((r - 60, f"RSI {r:.0f}: überkauft - Rücksetzer-Risiko"))
    elif r <= 30:
        sig.append((70 - r, f"RSI {r:.0f}: überverkauft - mögliche Gegenbewegung"))
    if len(close) > 205:
        diff = (sma50 - sma200).dropna()
        if len(diff) > 6:
            now, then = diff.iloc[-1], diff.iloc[-6]
            if then <= 0 < now:
                sig.append((9, "Golden Cross (SMA50 über SMA200) in den letzten 5 Tagen"))
            elif then >= 0 > now:
                sig.append((9, "Death Cross (SMA50 unter SMA200) in den letzten 5 Tagen"))
    if item["from_high"] is not None and item["from_high"] >= -0.5:
        sig.append((8, "Nahe/auf 52-Wochen-Hoch - Ausbruch/Trendstärke"))
    if "Volume" in df:
        vol = df["Volume"].dropna()
        if len(vol) > 21 and vol.iloc[-21:-1].mean() > 0:
            ratio = float(vol.iloc[-1] / vol.iloc[-21:-1].mean())
            # Verhältnis > 30 ist fast immer ein Datenartefakt (z. B. Futures-Volumen) -> ignorieren
            if ratio <= 30:
                item["vol_ratio"] = round(ratio, 2)
            if 2 <= ratio <= 30 and abs(d1) >= 1.5:
                sig.append((7 + ratio, f"Volumen {ratio:.1f}x über Schnitt bei {d1:+.1f} % - Bewegung mit Überzeugung"))
    sig.sort(reverse=True)
    item["signals"] = [t for _, t in sig]
    item["score"] = round(sum(s for s, _ in sig), 1)
    if item["vs_sma50"] is not None and item["vs_sma200"] is not None:
        item["trend"] = "auf" if item["vs_sma50"] > 0 and item["vs_sma200"] > 0 else \
                        "ab" if item["vs_sma50"] < 0 and item["vs_sma200"] < 0 else "seitwärts"
    return item

def group_comment(name, items):
    ds = [i["d1"] for i in items if i["d1"] is not None]
    ms = [i["m1"] for i in items if i["m1"] is not None]
    if not ds:
        return "Keine Daten."
    avg, mavg = sum(ds) / len(ds), (sum(ms) / len(ms) if ms else 0)
    best = max(items, key=lambda i: i["d1"] or -99)
    worst = min(items, key=lambda i: i["d1"] or 99)
    breadth = sum(1 for d in ds if d > 0)
    tone = "freundlich" if avg > 0.4 else "schwach" if avg < -0.4 else "unentschlossen"
    txt = (f"{name}: Tagesstimmung {tone} (Ø {avg:+.1f} %, {breadth} von {len(ds)} im Plus). "
           f"Stärkster: {best['name']} ({best['d1']:+.1f} %), schwächster: {worst['name']} ({worst['d1']:+.1f} %). "
           f"Auf Monatssicht Ø {mavg:+.1f} %.")
    if avg > 0 and mavg < 0:
        txt += " Tagesplus gegen den Monatstrend - Erholung oder Fehlsignal."
    if avg < 0 and mavg > 0:
        txt += " Tagesminus im intakten Monatstrend - womöglich Gewinnmitnahmen."
    return txt

def load_real():
    import yfinance as yf
    syms = [s for g in UNIVERSE.values() for s in g]
    raw = yf.download(syms, period="1y", interval="1d", group_by="ticker",
                      auto_adjust=True, progress=False, threads=True)
    return {s: raw[s].dropna(how="all") for s in syms if s in raw.columns.get_level_values(0)}

def load_demo():
    import numpy as np, pandas as pd
    rng = np.random.default_rng(42)
    idx = pd.bdate_range(end=dt.date.today(), periods=260)
    out = {}
    for g in UNIVERSE.values():
        for s in g:
            steps = rng.normal(0.0004, 0.014, len(idx))
            out[s] = pd.DataFrame({"Close": 100 * np.exp(np.cumsum(steps)),
                                   "Volume": rng.integers(1_000_000, 3_000_000, len(idx))}, index=idx)
    return out

def main():
    demo = "--demo" in sys.argv
    data = load_demo() if demo else load_real()
    groups, all_items = [], []
    for gname, members in UNIVERSE.items():
        items = []
        for sym, name in members.items():
            if sym in data:
                try:
                    it = analyse(sym, name, data[sym])
                    if it:
                        it["group"] = gname
                        items.append(it)
                except Exception as e:
                    print("Fehler bei", sym, e, file=sys.stderr)
        groups.append({"name": gname, "comment": group_comment(gname, items) if items else "Keine Daten.", "items": items})
        all_items += items
    if not all_items:
        sys.exit("Keine Daten geladen - breche ab, alte briefing.json bleibt erhalten.")
    top = sorted([i for i in all_items if i["signals"]], key=lambda i: -i["score"])[:10]
    out = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "demo": demo,
        "top_signals": [{"symbol": i["symbol"], "name": i["name"], "group": i["group"],
                         "d1": i["d1"], "signals": i["signals"]} for i in top],
        "groups": groups,
        "disclaimer": "Regelbasierte Auswertung von Kursdaten. Keine Anlageberatung.",
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"{len(all_items)} Instrumente, {len(top)} Top-Signale -> {OUT}")

if __name__ == "__main__":
    main()
