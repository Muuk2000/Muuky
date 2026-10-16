#!/usr/bin/env python3
"""Wirtschaftsseite: holt die Wirtschaftsnachrichten des Tages und ordnet sie dem Lehrplan zu.

Kosten: keine. Nur Standardbibliothek, Google News RSS ohne Schlüssel, keine KI.
Die Zuordnung zum Lehrplan arbeitet mit Stichwörtern (wirtschaft/data/lehrplan.json)
und ist eine grobe Vorsortierung, keine fachliche Bewertung.

Aufruf:  python wirtschaft_update.py
Ausgabe: wirtschaft/data/heute.json, wirtschaft/data/tage/JJJJ-MM-TT.json, wirtschaft/data/tage.json
"""
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).parent / "wirtschaft" / "data"
BERLIN = ZoneInfo("Europe/Berlin")
MAX_AGE_H = 40          # nur Meldungen der letzten ~Tage
MAX_ITEMS = 60
KEEP_DAYS = 90

# Suchbegriffe je Themenfeld (Google News, deutschsprachig)
QUERIES = [
    ("VWL", "Konjunktur Prognose Wirtschaft Deutschland"),
    ("VWL", "Inflation Verbraucherpreise"),
    ("VWL", "EZB Leitzins Zinsentscheidung"),
    ("VWL", "Arbeitsmarkt Arbeitslosigkeit Kurzarbeit"),
    ("VWL", "Bundeshaushalt Schulden Schuldenbremse"),
    ("VWL", "Rente Sozialversicherung Beiträge"),
    ("VWL", "Zölle Handelsabkommen Exporte"),
    ("VWL", "Energiepreise Ölpreis Gaspreis"),
    ("VWL", "Tarifabschluss Mindestlohn Löhne"),
    ("BWL", "Unternehmen Insolvenz Stellenabbau"),
    ("BWL", "Quartalszahlen Konzern Gewinn Umsatz"),
    ("BWL", "Lieferkette Produktion Industrie"),
    ("BWL", "Übernahme Fusion Unternehmen"),
    ("Kapitalmarkt", "DAX Börse Anleger"),
    ("Kapitalmarkt", "Anleihen Zinsen Geldanlage"),
    ("Recht", "Verbraucherschutz Urteil Wirtschaft"),
    ("Recht", "BGH Urteil Verbraucher Klausel"),
    ("Recht", "Bundesverfassungsgericht Urteil Beschluss"),
    ("Recht", "Widerruf Gewährleistung Verbraucherrecht Gesetz"),
    ("Recht", "Strafrecht Gesetzentwurf Bundestag Strafbarkeit"),
    ("Recht", "Datenschutz Bußgeld DSGVO Urteil"),
    ("Recht", "Wettbewerbsrecht Abmahnung Irreführung Werbung"),
    ("Recht", "Schadensersatz Haftung Urteil Kaufvertrag"),
]
SKIP = re.compile(r"Realtime|\|\s*Kurs|Fonds\s*\||Chart\s*$|Historische Kurse|Horoskop|Gewinnspiel", re.I)


def load_lehrplan():
    return json.loads((ROOT / "lehrplan.json").read_text(encoding="utf-8"))["bereiche"]


def kw_pattern(kw):
    kw = kw.strip().lower()
    pre = r"(?<![a-zäöüß])"
    post = r"(?![a-zäöüß])" if len(kw) <= 4 else ""
    return re.compile(pre + re.escape(kw) + post)


def build_matchers(bereiche):
    return [(b, [kw_pattern(k) for k in b["keywords"]]) for b in bereiche]


def match(title, matchers):
    t = title.lower()
    hits = []
    for b, pats in matchers:
        score = sum(1 for p in pats if p.search(t))
        if score:
            hits.append((score, b))
    hits.sort(key=lambda x: (-x[0], x[1]["id"]))
    return hits[:2]


def parse_feed(raw, fach, now):
    out = []
    root = ET.fromstring(raw)
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        src = (it.findtext("source") or "").strip()
        if src and title.endswith(" - " + src):
            title = title[: -len(src) - 3]
        try:
            dt = parsedate_to_datetime(it.findtext("pubDate"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if now - dt > timedelta(hours=MAX_AGE_H):
            continue
        if not title or not link.startswith("http") or SKIP.search(title):
            continue
        out.append({"t": title[:180], "u": link, "p": src, "ts": dt.astimezone(BERLIN).isoformat(timespec="minutes"), "fach": fach})
    return out


def fetch(query):
    q = urllib.parse.quote(f"{query} when:2d")
    url = f"https://news.google.com/rss/search?q={q}&hl=de&gl=DE&ceid=DE:de"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (wirtschaft-lehrplan)"})
    return urllib.request.urlopen(req, timeout=20).read()


def norm(t):
    return re.sub(r"[^a-zäöüß0-9]+", " ", t.lower()).strip()[:70]


def build(items, matchers):
    seen, res = set(), []
    for it in sorted(items, key=lambda x: x["ts"], reverse=True):
        k = norm(it["t"])
        if k in seen:
            continue
        seen.add(k)
        hits = match(it["t"], matchers)
        it["bezug"] = [
            {"id": b["id"], "jgst": b["jgst"], "titel": b["titel"], "niveau": b["niveau"], "score": s}
            for s, b in hits
        ]
        top = hits[0][0] if hits else 0
        it["passt"] = "gut" if top >= 2 else "bedingt" if top == 1 else "offen"
        res.append(it)
    # zuerst die mit Lehrplanbezug
    res.sort(key=lambda x: ({"gut": 0, "bedingt": 1, "offen": 2}[x["passt"]], x["ts"]), reverse=False)
    res.sort(key=lambda x: {"gut": 0, "bedingt": 1, "offen": 2}[x["passt"]])
    return res[:MAX_ITEMS]


def main():
    now = datetime.now(timezone.utc)
    matchers = build_matchers(load_lehrplan())
    items, ok, fail = [], 0, 0
    for fach, q in QUERIES:
        try:
            items += parse_feed(fetch(q), fach, now)
            ok += 1
        except Exception as e:  # ein ausgefallener Feed darf den Lauf nicht abbrechen
            fail += 1
            print(f"Feed fehlgeschlagen ({q}): {e}", file=sys.stderr)
    if ok == 0:
        print("Kein Feed erreichbar - bestehende Daten bleiben unverändert.", file=sys.stderr)
        return 0
    res = build(items, matchers)
    today = now.astimezone(BERLIN).date().isoformat()
    payload = {
        "generated": now.astimezone(BERLIN).isoformat(timespec="minutes"),
        "datum": today,
        "feeds_ok": ok,
        "feeds_fehler": fail,
        "hinweis": "Automatische Vorsortierung nach Stichwörtern. Keine fachliche Bewertung, bitte vor dem Einsatz prüfen.",
        "items": res,
    }
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "tage").mkdir(exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=1)
    (ROOT / "heute.json").write_text(text, encoding="utf-8")
    (ROOT / "tage" / f"{today}.json").write_text(text, encoding="utf-8")
    # Archiv-Index, alte Tage aufräumen
    cutoff = (now.astimezone(BERLIN).date() - timedelta(days=KEEP_DAYS)).isoformat()
    days = []
    for f in sorted((ROOT / "tage").glob("*.json")):
        if f.stem < cutoff:
            f.unlink()
        else:
            days.append(f.stem)
    (ROOT / "tage.json").write_text(json.dumps(sorted(days, reverse=True)), encoding="utf-8")
    print(f"{len(res)} Meldungen, {ok} Feeds ok, {fail} Fehler")
    return 0


if __name__ == "__main__":
    sys.exit(main())
