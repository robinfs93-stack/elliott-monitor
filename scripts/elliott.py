"""Algorithmische Elliott-Wellen-Zaehlung auf Tageskerzen.

Vorgehen
1. Wendepunkte per ZigZag mit ATR-Schwelle auf mehreren Graden (fein bis uebergeordnet).
2. Fuer jede Pivot-Folge werden Impuls- (1-5, optional mit A-B-C) und reine
   A-B-C-Interpretationen gebildet, die am aktuellen Kurs enden.
3. Harte Regeln filtern, Fibonacci-Richtlinien bewerten (Passung 0..1).
4. Beste Zaehlung = Hauptszenario, naechstbeste mit anderer Aussage = Alternative.
5. Ziele, Zielzonen und Invalidierung werden aus der Zaehlung abgeleitet.
"""
import math

DEGREES = [
    (2.0, "Fein"),
    (3.0, "Mittel"),
    (4.5, "Grob"),
    (6.5, "Übergeordnet"),
]
MAX_PIVOTS = 16


# ---------------------------------------------------------------- Indikatoren
def atr(h, l, c, n=14):
    tr = [h[0] - l[0]]
    for i in range(1, len(c)):
        tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    out = []
    a = sum(tr[:n]) / min(n, len(tr))
    for i, t in enumerate(tr):
        if i < n:
            a = sum(tr[: i + 1]) / (i + 1)
        else:
            a = (a * (n - 1) + t) / n
        out.append(a)
    return out


def rsi(c, n=14):
    out = [None] * len(c)
    if len(c) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = c[i] - c[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    ag, al = gains / n, losses / n
    out[n] = 100 - 100 / (1 + ag / al) if al else 100.0
    for i in range(n + 1, len(c)):
        d = c[i] - c[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        out[i] = 100 - 100 / (1 + ag / al) if al else 100.0
    return out


def sma(c, n):
    if len(c) < n:
        return None
    return sum(c[-n:]) / n


# ---------------------------------------------------------------- ZigZag
def zigzag(h, l, atrs, k):
    """Liefert Pivots (index, preis, 'H'/'L'); letzter Pivot ist vorlaeufig (laufendes Extrem)."""
    n = len(h)
    piv = []
    trend = 0
    hi, lo, hi_i, lo_i = h[0], l[0], 0, 0
    cand, cand_i = None, None
    for i in range(n):
        thr = k * atrs[i]
        if trend == 0:
            if h[i] > hi:
                hi, hi_i = h[i], i
            if l[i] < lo:
                lo, lo_i = l[i], i
            if hi - lo >= thr:
                if hi_i > lo_i:
                    piv.append((lo_i, lo, "L"))
                    trend, cand, cand_i = 1, hi, hi_i
                else:
                    piv.append((hi_i, hi, "H"))
                    trend, cand, cand_i = -1, lo, lo_i
        elif trend == 1:
            if h[i] >= cand:
                cand, cand_i = h[i], i
            elif cand - l[i] >= thr:
                piv.append((cand_i, cand, "H"))
                trend, cand, cand_i = -1, l[i], i
        else:
            if l[i] <= cand:
                cand, cand_i = l[i], i
            elif h[i] - cand >= thr:
                piv.append((cand_i, cand, "L"))
                trend, cand, cand_i = 1, h[i], i
    if trend != 0:
        piv.append((cand_i, cand, "H" if trend == 1 else "L"))
    return piv


# ---------------------------------------------------------------- Bewertung
def fit(x, targets, tol):
    return max(math.exp(-(((x - t) / tol) ** 2)) for t in targets)


def de(x, d):
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(x):
    return de(x * 100, 1) + " %"


def ratio(x):
    return de(x, 2)


def num(x):
    a = abs(x)
    return de(x, 0 if a >= 1000 else 2 if a >= 1 else 4 if a >= 0.01 else 6)


def significance(idx, price, kind, h, l, lookback=250):
    """Wie viele Kerzen vor dem Startpunkt lag kein tieferes Tief (bzw. hoeheres Hoch)?"""
    cnt = 0
    j = idx - 1
    while j >= 0 and cnt < lookback:
        if kind == "L" and l[j] < price:
            break
        if kind == "H" and h[j] > price:
            break
        cnt += 1
        j -= 1
    return cnt / lookback


def eval_impulse(v, m):
    """v: Punkte in 'Aufwaerts'-Orientierung (v0 Tief). m Teilwellen (2..8).
    Rueckgabe (ok, rules, guides, notes) oder None bei Regelbruch."""
    rules, guides = [], []
    L = [None] + [abs(v[j] - v[j - 1]) for j in range(1, m + 1)]
    if any(x == 0 for x in L[1:]):
        return None

    # Regel 1: Welle 2 korrigiert nie mehr als 100 % von Welle 1
    r2 = L[2] / L[1]
    ok = v[2] > v[0]
    rules.append({"name": "Welle 2 unterschreitet nicht den Start von Welle 1", "ok": ok,
                  "detail": f"Korrektur {pct(r2)} von Welle 1"})
    if not ok:
        return None
    guides.append({"w": 2, "name": "Welle 2 / Welle 1", "actual": pct(r2), "ideal": "50–61,8 %",
                   "score": max(fit(r2, [0.5, 0.618], 0.15), 0.8 * fit(r2, [0.382], 0.1))})

    if m >= 3:
        r3 = L[3] / L[1]
        guides.append({"w": 3, "name": "Welle 3 / Welle 1", "actual": ratio(r3), "ideal": "1,618 (oder 2,618)",
                       "score": max(fit(r3, [1.618], 0.4), fit(r3, [2.618], 0.6))})
        if m >= 4:
            ok = v[3] > v[1]
            rules.append({"name": "Welle 3 übersteigt das Ende von Welle 1", "ok": ok,
                          "detail": f"Welle 3 = {ratio(r3)} × Welle 1"})
            if not ok:
                return None

    if m >= 4:
        r4 = L[4] / L[3]
        ok = v[4] > v[1]
        rules.append({"name": "Welle 4 überlappt nicht mit Welle 1", "ok": ok,
                      "detail": f"Abstand Welle-4-Tief zu Welle-1-Hoch: {pct((v[4] - v[1]) / L[1])} von W1"})
        if not ok:
            return None
        guides.append({"w": 4, "name": "Welle 4 / Welle 3", "actual": pct(r4), "ideal": "23,6–38,2 %",
                       "score": fit(r4, [0.382, 0.236], 0.12)})
        deep2, deep4 = r2 > 0.5, r4 > 0.5
        guides.append({"w": 4, "name": "Wechselregel (W2 vs. W4)", "actual": f"W2 {pct(r2)}, W4 {pct(r4)}",
                       "ideal": "eine tief, eine flach", "score": 1.0 if deep2 != deep4 else 0.45})

    if m >= 5:
        shortest = L[3] < L[1] and L[3] < L[5]
        rules.append({"name": "Welle 3 ist nicht die kürzeste", "ok": not shortest,
                      "detail": f"Längen: W1 {num(L[1])} · W3 {num(L[3])} · W5 {num(L[5])}"})
        if shortest:
            return None
        r5 = L[5] / L[1]
        guides.append({"w": 5, "name": "Welle 5 / Welle 1", "actual": ratio(r5), "ideal": "1,0 oder 0,618",
                       "score": max(fit(r5, [1.0], 0.25), fit(r5, [0.618], 0.15))})
        if m >= 6 and r5 < 0.236:
            return None  # abgeschlossene Welle 5 unter 23,6 % von W1: Struktur nicht plausibel
        if m >= 6:
            guides.append({"w": 5, "name": "Welle 5 übersteigt Welle 3", "actual": "ja" if v[5] > v[3] else "nein (verkürzt)",
                           "ideal": "ja", "score": 1.0 if v[5] > v[3] else 0.3})

    # Korrektur nach dem Impuls
    if m >= 6:
        imp = v[5] - v[0]
        ok = all(v[j] > v[0] for j in range(6, m + 1))
        rules.append({"name": "Korrektur bleibt über dem Impulsstart", "ok": ok,
                      "detail": f"Welle A korrigiert {pct((v[5] - v[6]) / imp)} des Impulses"})
        if not ok:
            return None
        ra = (v[5] - v[6]) / imp
        guides.append({"w": 6, "name": "Welle A / Impuls", "actual": pct(ra), "ideal": "38,2–50 % (Zone Welle 4)",
                       "score": fit(ra, [0.382, 0.5], 0.15)})
    if m >= 7:
        rb = (v[7] - v[6]) / (v[5] - v[6])
        ok = rb < 1.38
        rules.append({"name": "Welle B max. 138 % von Welle A", "ok": ok, "detail": f"B = {pct(rb)} von A"})
        if not ok:
            return None
        guides.append({"w": 7, "name": "Welle B / Welle A", "actual": pct(rb), "ideal": "50–78,6 % (Zickzack) / 90–100 % (Flat)",
                       "score": max(fit(rb, [0.5, 0.618, 0.786], 0.12), fit(rb, [0.95], 0.08))})
    if m >= 8:
        rc = L[8] / L[6]
        guides.append({"w": 8, "name": "Welle C / Welle A", "actual": ratio(rc), "ideal": "1,0 (oder 1,618 / 0,618)",
                       "score": max(fit(rc, [1.0], 0.2), fit(rc, [1.618, 0.618], 0.15))})
    return rules, guides


def eval_abc(v, m, prior_leg):
    """Reine Korrektur A-B-C; v0 = Start, Welle A aufwaerts orientiert."""
    rules, guides = [], []
    L = [None] + [abs(v[j] - v[j - 1]) for j in range(1, m + 1)]
    if any(x == 0 for x in L[1:]):
        return None
    rb = L[2] / L[1]
    ok = rb < 1.38
    rules.append({"name": "Welle B max. 138 % von Welle A", "ok": ok, "detail": f"B = {pct(rb)} von A"})
    if not ok:
        return None
    guides.append({"w": 2, "name": "Welle B / Welle A", "actual": pct(rb), "ideal": "50–78,6 % (Zickzack) / 90–100 % (Flat)",
                   "score": max(fit(rb, [0.5, 0.618, 0.786], 0.12), fit(rb, [0.95], 0.08))})
    if m >= 3:
        rc = L[3] / L[1]
        guides.append({"w": 3, "name": "Welle C / Welle A", "actual": ratio(rc), "ideal": "1,0 (oder 1,618 / 0,618)",
                       "score": max(fit(rc, [1.0], 0.2), fit(rc, [1.618, 0.618], 0.15))})
    if prior_leg:
        total = max(v[1:m + 1]) - v[0]
        rr = total / prior_leg
        ok = rr < 1.0
        rules.append({"name": "Korrektur kleiner als die vorherige Bewegung", "ok": ok,
                      "detail": f"Korrigiert {pct(rr)} der Vorbewegung"})
        if not ok:
            return None
        guides.append({"w": 3, "name": "Korrekturtiefe / Vorbewegung", "actual": pct(rr), "ideal": "38,2–61,8 %",
                       "score": fit(rr, [0.382, 0.5, 0.618], 0.15)})
    return rules, guides


COMPLETENESS = {2: 0.55, 3: 0.8, 4: 0.92, 5: 1.0, 6: 1.0, 7: 1.0, 8: 1.0}
IMPULSE_LABELS = ["0", "1", "2", "3", "4", "5", "A", "B", "C"]
ABC_LABELS = ["0", "A", "B", "C"]


# ---------------------------------------------------------------- Projektion
def project(kind, v, m, s, price_now):
    """Zielzonen, Invalidierung, Erwartung. v in Orientierung, s = +1/-1 Rueckrechnung."""
    P = lambda x: s * x  # zurueck in echten Preis
    L = [None] + [abs(v[j] - v[j - 1]) for j in range(1, m + 1)]
    targets, invalid = [], None
    up = s == 1

    def T(label, x, role="Ziel"):
        targets.append({"label": label, "price": P(x), "role": role})

    if kind == "impulse":
        word = "aufwärts" if up else "abwärts"
        if m == 2:
            cur = "Welle 2"
            T("W2 bei 50 %", v[1] - 0.5 * L[1], "Zone")
            T("W2 bei 61,8 %", v[1] - 0.618 * L[1], "Zone")
            T("W3 = 1,618 × W1", v[2] + 1.618 * L[1])
            T("W3 = 2,618 × W1", v[2] + 2.618 * L[1])
            invalid = (P(v[0]), "Start von Welle 1")
            expect = f"Korrektur Welle 2 läuft/endet, danach Welle 3 {word} erwartet"
            next_dir = s
        elif m == 3:
            cur = "Welle 3"
            T("W3 = 1,0 × W1", v[2] + 1.0 * L[1])
            T("W3 = 1,618 × W1", v[2] + 1.618 * L[1])
            T("W3 = 2,618 × W1", v[2] + 2.618 * L[1])
            invalid = (P(v[1]), "Ende Welle 1 (Welle 4 darf nicht überlappen)")
            expect = f"Welle 3 {word} läuft, danach Korrektur Welle 4"
            next_dir = s
        elif m == 4:
            cur = "Welle 4"
            T("W4 bei 23,6 %", v[3] - 0.236 * L[3], "Zone")
            T("W4 bei 38,2 %", v[3] - 0.382 * L[3], "Zone")
            T("W5 = 0,618 × W1", v[4] + 0.618 * L[1])
            T("W5 = 1,0 × W1", v[4] + 1.0 * L[1])
            T("W5 = 0,618 × (W1 bis W3)", v[4] + 0.618 * (v[3] - v[0]))
            invalid = (P(v[1]), "Ende Welle 1 (Überlappung)")
            expect = f"Korrektur Welle 4 läuft, danach letzte Welle 5 {word}"
            next_dir = s
        elif m == 5:
            cur = "Welle 5"
            T("W5 = 0,618 × W1", v[4] + 0.618 * L[1])
            T("W5 = 1,0 × W1", v[4] + 1.0 * L[1])
            T("W5 = 1,618 × W1", v[4] + 1.618 * L[1])
            if L[3] < L[1]:
                T("Max. W5 (W3 nicht kürzeste)", v[4] + L[3], "Grenze")
            invalid = (P(v[4]), "Ende Welle 4 (Bruch = Impuls beendet)")
            expect = f"Letzte Welle 5 {word} läuft – Impulsende nahe, danach A-B-C-Korrektur"
            next_dir = s
        elif m == 6:
            cur = "Welle A"
            imp = v[5] - v[0]
            T("A bei 38,2 % des Impulses", v[5] - 0.382 * imp, "Zone")
            T("A bei 50 % des Impulses", v[5] - 0.5 * imp, "Zone")
            T("Zone Welle 4", v[4], "Zone")
            invalid = (P(v[5]), "Hoch von Welle 5 (sonst verlängerte W5)")
            expect = "Impuls abgeschlossen, Korrekturwelle A läuft gegen den Trend"
            next_dir = -s
        elif m == 7:
            cur = "Welle B"
            A = L[6]
            T("B bei 50 % von A", v[6] + 0.5 * A, "Zone")
            T("B bei 61,8 % von A", v[6] + 0.618 * A, "Zone")
            T("B bei 78,6 % von A", v[6] + 0.786 * A, "Zone")
            T("C = 1,0 × A", v[7] - 1.0 * A)
            T("C = 1,618 × A", v[7] - 1.618 * A)
            invalid = (P(v[5] + 0.38 * A), "138 % von A (Flat-Grenze)")
            expect = "Gegenbewegung B läuft, danach Welle C gegen den Trend"
            next_dir = -s
        else:
            cur = "Welle C"
            A = L[6]
            T("C = 0,618 × A", v[7] - 0.618 * A)
            T("C = 1,0 × A", v[7] - 1.0 * A)
            T("C = 1,618 × A", v[7] - 1.618 * A)
            invalid = (P(v[7]), "Ende Welle B")
            expect = "Welle C läuft – Korrekturende nahe, danach neuer Impuls im Haupttrend"
            next_dir = -s
        name = f"Impuls {word}"
    else:
        word = "aufwärts" if up else "abwärts"
        A = L[1]
        if m == 2:
            cur = "Welle B"
            T("B bei 50 % von A", v[1] - 0.5 * A, "Zone")
            T("B bei 61,8 % von A", v[1] - 0.618 * A, "Zone")
            T("B bei 78,6 % von A", v[1] - 0.786 * A, "Zone")
            T("C = 1,0 × A", v[2] + 1.0 * A)
            T("C = 1,618 × A", v[2] + 1.618 * A)
            invalid = (P(v[0] - 0.38 * A), "138 % von A")
            expect = f"Korrektur {word}: B läuft, danach Welle C {word}"
            next_dir = s
        else:
            cur = "Welle C"
            T("C = 0,618 × A", v[2] + 0.618 * A)
            T("C = 1,0 × A", v[2] + 1.0 * A)
            T("C = 1,618 × A", v[2] + 1.618 * A)
            invalid = (P(v[2]), "Ende Welle B")
            expect = f"Korrekturwelle C {word} läuft – danach Wiederaufnahme des übergeordneten Trends"
            next_dir = s
        name = f"A-B-C-Korrektur {word}"
    # Ziele in Bewegungsrichtung zuerst, nach Abstand sortiert
    if kind == "impulse":
        cur_dir = {1: s, 2: -s, 3: s, 4: -s, 5: s, 6: -s, 7: s, 8: -s}[m]
    else:
        cur_dir = {2: -s, 3: s}[m]
    return {"pattern": name, "current": cur, "expect": expect, "targets": targets, "cur_dir": cur_dir,
            "invalidation": {"price": invalid[0], "text": invalid[1]},
            "next_dir": next_dir}


# ---------------------------------------------------------------- Hauptanalyse
def analyze(candles):
    dates = [c[0] for c in candles]
    o = [c[1] for c in candles]
    h = [c[2] for c in candles]
    l = [c[3] for c in candles]
    c = [c[4] for c in candles]
    n = len(c)
    if n < 60:
        return {"error": "Zu wenig Kursdaten für eine Zählung (mind. 60 Tageskerzen)."}
    atrs = atr(h, l, c)
    rsis = rsi(c)
    price = c[-1]
    cands = []
    seen = set()
    zz_by_degree = {}

    def score_guides(guides, m, live):
        """Richtlinien der noch laufenden Welle zaehlen nicht (Welle ist unfertig)."""
        used = []
        for g in guides:
            if live and g["w"] == m:
                g["live"] = True
                continue
            used.append(g["score"])
        return sum(used) / len(used) if used else 0.35

    for k, deg in DEGREES:
        piv = zigzag(h, l, atrs, k)
        zz_by_degree[deg] = piv
        if len(piv) < 3:
            continue
        piv = piv[-MAX_PIVOTS:]
        last = len(piv) - 1
        thr = k * atrs[-1]
        # Ruecklauf seit dem laufenden Extrem, gemessen an der Schwelle
        li, lp, lt = piv[last]
        if lt == "H":
            ext_i = min(range(li, n), key=lambda j: l[j])
            ext_p = l[ext_i]
        else:
            ext_i = max(range(li, n), key=lambda j: h[j])
            ext_p = h[ext_i]
        back = abs(ext_p - lp) / thr if thr else 0
        piv_ext = piv + [(ext_i, ext_p, "L" if lt == "H" else "H")] if back >= 0.5 and ext_i > li else None

        # Deutlicher Ruecklauf: laufendes Extrem gilt als Wellenende, die Gegenbewegung als neue (laufende) Welle
        variants = [(piv_ext, True)] if piv_ext else [(piv, False)]
        for pv, extended in variants:
            lastp = len(pv) - 1
            for i in range(lastp - 1, -1, -1):
                m = lastp - i
                if m < 2 or m > 8:
                    continue
                seq = pv[i:]
                s = 1 if seq[0][2] == "L" else -1
                v = [s * p[1] for p in seq]
                key = tuple((p[0], round(p[1], 8)) for p in seq)
                # Nicht erweiterte Variante bei deutlichem Ruecklauf: letzte Welle fertig, Bewertung leicht abgewertet
                live = True
                penalty = 1.0

                res = eval_impulse(v, m)
                if res and ("I", key) not in seen:
                    rules, guides = res
                    if m >= 5 and rsis[seq[3][0]] is not None and rsis[seq[5][0]] is not None:
                        div = (rsis[seq[5][0]] < rsis[seq[3][0]]) if s == 1 else (rsis[seq[5][0]] > rsis[seq[3][0]])
                        guides.append({"w": 5, "name": "RSI-Divergenz W5 zu W3", "actual": "ja" if div else "nein",
                                       "ideal": "ja", "score": 1.0 if div else 0.5})
                    sig = significance(seq[0][0], seq[0][1], seq[0][2], h, l)
                    g = score_guides(guides, m, live)
                    score = g * COMPLETENESS[m] * (0.85 + 0.15 * sig) * penalty
                    seen.add(("I", key))
                    cands.append(dict(kind="impulse", m=m, s=s, seq=seq, v=v, rules=rules, guides=guides,
                                      score=score, degree=deg, k=k, live=live))
                if m <= 3 and i >= 1:
                    prior = abs(pv[i][1] - pv[i - 1][1])
                    res = eval_abc(v, m, prior)
                    if res and ("C", key) not in seen:
                        rules, guides = res
                        g = score_guides(guides, m, live)
                        score = g * COMPLETENESS[m + 2] * 0.82 * penalty
                        seen.add(("C", key))
                        cands.append(dict(kind="abc", m=m, s=s, seq=seq, v=v, rules=rules, guides=guides,
                                          score=score, degree=deg, k=k, live=live))

    if not cands:
        return {"error": "Keine regelkonforme Zählung gefunden – Markt läuft ohne klare Wellenstruktur."}

    cands.sort(key=lambda x: -x["score"])

    def build(cd):
        pr = project(cd["kind"], cd["v"], cd["m"], cd["s"], price)
        labels = IMPULSE_LABELS if cd["kind"] == "impulse" else ABC_LABELS
        pts = [{"date": dates[p[0]], "price": p[1], "label": labels[j]} for j, p in enumerate(cd["seq"])]
        phase = f"{pr['current']} läuft" if cd["live"] else f"{pr['current']} vermutlich abgeschlossen"
        inv = pr["invalidation"]["price"]
        dist = (inv - price) / price
        cur = pr["cur_dir"] if cd["live"] else pr["next_dir"]
        ahead = [t for t in pr["targets"] if (t["price"] - price) * cur > 0 and t["role"] != "Grenze"]
        ahead.sort(key=lambda t: abs(t["price"] - price))
        return {
            "pattern": pr["pattern"], "current": pr["current"], "phase": phase,
            "expect": pr["expect"], "degree": cd["degree"],
            "bias": "steigend" if cur == 1 else "fallend",
            "score": round(cd["score"] * 100),
            "points": pts, "targets": pr["targets"], "invalidation": pr["invalidation"],
            "invalidation_dist": dist,
            "next_target": ahead[0] if ahead else None,
            "rules": cd["rules"],
            "guides": [{**{k2: g[k2] for k2 in ("name", "actual", "ideal")},
                        "score": None if g.get("live") else round(g["score"] * 100)} for g in cd["guides"]],
        }

    primary = build(cands[0])
    alt = None
    for cd in cands[1:]:
        b = build(cd)
        if (b["pattern"], b["current"]) != (primary["pattern"], primary["current"]):
            alt = b
            break

    s50, s200 = sma(c, 50), sma(c, 200)
    return {
        "price": price,
        "date": dates[-1],
        "change_1d": (c[-1] / c[-2] - 1) if n > 1 else 0,
        "rsi": rsis[-1],
        "sma50": s50, "sma200": s200,
        "atr": atrs[-1],
        "primary": primary,
        "alternative": alt,
        "zigzag": {deg: [{"date": dates[p[0]], "price": p[1]} for p in zz[-40:]] for deg, zz in zz_by_degree.items()},
    }
