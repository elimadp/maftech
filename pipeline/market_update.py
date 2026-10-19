#!/usr/bin/env python3
"""Refresh the market numbers in market.json from official public APIs.

  Bank of Israel interest rate + next decision date:  https://www.boi.org.il/PublicApi/GetInterest
  CBS indices (consumer prices, housing prices, residential construction inputs):
      https://api.cbs.gov.il/index/data/price?id=<code>&format=json&download=false&last=<n>

Usage: python3 market_update.py market.json
Anything that cannot be fetched or fails a sanity check is left as it was (and reported).
Average mortgage rates are not touched here.
"""
import datetime, json, sys
import requests

HEB_MONTHS = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני", "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"]
CBS = "https://api.cbs.gov.il/index/data/price"
SERIES = {"cpi": (120010, "צרכן"), "housing": (40010, "דירות"), "construction": (200010, "תשומ")}


def dmy(d):
    return f"{d.day}.{d.month}.{d.year}"


def get_json(url, **params):
    r = requests.get(url, params=params, timeout=60, headers={"User-Agent": "maftech-data-update"})
    r.raise_for_status()
    return r.json()


def boi(mk, log):
    j = get_json("https://www.boi.org.il/PublicApi/GetInterest")
    rate = float(j["currentInterest"])
    if not 0 <= rate <= 15:
        raise ValueError(f"rate out of range: {rate}")
    pub = datetime.datetime.fromisoformat(j["lastPublishedDate"].replace("Z", "+00:00")).astimezone(datetime.timezone(datetime.timedelta(hours=3))).date()
    nxt = datetime.datetime.fromisoformat(j["nextInterestDate"].replace("Z", "+00:00")).date()
    changed = False
    if mk["boi"].get("rate") != rate or mk["boi"].get("date") != dmy(pub):
        mk["boi"].update({"rate": rate, "date": dmy(pub), "src": "https://www.boi.org.il/"})
        mk["prime"] = round(rate + 1.5, 2)
        changed = True
        log.append(f"ריבית בנק ישראל: {rate}% (מ-{dmy(pub)})")
    if mk.get("nextBoiISO") != nxt.isoformat():
        mk["nextBoiISO"] = nxt.isoformat()
        mk["boi"]["next"] = dmy(nxt)
        changed = True
        log.append(f"החלטת הריבית הבאה: {dmy(nxt)}")
    return changed


def points(obj):
    """All {year, month, percent, percentYear} entries anywhere in the CBS response, oldest first."""
    out, name = [], ""
    def walk(o):
        nonlocal name
        if isinstance(o, dict):
            if isinstance(o.get("name"), str) and not name:
                name = o["name"]
            if "year" in o and "month" in o and ("percent" in o or "percentYear" in o):
                out.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(obj)
    out.sort(key=lambda p: (int(p["year"]), int(p["month"])))
    return out, name


def cbs(key, last=13):
    code, must = SERIES[key]
    pts, name = points(get_json(CBS, id=code, format="json", download="false", last=last))
    if not pts:
        raise ValueError("no data points")
    if name and must not in name:
        raise ValueError(f"unexpected series name: {name}")
    for p in pts:
        for f in ("percent", "percentYear"):
            if p.get(f) is not None and not -30 <= float(p[f]) <= 30:
                raise ValueError(f"{f} out of range: {p[f]}")
    return pts


def month_label(p):
    return f"{HEB_MONTHS[int(p['month']) - 1]} {int(p['year'])}"


def update(path):
    mk = json.load(open(path, encoding="utf-8"))
    log, problems, changed = [], [], False
    try:
        changed |= boi(mk, log)
    except Exception as e:
        problems.append(f"bank of israel: {e}")
    today = datetime.date.today()
    try:
        p = cbs("cpi")[-1]
        if mk["cpi"].get("month") != month_label(p):
            mk["cpi"].update({"month": month_label(p), "mom": round(float(p["percent"]), 1), "yoy": round(float(p["percentYear"]), 1),
                              "published": dmy(today), "src": "https://www.cbs.gov.il/he/Pages/default.aspx"})
            changed = True
            log.append(f"מדד המחירים לצרכן ל{month_label(p)}: {p['percent']}%")
    except Exception as e:
        problems.append(f"cpi: {e}")
    try:
        p = cbs("housing")[-1]
        if p.get("percentYear") is not None and mk["cpi"].get("housingYoy") != round(float(p["percentYear"]), 1):
            mk["cpi"]["housingYoy"] = round(float(p["percentYear"]), 1)
            changed = True
            log.append(f"מחירי הדירות בשנה האחרונה: {p['percentYear']}%")
    except Exception as e:
        problems.append(f"housing prices: {e}")
    try:
        pts = cbs("construction")
        p = pts[-1]
        if mk["construction"].get("month") != month_label(p):
            year = [x for x in pts if int(x["year"]) == int(p["year"])]
            ytd = 1.0
            for x in year:
                ytd *= 1 + float(x["percent"]) / 100
            mk["construction"].update({"month": month_label(p), "mom": round(float(p["percent"]), 1), "ytd": round((ytd - 1) * 100, 1),
                                       "monthly": [round(float(x["percent"]), 1) for x in year], "src": "https://www.cbs.gov.il/he/Pages/default.aspx"})
            changed = True
            log.append(f"מדד תשומות הבנייה ל{month_label(p)}: {p['percent']}%")
    except Exception as e:
        problems.append(f"construction index: {e}")
    if changed:
        mk["updated"], mk["updatedISO"] = dmy(today), today.isoformat()
        json.dump(mk, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"changed": changed, "log": log, "problems": problems}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(update(sys.argv[1]))
