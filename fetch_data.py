#!/usr/bin/env python3
"""Holt Kursdaten, berechnet Signale und schreibt data/briefing.json.

Aufruf:  python fetch_data.py          (echte Daten via Yahoo Finance)
         python fetch_data.py --demo   (synthetische Testdaten, ohne Netz)
Keine Anlageberatung - rein regelbasierte Auswertung von Kursdaten.
"""
import json, sys, math, datetime as dt
from pathlib import Path
import numpy as np
import pandas as pd

OUT = Path(__file__).parent / "data" / "briefing.json"
BENCH = "ACWI"  # Welt-Aktien-ETF als Vergleichsmaßstab für die relative Stärke
SECTORS = {"XLF", "KBE", "KIE", "EUFN", "XLI", "ITA", "IYT", "XLE", "XLB", "SMH", "AIQ", "BOTZ"}

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

def analyse(sym, name, df, bench=None):
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
    # --- Frühindikator: relative Stärke gegenüber dem Weltmarkt ---
    if bench is not None and not sym.endswith("=F") and sym != BENCH and len(close) > 40:
        b = bench.reindex(close.index, method="ffill")
        rs = (close / b).dropna()
        if len(rs) > 40:
            rs_sma = rs.rolling(20).mean()
            rs5 = pct(float(rs.iloc[-1]), float(rs.iloc[-6]))
            rs20 = pct(float(rs.iloc[-1]), float(rs.iloc[-21]))
            rs_up = float(rs.iloc[-1]) > float(rs_sma.iloc[-1])
            item["rs5"], item["rs20"] = round(rs5, 2), round(rs20, 2)
            v50 = item["vs_sma50"]
            state = "neutral"
            if rs5 > 0.5 and rs_up and (v50 is None or v50 < 0 or (item["m1"] or 0) < 0):
                state = "frueh_rein"
                sig.append((10, f"Frühsignal: relative Stärke dreht nach oben ({rs5:+.1f} % in 5 Tagen), Kurs noch nicht bestätigt"))
            elif rs5 < -0.5 and not rs_up and (v50 is not None and v50 > 0):
                state = "frueh_raus"
                sig.append((10, f"Frühwarnung: relative Stärke lässt nach ({rs5:+.1f} % in 5 Tagen), Kurs hält noch"))
            elif rs20 > 3 and rs_up:
                state = "fuehrend"
            elif rs20 < -3 and not rs_up:
                state = "schwach"
            item["rs_state"] = state
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
    syms = [s for g in UNIVERSE.values() for s in g] + [BENCH]
    raw = yf.download(syms, period="1y", interval="1d", group_by="ticker",
                      auto_adjust=True, progress=False, threads=True)
    return {s: raw[s].dropna(how="all") for s in syms if s in raw.columns.get_level_values(0)}

def load_demo():
    import numpy as np, pandas as pd
    rng = np.random.default_rng(42)
    idx = pd.bdate_range(end=dt.date.today(), periods=260)
    out = {}
    for s in [s for g in UNIVERSE.values() for s in g] + [BENCH]:
        if True:
            steps = rng.normal(0.0004, 0.014, len(idx))
            out[s] = pd.DataFrame({"Close": 100 * np.exp(np.cumsum(steps)),
                                   "Volume": rng.integers(1_000_000, 3_000_000, len(idx))}, index=idx)
    return out

# ---------------------------------------------------------------------------
# Prognose-Protokoll: Tagesrichtung aus Indikatoren, abends gegen den Schlusskurs geprüft
# ---------------------------------------------------------------------------
LOG = OUT.parent / "forecasts.json"
STATS = OUT.parent / "stats.json"
THRESH = 1.0          # ab diesem Punktestand (Betrag) wird eine Richtung prognostiziert
COMPS = {"trend": "Trend (Kurs über/unter SMA50)", "momentum": "Momentum (5 Tage)",
         "rsi": "RSI-Extreme (Gegenbewegung)", "rs": "Relative Stärke (Frühindikator)"}
GROUP_OF = {sym: g for g, m in UNIVERSE.items() for sym in m}

def norm_df(df):
    df = df.copy()
    idx = pd.to_datetime(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    df.index = idx.normalize()
    return df[~df.index.duplicated(keep="last")]

def features(close, bench, futures=False):
    """Indikator-Beiträge je Tag; jeder Wert nutzt nur Daten bis einschließlich dieses Tages."""
    sma50 = close.rolling(50).mean()
    trend = pd.Series(np.where(close > sma50, 1.0, -1.0), index=close.index).where(sma50.notna(), 0.0)
    momentum = (np.sign(close.pct_change(5)) * 0.5).fillna(0.0)
    r = rsi(close)
    rsi_c = pd.Series(np.where(r > 70, -1.0, np.where(r < 30, 1.0, 0.0)), index=close.index).where(r.notna(), 0.0)
    rs_c = pd.Series(0.0, index=close.index)
    if bench is not None and not futures:
        b = bench.reindex(close.index, method="ffill")
        rs = close / b
        rs_up = rs > rs.rolling(20).mean()
        rs5, rs20 = rs.pct_change(5) * 100, rs.pct_change(20) * 100
        weak = (close < sma50) | (close.pct_change(21) < 0)
        rs_c = pd.Series(np.select(
            [(rs5 > 0.5) & rs_up & weak, (rs5 < -0.5) & ~rs_up & (close > sma50),
             (rs20 > 3) & rs_up, (rs20 < -3) & ~rs_up],
            [1.0, -1.0, 0.5, -0.5], default=0.0), index=close.index)
    f = pd.DataFrame({"trend": trend, "momentum": momentum, "rsi": rsi_c, "rs": rs_c})
    f["score"] = f.sum(axis=1)
    return f

def hit_of(sign, chg):
    return None if chg == 0 else (sign * chg > 0)

def summarize(rows, base_rows=None):
    """rows: dicts mit pred(+1/-1), chg(%), group, comps. base_rows: alle Tage (für die Basisrate)."""
    res = [(r, hit_of(r["pred"], r["chg"])) for r in rows]
    res = [(r, h) for r, h in res if h is not None]
    n = len(res)
    if n == 0:
        return {"n": 0}
    hits = sum(1 for _, h in res if h)
    rate = hits / n
    allr = base_rows if base_rows is not None else rows
    ups = [r["chg"] for r in allr if r["chg"] != 0]
    base_up = (sum(1 for c in ups if c > 0) / len(ups)) if ups else 0.5
    const = max(base_up, 1 - base_up)
    out = {"n": n, "hits": hits, "rate": round(rate * 100, 1),
           "ci": round(1.96 * math.sqrt(rate * (1 - rate) / n) * 100, 1),
           "base_up": round(base_up * 100, 1), "edge": round((rate - const) * 100, 1)}
    by_group = {}
    for g in UNIVERSE:
        gr = [(r, h) for r, h in res if r["group"] == g]
        if gr:
            by_group[g] = {"n": len(gr), "rate": round(100 * sum(1 for _, h in gr if h) / len(gr), 1)}
    out["by_group"] = by_group
    by_dir = {}
    for key, lab in ((1, "steigt"), (-1, "fällt")):
        dr = [(r, h) for r, h in res if r["pred"] == key]
        if dr:
            by_dir[lab] = {"n": len(dr), "rate": round(100 * sum(1 for _, h in dr if h) / len(dr), 1)}
    out["by_direction"] = by_dir
    by_comp = {}
    for c, lab in COMPS.items():
        cr = [(r, hit_of(np.sign(r["comps"][c]), r["chg"])) for r in rows if r["comps"].get(c, 0) != 0]
        cr = [x for x in cr if x[1] is not None]
        if cr:
            by_comp[lab] = {"n": len(cr), "rate": round(100 * sum(1 for _, h in cr if h) / len(cr), 1)}
    out["by_component"] = by_comp
    return out

def backtest(data, bench, days=200):
    rows, base = [], []
    for sym, df in data.items():
        if sym == BENCH or sym not in GROUP_OF:
            continue
        close = df["Close"].dropna()
        if len(close) < 120:
            continue
        f = features(close, bench, futures=sym.endswith("=F"))
        nxt = (close.shift(-1) / close - 1) * 100
        valid = f.index[60:]
        valid = [t for t in valid if not math.isnan(nxt.loc[t])][-days:]
        for t in valid:
            chg = float(nxt.loc[t])
            base.append({"chg": chg})
            sc = float(f.loc[t, "score"])
            if abs(sc) >= THRESH:
                rows.append({"pred": 1 if sc > 0 else -1, "chg": chg, "group": GROUP_OF[sym],
                             "comps": {c: float(f.loc[t, c]) for c in COMPS}})
    out = summarize(rows, base)
    out["tage_x_werte"] = len(base)
    out["abdeckung"] = round(100 * len(rows) / max(len(base), 1), 1)
    return out

def load_log():
    try:
        return json.loads(LOG.read_text())
    except Exception:
        return []

def evaluate(log, data, now):
    """Offene Prognosen gegen den Schlusskurs des Prognosetags prüfen."""
    today = pd.Timestamp(now.date())
    done = 0
    for e in log:
        if e.get("res") is not None:
            continue
        d = pd.Timestamp(e["date"])
        if d > today or (d == today and now.hour < 21):   # Tag noch nicht abgeschlossen
            continue
        df = data.get(e["symbol"])
        if df is None:
            continue
        close = df["Close"].dropna()
        if d in close.index:
            chg = (float(close.loc[d]) / e["ref"] - 1) * 100
            e["res"] = {"chg": round(chg, 2), "close": round(float(close.loc[d]), 2)}
            done += 1
        elif (today - d).days > 6:
            e["res"] = {"chg": None}        # kein Handelstag / keine Daten
    return done

def live_rows(log):
    rows = []
    for e in log:
        r = e.get("res")
        if r and r.get("chg") is not None:
            rows.append({"pred": e["pred"], "chg": r["chg"], "group": e["group"], "comps": e["comps"],
                         "date": e["date"], "name": e.get("name", e["symbol"]), "symbol": e["symbol"]})
    return rows

def build_stats(log, data, bench, demo):
    rows = live_rows(log)
    recent = sorted(rows, key=lambda r: (r["date"], abs(r["chg"])), reverse=True)[:15]
    return {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes"),
        "demo": demo,
        "live": summarize(rows),
        "live_offen": sum(1 for e in log if e.get("res") is None),
        "backtest": backtest(data, bench),
        "recent": [{"date": r["date"], "name": r["name"], "symbol": r["symbol"], "pred": r["pred"],
                    "chg": r["chg"], "hit": hit_of(r["pred"], r["chg"])} for r in recent],
        "method": ("Prognose = Vorzeichen eines Punktesystems aus vier Indikatoren (" + "; ".join(COMPS.values()) +
                   f"), nur ab Betrag {THRESH}. Sie nutzt ausschließlich Daten bis zum Vortagesschluss und wird "
                   "morgens im Repo festgeschrieben. Bewertung: Schlusskurs des Tages gegen Vortagesschluss. "
                   "Rückschau = dieselben Regeln auf die letzten 200 Handelstage, ohne spätere Daten; die Regeln wurden "
                   "nicht an diesen Daten optimiert, sind aber vor der Rückschau festgelegt worden - Zufallstreffer sind möglich."),
    }

def extras(all_items, data):
    """Geopolitik (GDELT) und Bitcoin; jeder Teil darf ausfallen, ohne das Briefing zu stoppen."""
    gen = dt.datetime.now(dt.timezone.utc).isoformat(timespec="minutes")
    try:
        import geo
        pairs = geo.build()
        if pairs:
            want = {"GC=F": "Gold", "CL=F": "Öl (WTI)", "ITA": "Luft/Rüstung (ETF)", "RHM.DE": "Rheinmetall", "^GSPC": "S&P 500"}
            mk = [{"name": want[i["symbol"]], "d1": i["d1"], "m1": i["m1"]} for i in all_items if i["symbol"] in want]
            (OUT.parent / "geo.json").write_text(json.dumps({"generated": gen, "pairs": pairs, "markets": mk,
                "note": "Automatische Auswertung der Medien-Stimmung (GDELT), kein Lagebericht. Viel Rauschen."},
                ensure_ascii=False, indent=1))
            print("Geopolitik:", ", ".join(f"{p['pair']}={p['state']}" for p in pairs))
    except Exception as e:
        print("Geopolitik fehlgeschlagen:", e, file=sys.stderr)
    try:
        import yfinance as yf, btc
        raw = yf.download("BTC-USD", period="2y", interval="1d", auto_adjust=True, progress=False)
        raw = norm_df(raw.droplevel(1, axis=1) if hasattr(raw.columns, "levels") and raw.columns.nlevels > 1 else raw)
        ref = data["^NDX"]["Close"].dropna() if "^NDX" in data else None
        res = btc.analyse(raw["Close"], ref, btc.fear_greed())
        if res:
            res["generated"] = gen
            (OUT.parent / "btc.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
            print("Bitcoin:", res["state"], res["price"])
    except Exception as e:
        print("Bitcoin fehlgeschlagen:", e, file=sys.stderr)

def main():
    demo = "--demo" in sys.argv
    evening = "--evening" in sys.argv
    now = dt.datetime.now(dt.timezone.utc)
    today = pd.Timestamp(now.date())
    data = load_demo() if demo else load_real()
    data = {k: norm_df(v) for k, v in data.items()}
    bench = data[BENCH]["Close"].dropna() if BENCH in data else None
    log = load_log()
    if not demo:
        n = evaluate(log, data, now)
        print(f"{n} Prognosen ausgewertet")
    if evening:
        if demo:
            sys.exit("--evening nicht mit --demo")
        log = [e for e in log if (today - pd.Timestamp(e["date"])).days <= 400]
        LOG.write_text(json.dumps(log, ensure_ascii=False, separators=(",", ":")))
        STATS.write_text(json.dumps(build_stats(log, data, bench, demo), ensure_ascii=False, indent=1))
        print("Abendauswertung geschrieben")
        return

    groups, all_items = [], []
    for gname, members in UNIVERSE.items():
        items = []
        for sym, name in members.items():
            if sym in data:
                try:
                    it = analyse(sym, name, data[sym], bench)
                    if it:
                        it["group"] = gname
                        # Prognose nur aus Daten bis zum Vortagesschluss
                        cl = data[sym]["Close"].dropna()
                        cl = cl[cl.index < today]
                        if len(cl) > 80:
                            f = features(cl, bench[bench.index < today] if bench is not None else None,
                                         futures=sym.endswith("=F")).iloc[-1]
                            if abs(f["score"]) >= THRESH:
                                it["forecast"] = "up" if f["score"] > 0 else "down"
                                it["_fc"] = (float(f["score"]), {c: float(f[c]) for c in COMPS}, float(cl.iloc[-1]), name)
                        items.append(it)
                except Exception as e:
                    print("Fehler bei", sym, e, file=sys.stderr)
        groups.append({"name": gname, "comment": group_comment(gname, items) if items else "Keine Daten.", "items": items})
        all_items += items
    if not all_items:
        sys.exit("Keine Daten geladen - breche ab, alte briefing.json bleibt erhalten.")

    # Prognosen für heute festschreiben (nur morgens, nur Werktage, nur einmal je Tag)
    if not demo and now.hour < 13 and today.weekday() < 5:
        have = {(e["date"], e["symbol"]) for e in log}
        for it in all_items:
            fc = it.get("_fc")
            if fc and (str(today.date()), it["symbol"]) not in have:
                log.append({"date": str(today.date()), "made_at": now.isoformat(timespec="minutes"),
                            "symbol": it["symbol"], "name": fc[3], "group": it["group"],
                            "pred": 1 if fc[0] > 0 else -1, "score": round(fc[0], 1),
                            "comps": fc[1], "ref": round(fc[2], 4), "res": None})
    for it in all_items:
        it.pop("_fc", None)
    log = [e for e in log if (today - pd.Timestamp(e["date"])).days <= 400]
    if not demo:
        LOG.write_text(json.dumps(log, ensure_ascii=False, separators=(",", ":")))
    STATS.write_text(json.dumps(build_stats(log, data, bench, demo), ensure_ascii=False, indent=1))

    if not demo:
        extras(all_items, data)
    top = sorted([i for i in all_items if i["signals"]], key=lambda i: -i["score"])[:10]
    rotation = sorted(
        [{"symbol": i["symbol"], "name": i["name"], "group": i["group"], "rs5": i["rs5"], "rs20": i["rs20"],
          "state": i["rs_state"], "d1": i["d1"]}
         for i in all_items if i["symbol"] in SECTORS and "rs20" in i],
        key=lambda r: -r["rs20"])
    out = {
        "rotation": rotation,
        "generated": now.isoformat(timespec="minutes"),
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
