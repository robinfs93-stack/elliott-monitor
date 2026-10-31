"""Holt Tageskerzen, rechnet die Elliott-Analyse und schreibt data/*.json.

Quellen: Yahoo Finance (Aktien, Indizes, Krypto-Fallback), KuCoin (Krypto).
Schlaegt ein Abruf fehl, bleiben die letzten guten Daten erhalten und werden als veraltet markiert.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from elliott import analyze  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_json(url, tries=3):
    last = None
    for t in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 + 3 * t)
    raise RuntimeError(f"{url}: {last}")


def yahoo(symbol):
    sym = urllib.parse.quote(symbol)
    for host in ("query1", "query2"):
        try:
            d = get_json(f"https://{host}.finance.yahoo.com/v8/finance/chart/{sym}?range=2y&interval=1d")
            break
        except Exception:  # noqa: BLE001
            d = None
    if not d:
        raise RuntimeError(f"Yahoo {symbol}: keine Antwort")
    r = d["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    out = []
    for i, ts in enumerate(r["timestamp"]):
        vals = [q["open"][i], q["high"][i], q["low"][i], q["close"][i]]
        if any(x is None for x in vals):
            continue
        # Yahoo-Zeitstempel = Handelsbeginn; Datum in Boersenzeitzone
        off = r["meta"].get("gmtoffset", 0)
        day = datetime.fromtimestamp(ts + off, timezone.utc).strftime("%Y-%m-%d")
        out.append([day] + [float(x) for x in vals] + [float(q["volume"][i] or 0)])
    return dedupe(out)


def kucoin(symbol):
    end = int(time.time())
    start = end - 2 * 365 * 86400
    d = get_json(f"https://api.kucoin.com/api/v1/market/candles?type=1day&symbol={symbol}&startAt={start}&endAt={end}")
    if d.get("code") != "200000" or not d.get("data"):
        raise RuntimeError(f"KuCoin {symbol}: {d.get('msg', 'leer')}")
    out = []
    for row in d["data"]:  # [time, open, close, high, low, volume, turnover], neueste zuerst
        day = datetime.fromtimestamp(int(row[0]), timezone.utc).strftime("%Y-%m-%d")
        out.append([day, float(row[1]), float(row[3]), float(row[4]), float(row[2]), float(row[5])])
    out.sort(key=lambda x: x[0])
    return dedupe(out)


def dedupe(rows):
    seen = {}
    for r in rows:
        seen[r[0]] = r
    return [seen[k] for k in sorted(seen)]


def drop_incomplete(rows, crypto):
    # Krypto: Tageskerze des laufenden UTC-Tages ist unvollstaendig.
    # Aktien: um 6 Uhr gibt es keine laufende Kerze; zur Sicherheit heutige Zeile ebenfalls verwerfen.
    if rows and rows[-1][0] >= TODAY:
        rows = rows[:-1]
    return rows


def load_previous(aid):
    p = os.path.join(DATA, f"{aid}.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None


def main():
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(ROOT, "config", "assets.json"), encoding="utf-8") as f:
        assets = json.load(f)
    summary = {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "assets": []}
    errors = 0
    for a in assets:
        crypto = "kucoin" in a
        rows, source, err = None, None, None
        attempts = ([("KuCoin", kucoin, a["kucoin"])] if crypto else []) + \
                   ([("Yahoo Finance", yahoo, a["yahoo"])] if a.get("yahoo") else [])
        for name, fn, sym in attempts:
            try:
                rows = drop_incomplete(fn(sym), crypto)
                if len(rows) < 60:
                    raise RuntimeError(f"nur {len(rows)} Kerzen")
                source = f"{name} ({sym})"
                break
            except Exception as e:  # noqa: BLE001
                err = str(e)
                rows = None
        stale = False
        if rows is None:
            errors += 1
            prev = load_previous(a["id"])
            if not prev:
                print(f"[FEHLER] {a['name']}: {err}")
                summary["assets"].append({**a, "error": f"Keine Daten: {err}"})
                continue
            rows, source, stale = prev["candles"], prev.get("source", "?"), True
            print(f"[VERALTET] {a['name']}: {err} – nutze letzte Daten bis {rows[-1][0]}")
        else:
            print(f"[OK] {a['name']}: {len(rows)} Kerzen bis {rows[-1][0]} von {source}")

        res = analyze(rows)
        doc = {**a, "source": source, "stale": stale, "candles": [[r[0]] + [round(x, 8) for x in r[1:]] for r in rows],
               "analysis": res}
        with open(os.path.join(DATA, f"{a['id']}.json"), "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))

        entry = {**a, "source": source, "stale": stale}
        if "error" in res:
            entry["error"] = res["error"]
            entry["price"] = rows[-1][4]
            entry["date"] = rows[-1][0]
        else:
            p = res["primary"]
            entry.update({
                "price": res["price"], "date": res["date"], "change_1d": res["change_1d"], "rsi": res["rsi"],
                "sma200": res["sma200"],
                "spark": [r[4] for r in rows[-90:]],
                "primary": {k: p[k] for k in ("pattern", "current", "phase", "bias", "score", "degree",
                                              "invalidation", "invalidation_dist", "next_target")},
                "alternative": ({k: res["alternative"][k] for k in ("pattern", "current", "bias", "score")}
                                if res["alternative"] else None),
            })
        summary["assets"].append(entry)

    with open(os.path.join(DATA, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Fertig. {len(assets) - errors}/{len(assets)} Werte aktuell.")
    if errors == len(assets):
        sys.exit(1)


if __name__ == "__main__":
    main()
