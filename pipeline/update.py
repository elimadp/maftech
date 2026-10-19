#!/usr/bin/env python3
"""Daily data refresh for the "מפתח" app.

Usage:
  python3 update.py --app index.html --data DIR --out index.new.html [--market market.json]

DIR holds the mapping caches (dict.json, gush_area.json, gush_top_helka.json); new blocks found
in the deals are looked up and the caches are updated in place.
Exits with code 2 if a sanity check fails (then do NOT publish).
"""
import argparse, collections, datetime, json, os, re, statistics, sys, time
import requests

SQL_URL = "https://www.over.org.il/api/append/fd06f5ae-8a4f-4120-b275-8a514ad23499/sql"
DEALS = "append_taxes_nadlan_full_f41fb496_fd06f5ae"
LOTTERIES = "append_mechir_lamishtaken_68269ade_7c8255d0"
LOOKUP = "https://www.over.org.il/api/nadlan/lookup"
HEB_MONTHS = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני", "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"]
NATURE = {"דירה בבית קומות": "A", "דירת גן": "G", "דירת גג": "R", "מגורים": "M",
          "קוטג' דו משפחתי": "H", "קוטג' חד משפחתי": "H", "קוטג' טורי": "H", "בית בודד": "H"}
AGES = ["all", "new", "old", "m93", "p93"]          # building age (separate question)
ROOMS = ["all", "r3", "r4", "r5", "house"]          # rooms / type (separate question); key = ai * 5 + ri


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def q(sql, tries=6):
    for a in range(tries):
        try:
            r = requests.post(SQL_URL, json={"sql": sql}, timeout=290)
            if r.status_code == 200 and "rows" in r.json():
                return r.json()["rows"]
            log("  SQL ERR", r.status_code, r.text[:200])
        except Exception as e:
            log("  SQL EXC", e)
        time.sleep(8 * (a + 1))
    raise RuntimeError("SQL failed: " + sql[:120])


def sq(s):
    return "'" + s.replace("'", "''") + "'"


# ---------------------------------------------------------------- lotteries -> OFFICIAL
def build_official():
    rows = []
    off = 0
    while True:
        r = q(f"SELECT * FROM {LOTTERIES} ORDER BY \"LotteryId\" LIMIT 1000 OFFSET {off}")
        rows += r
        off += 1000
        if len(r) < 1000:
            break
    first = [x for x in rows if x.get("LotteryType") == "ראשונה" and x.get("LotteryExecutionDate")]
    provs = sorted({(x.get("ProviderName") or "-").strip()[:30] for x in first} | {"-"})
    pi = {p: i for i, p in enumerate(provs)}
    p = []
    for x in sorted(first, key=lambda x: (x["LamasName"], x["LotteryExecutionDate"])):
        try:
            units = int(float(x.get("LotteryHousingUnits") or 0))
            pp = int(float(str(x.get("PriceForMeter") or "0").replace(",", "")))
        except ValueError:
            continue
        p.append([x["LamasName"].strip(), (x.get("Neighborhood") or "").strip(), (x.get("ProjectName") or "").strip(),
                  pi[(x.get("ProviderName") or "-").strip()[:30]], x["LotteryExecutionDate"][:10], units, pp,
                  1 if "מטרה" in (x.get("MarketingMethodDesc") or "") else 0])
    return {"provs": provs, "p": p}, len(rows)


# ---------------------------------------------------------------- deals (5 years)
def pull_deals(since):
    case = "CASE deal_nature " + " ".join(f"WHEN {sq(k)} THEN '{v}'" for k, v in NATURE.items()) + " END"
    inl = ",".join(sq(k) for k in NATURE)
    cities, off = [], 0
    while True:   # the SQL endpoint returns at most 1000 rows per query
        r = q(f"SELECT DISTINCT settlement FROM {DEALS} WHERE settlement IS NOT NULL ORDER BY 1 LIMIT 1000 OFFSET {off}")
        cities += [x["settlement"] for x in r]
        off += 1000
        if len(r) < 1000:
            break
    log(f"  {len(cities)} settlements")
    out = {}
    for i in range(0, len(cities), 15):
        grp = cities[i:i + 15]
        r = q(f"SELECT settlement, gush, string_agg(to_char(to_date(deal_date,'DD/MM/YYYY'),'YYMM')||'|'||deal_amount||'|'||coalesce(year_built,'')||'|'||coalesce(room_num,'')||'|'||coalesce(asset_area,'')||'|'||{case}||'|'||coalesce(chelka,''),';') s "
              f"FROM {DEALS} WHERE settlement IN ({','.join(sq(c) for c in grp)}) AND to_date(deal_date,'DD/MM/YYYY')>='{since}' "
              f"AND deal_nature IN ({inl}) AND portion='1.000' GROUP BY settlement, gush")
        for x in r:
            out.setdefault(x["settlement"], {})[x["gush"]] = x["s"]
        if i % 150 == 0:
            log(f"  deals: {i}/{len(cities)} cities")
    return out


# ---------------------------------------------------------------- block -> statistical area
def lookup_new_gushes(deals, ga, top, recent_cut, cap=400):
    new = collections.Counter()
    helka = collections.defaultdict(collections.Counter)
    city_of = {}
    for city, gs in deals.items():
        for g, s in gs.items():
            if g in ga:
                continue
            for d in s.split(";"):
                f = d.split("|")
                if int(f[0]) >= recent_cut:
                    new[g] += 1
                    helka[g][f[6]] += 1
                    city_of[g] = city
    todo = [g for g, _ in new.most_common(cap)]
    log(f"  unmapped blocks with recent deals: {len(new)}, looking up {len(todo)}")
    for g in todo:
        res = None
        for h, _ in helka[g].most_common(3):
            if not h:
                continue
            try:
                for k in range(3):
                    try:
                        j = requests.get(LOOKUP, params={"gush": g, "helka": h, "fields": "stat_area,identity"}, timeout=60).json()
                        break
                    except requests.exceptions.RequestException:
                        if k == 2:
                            raise
                        time.sleep(4 * (k + 1))
                d = (j.get("data") or [None])[0]
                if d and (d.get("stat_area") or {}).get("yishuv_stat"):
                    idn = d.get("identity") or {}
                    res = {"stat": d["stat_area"]["yishuv_stat"], "city": (idn.get("settlement") or {}).get("name"), "via": h}
                    break
            except Exception as e:
                log("  lookup err", g, e)
                time.sleep(3)
        ga[g] = res
        top[g] = {"gush": g, "settlement": city_of[g], "chelka": helka[g].most_common(1)[0][0], "n": new[g]}
    return len(todo)


def area_map(D, ga, top):
    groups = collections.defaultdict(set)
    gk = {}
    for g, v in ga.items():
        if not (isinstance(v, dict) and v.get("stat")) or g not in top:
            continue
        code = str(v["stat"])
        city = top[g]["settlement"]
        r = D.get(code)
        key = ("nb", (r["nb"] or "").strip()) if r and (r.get("nb") or "").strip() else ("sa", code)
        groups[(city, key)].add(g)
        gk[g] = (city, key)

    def label(city, key):
        if key[0] == "nb":
            return key[1]
        r = D.get(key[1])
        st = [s.strip() for s in ((r or {}).get("st") or "").split(",") if s.strip()]
        if not st:
            for g in sorted(groups[(city, key)]):
                if (ga[g] or {}).get("streets"):
                    st = ga[g]["streets"]
                    break
        if st:
            return "אזור " + ", ".join(st[:2])
        return "אזור ללא שם רשמי, גוש " + min(groups[(city, key)], key=lambda x: int(x) if x.isdigit() else 0)

    labels = {k: label(*k) for k in groups}
    return {g: (gk[g][0], labels[gk[g]]) for g in gk}


# ---------------------------------------------------------------- statistics
def med(v):
    return statistics.median(v) if v else None


def compute(deals, area_of, last_ym):
    """last_ym: YYMM int of latest data month."""
    def ym_minus(ym, months):
        y, m = 2000 + ym // 100, ym % 100
        t = y * 12 + (m - 1) - months
        return (t // 12 - 2000) * 100 + t % 12 + 1
    c12, c24, c60 = ym_minus(last_ym, 11), ym_minus(last_ym, 23), ym_minus(last_ym, 59)

    PXc = collections.defaultdict(lambda: collections.defaultdict(list))
    PXa = collections.defaultdict(lambda: collections.defaultdict(list))
    SQc = collections.defaultdict(lambda: collections.defaultdict(list))   # ppsqm per city: (period, kind)
    SQa = collections.defaultdict(lambda: collections.defaultdict(list))
    tot12, map12, tot5, map5 = collections.Counter(), collections.Counter(), collections.Counter(), collections.Counter()
    n_all = dropped = 0
    GA = collections.defaultdict(set)   # (city, area label) -> blocks with deals there, so the app can list the deals behind each row
    for city, gs in deals.items():
        for g, s in gs.items():
            a = area_of.get(g)
            if a and a[0] != city:
                a = (city, a[1])
            if a:
                GA[a].add(g)
            for d in s.split(";"):
                f = d.split("|")
                ym, pr, yb, rm, ar, t = int(f[0]), float(f[1] or 0), f[2], f[3], f[4], f[5]
                if ym < c60 or ym > last_ym:
                    continue
                n_all += 1
                yb = int(yb) if yb.isdigit() and 1900 < int(yb) < 2035 else None
                try:
                    rm = float(rm)
                except ValueError:
                    rm = None
                try:
                    ar = float(ar)
                except ValueError:
                    ar = None
                if pr < 150000 or pr > 40e6 or (ar and ar > 20 and not 2000 <= pr / ar <= 150000):
                    dropped += 1
                    continue
                sy = 2000 + ym // 100
                per = [5] + ([2] if ym >= c24 else []) + ([1] if ym >= c12 else [])
                ages = [0]
                if yb:
                    ages.append(1 if sy - yb <= 2 else 2)
                    ages.append(3 if yb >= 1993 else 4)
                rooms = [0]
                if t in "AGR" and rm:
                    r = int(rm + .01)
                    rooms += [1] if r <= 3 else [2] if r == 4 else [3]
                elif t == "H":
                    rooms.append(4)
                sg = [ai * 5 + ri for ai in ages for ri in rooms]
                for p in per:
                    for x in sg:
                        PXc[city][(p, x)].append(pr)
                        if a:
                            PXa[a][(p, x)].append(pr)
                tot5[city] += 1
                if a:
                    map5[city] += 1
                # price per sqm, apartments only, last 24 months
                if t in "AGRM" and ar and ar >= 25 and ym >= c24:
                    ps = pr / ar
                    kind = ("rec" if ym >= c12 else "base")
                    old = yb is not None and sy - yb >= 3
                    new = yb is not None and sy - yb <= 2
                    for tgt in ([SQc[city]] + ([SQa[a]] if a else [])):
                        tgt[(kind, "all")].append(ps)
                        if old:
                            tgt[(kind, "old")].append(ps)
                        if new:
                            tgt[(kind, "new")].append(ps)
                if ym >= c12:
                    tot12[city] += 1
                    if a:
                        map12[city] += 1

    def cell(v):
        return [round(statistics.median(v) / 1000), round(sum(v) / len(v) / 1000), len(v)] if len(v) >= 5 else None

    def pack(d):   # sparse: {key: [last 12m, 24m, 60m]} only where the 5-year cell has enough deals
        out = {}
        for k in range(25):
            if len(d.get((5, k), [])) >= 5:
                out[k] = [cell(d.get((p, k), [])) for p in (1, 2, 5)]
        return out

    px_c = {c: pack(d) for c, d in PXc.items() if len(d.get((5, 0), [])) >= 5}
    px_a = collections.defaultdict(list)
    for (c, lbl), d in PXa.items():
        if len(d.get((5, 0), [])) >= 5:
            px_a[c].append([lbl, pack(d), ",".join(sorted(GA[(c, lbl)], key=lambda x: int(x) if x.isdigit() else 0))])
    for c in px_a:
        px_a[c].sort(key=lambda r: (-((r[1][0][0] or [0, 0, 0])[2]), -(r[1][0][2][2])))
    px_cov = {c: round(map5[c] / tot5[c] * 100) for c in px_a if tot5[c]}

    def chg(d):
        a, b = d.get(("rec", "old"), []), d.get(("base", "old"), [])
        return round((med(a) / med(b) - 1) * 100, 1) if len(a) >= 10 and len(b) >= 10 else None

    areas = collections.defaultdict(list)
    for (c, lbl), d in SQa.items():
        v = d.get(("rec", "all"), [])
        if len(v) < 3:
            continue
        o, nw = d.get(("rec", "old"), []), d.get(("rec", "new"), [])
        areas[c].append([lbl, int(round(med(v), -2)), len(v), int(round(med(o), -2)) if len(o) >= 3 else 0,
                         int(round(med(nw), -2)) if len(nw) >= 3 else 0, chg(d)])
    for c in areas:
        areas[c].sort(key=lambda x: -x[2])
    cov = {c: round(map12[c] / tot12[c] * 100) for c in tot12 if tot12[c] and c in areas}
    cities = {}
    for c, d in SQc.items():
        ch = chg(d)
        o = d.get(("rec", "old"), [])
        if ch is not None and len(o) >= 20:
            cities[c] = [ch, len(o), round(med(o))]
    stats = {"deals5": n_all, "dropped": dropped, "map12": sum(map12.values()), "tot12": sum(tot12.values())}
    return {"v": 2, "ages": AGES, "rooms": ROOMS, "c": px_c, "a": px_a, "cov": px_cov}, {"a": areas, "cov": cov}, cities, stats


# ---------------------------------------------------------------- splice into the app
def js(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def replace_const(h, name, value_js):
    i = h.index(f"const {name} = ")
    if h[i:].startswith(f"const {name} = {{\n"):   # multi-line literal (MARKET)
        j = h.index("\n};", i) + 3
    else:
        j = h.index("\n", i)
    return h[:i] + f"const {name} = {value_js};" + h[j:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--market")
    ap.add_argument("--report", default="update_report.json")
    a = ap.parse_args()
    h = open(a.app, encoding="utf-8").read()
    old = {k: json.loads(re.search(rf"^const {k} = (.*);$", h, re.M).group(1)) for k in ["NAT", "OFFICIAL", "AREAS", "AREAS_COV", "PX"]}
    D = json.load(open(os.path.join(a.data, "dict.json")))
    ga = json.load(open(os.path.join(a.data, "gush_area.json")))
    top = {r["gush"]: r for r in json.load(open(os.path.join(a.data, "gush_top_helka.json")))}
    today = datetime.date.today()
    rep = {"date": today.isoformat(), "problems": []}

    log("1/5 lotteries")
    official, n_lot = build_official()
    rep["lotteries"] = {"rows": n_lot, "projects": len(official["p"]), "before": len(old["OFFICIAL"]["p"])}

    log("2/5 deals")
    last = q(f"SELECT max(to_date(deal_date,'DD/MM/YYYY')) m FROM {DEALS}")[0]["m"]
    last_d = datetime.date.fromisoformat(str(last)[:10])
    last_ym = (last_d.year - 2000) * 100 + last_d.month
    # deals reach the Tax Authority weeks or months late, so the newest months are partial. A month counts as
    # complete only when it has at least 60% of the usual monthly volume (median of the 6 months before it).
    mc = q(f"SELECT to_char(to_date(deal_date,'DD/MM/YYYY'),'YYYY-MM') m, count(*) n FROM {DEALS} "
           f"WHERE to_date(deal_date,'DD/MM/YYYY') >= '{(last_d - datetime.timedelta(days=400)).isoformat()}' GROUP BY 1 ORDER BY 1")
    months = [(r["m"], int(r["n"])) for r in mc]
    pick = months[-1][0] if months else last_d.strftime("%Y-%m")
    for i in range(len(months) - 1, 5, -1):
        base = statistics.median(n for _, n in months[i - 6:i])
        if months[i][1] >= 0.6 * base:
            pick = months[i][0]
            break
    y, m = int(pick[:4]), int(pick[5:7])
    last_ym = (y - 2000) * 100 + m
    rep["months"] = months[-8:]
    since = datetime.date(y - 5, m, 1) + datetime.timedelta(days=32)
    since = since.replace(day=1).isoformat()
    deals = pull_deals(since)
    n_total = q(f"SELECT count(*) n FROM {DEALS}")[0]["n"]
    scraped = str(q(f"SELECT max(scraped_at) s FROM {DEALS}")[0]["s"])[:10]

    log("3/5 new blocks")
    recent_cut = last_ym - 100
    rep["looked_up"] = lookup_new_gushes(deals, ga, top, recent_cut)
    json.dump(ga, open(os.path.join(a.data, "gush_area.json"), "w"), ensure_ascii=False)
    json.dump(list(top.values()), open(os.path.join(a.data, "gush_top_helka.json"), "w"), ensure_ascii=False)

    log("4/5 statistics")
    area_of = area_map(D, ga, top)
    px, areas, cities, st = compute(deals, area_of, last_ym)
    rep["stats"] = st
    nat = dict(old["NAT"])
    nat.update({"generated": today.strftime("%-d.%-m.%Y"), "through": f"{HEB_MONTHS[m - 1]} {y}", "thruYM": f"{y}-{m:02d}", "scraped": scraped, "deals": n_total, "cities": cities})

    # ---- sanity checks against the previous version
    def chk(cond, msg):
        if not cond:
            rep["problems"].append(msg)
    nA, nA0 = sum(len(v) for v in areas["a"].values()), sum(len(v) for v in old["AREAS"].values())
    chk(n_total >= old["NAT"]["deals"] * 0.98, f"deals count fell: {n_total} < {old['NAT']['deals']}")
    chk(len(official["p"]) >= len(old["OFFICIAL"]["p"]) * 0.97, f"projects fell: {len(official['p'])}")
    chk(nA >= nA0 * 0.9, f"areas fell: {nA} vs {nA0}")
    chk(len(px["c"]) >= len(old["PX"]["c"]) * 0.9, f"price cities fell: {len(px['c'])}")
    chk(len(cities) >= 40, f"too few cities with price change: {len(cities)}")
    cov = st["map12"] / max(1, st["tot12"])
    chk(cov >= 0.95, f"national area coverage {cov:.1%}")
    pt = next((v for k, v in areas["a"].items() if k.replace(" ", "") in ("פתחתקווה", "פתחתקוה")), [])
    chk(any("עין גנים" in r[0] for r in pt), "Petah Tikva area list lost Ein Ganim")
    rep["areas"] = {"n": nA, "before": nA0, "coverage12": round(cov * 100, 1), "cities_chg": len(cities), "px_cities": len(px["c"])}
    rep["through"] = nat["through"]

    log("5/5 splice")
    h = replace_const(h, "NAT", js(nat))
    h = replace_const(h, "OFFICIAL", js(official))
    h = replace_const(h, "AREAS", js(areas["a"]))
    h = replace_const(h, "AREAS_COV", js(areas["cov"]))
    h = replace_const(h, "PX", js(px))
    if a.market:
        mk = json.load(open(a.market, encoding="utf-8"))
        h = replace_const(h, "MARKET", json.dumps(mk, ensure_ascii=False, indent=1))
        rep["market_updated"] = mk.get("updated")
    open(a.out, "w", encoding="utf-8").write(h)
    json.dump(rep, open(a.report, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    sys.exit(2 if rep["problems"] else 0)


if __name__ == "__main__":
    main()
